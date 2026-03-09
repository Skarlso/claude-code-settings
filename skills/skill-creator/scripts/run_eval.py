#!/usr/bin/env python3
"""Run trigger evaluation for a skill description.

Tests whether a skill's description causes an agent to trigger for a set of
queries. Outputs results as JSON.

Supports multiple platforms via --platform:
  claude-code  (default) Uses Claude Code stream events (authoritative)
  openclaw               Uses OpenClaw response-sentinel heuristic
  codex                  Uses Codex response-sentinel heuristic
"""

import argparse
import json
import sys
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from scripts.utils import parse_skill_md


def _make_adapter(platform: str, openclaw_agent: str, model: str | None):
    """Instantiate the correct PlatformAdapter for the given platform string."""
    if platform == "openclaw":
        from scripts.platforms.openclaw import OpenClawAdapter
        return OpenClawAdapter(agent_id=openclaw_agent)
    elif platform == "codex":
        from scripts.platforms.codex import CodexAdapter
        return CodexAdapter()
    else:
        from scripts.platforms.claude_code import ClaudeCodeAdapter
        return ClaudeCodeAdapter(model=model)


def run_single_query(
    query: str,
    skill_name: str,
    skill_description: str,
    timeout: int,
    model: str | None,
    platform: str,
    openclaw_agent: str,
) -> dict:
    """Run a single query and return whether the skill was triggered.

    Creates a temporary skill via the platform adapter, runs the query, detects
    triggering, then cleans up. Each call is self-contained so it is safe to
    run in a subprocess worker.
    """
    adapter = _make_adapter(platform, openclaw_agent, model)
    unique_id = uuid.uuid4().hex[:8]
    sentinel = f"SKILL_ACTIVE_{unique_id}"
    temp_name = f"{skill_name}-skill-{unique_id}"

    registration = adapter.register_skill(temp_name, skill_description, sentinel)
    try:
        run_result = adapter.run_query(query, timeout, model)
        if run_result is None:
            return {
                "triggered": False,
                "detection_mode": registration.detection_mode,
                "detection_details": registration.detection_details,
            }
        return {
            "triggered": adapter.detect_trigger(run_result, registration),
            "detection_mode": registration.detection_mode,
            "detection_details": registration.detection_details,
        }
    finally:
        adapter.unregister_skill(registration)


def run_eval(
    eval_set: list[dict],
    skill_name: str,
    description: str,
    num_workers: int,
    timeout: int,
    platform: str = "claude-code",
    openclaw_agent: str = "main",
    runs_per_query: int = 1,
    trigger_threshold: float = 0.5,
    model: str | None = None,
    # Legacy parameter kept for backward compatibility
    project_root: Path | None = None,
) -> dict:
    """Run the full eval set and return results."""
    results = []

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        future_to_info = {}
        for item in eval_set:
            for run_idx in range(runs_per_query):
                future = executor.submit(
                    run_single_query,
                    item["query"],
                    skill_name,
                    description,
                    timeout,
                    model,
                    platform,
                    openclaw_agent,
                )
                future_to_info[future] = (item, run_idx)

        query_triggers: dict[str, list[bool]] = {}
        query_items: dict[str, dict] = {}
        detection_modes: set[str] = set()
        detection_details: list[str] = []
        for future in as_completed(future_to_info):
            item, _ = future_to_info[future]
            query = item["query"]
            query_items[query] = item
            if query not in query_triggers:
                query_triggers[query] = []
            try:
                outcome = future.result()
                query_triggers[query].append(outcome["triggered"])
                detection_modes.add(outcome["detection_mode"])
                detail = outcome.get("detection_details")
                if detail and detail not in detection_details:
                    detection_details.append(detail)
            except Exception as e:
                print(f"Warning: query failed: {e}", file=sys.stderr)
                query_triggers[query].append(False)

    for query, triggers in query_triggers.items():
        item = query_items[query]
        trigger_rate = sum(triggers) / len(triggers)
        should_trigger = item["should_trigger"]
        if should_trigger:
            did_pass = trigger_rate >= trigger_threshold
        else:
            did_pass = trigger_rate < trigger_threshold
        results.append({
            "query": query,
            "should_trigger": should_trigger,
            "trigger_rate": trigger_rate,
            "triggers": sum(triggers),
            "runs": len(triggers),
            "pass": did_pass,
            "detection_mode": next(iter(detection_modes), "unknown"),
        })

    passed = sum(1 for r in results if r["pass"])
    total = len(results)

    return {
        "skill_name": skill_name,
        "description": description,
        "platform": platform,
        "detection": {
            "mode": next(iter(detection_modes), "unknown"),
            "details": detection_details,
            "heuristic": "heuristic" in detection_modes,
        },
        "results": results,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Run trigger evaluation for a skill description")
    parser.add_argument("--eval-set", required=True, help="Path to eval set JSON file")
    parser.add_argument("--skill-path", required=True, help="Path to skill directory")
    parser.add_argument("--description", default=None, help="Override description to test")
    parser.add_argument("--num-workers", type=int, default=10, help="Number of parallel workers")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per query in seconds")
    parser.add_argument("--runs-per-query", type=int, default=3, help="Number of runs per query")
    parser.add_argument("--trigger-threshold", type=float, default=0.5, help="Trigger rate threshold")
    parser.add_argument("--model", default=None, help="Model to use (platform-specific)")
    parser.add_argument(
        "--platform",
        choices=["claude-code", "openclaw", "codex"],
        default="claude-code",
        help="Platform to test against (default: claude-code)",
    )
    parser.add_argument(
        "--openclaw-agent",
        default="main",
        help="OpenClaw agent id to use (default: main, openclaw platform only)",
    )
    parser.add_argument("--verbose", action="store_true", help="Print progress to stderr")
    args = parser.parse_args()

    eval_set = json.loads(Path(args.eval_set).read_text())
    skill_path = Path(args.skill_path)

    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    name, original_description, _ = parse_skill_md(skill_path)
    description = args.description or original_description

    if args.verbose:
        print(f"Platform: {args.platform}", file=sys.stderr)
        print(f"Evaluating: {description}", file=sys.stderr)

    output = run_eval(
        eval_set=eval_set,
        skill_name=name,
        description=description,
        num_workers=args.num_workers,
        timeout=args.timeout,
        platform=args.platform,
        openclaw_agent=args.openclaw_agent,
        runs_per_query=args.runs_per_query,
        trigger_threshold=args.trigger_threshold,
        model=args.model,
    )

    if args.verbose:
        summary = output["summary"]
        print(f"Results: {summary['passed']}/{summary['total']} passed", file=sys.stderr)
        for r in output["results"]:
            status = "PASS" if r["pass"] else "FAIL"
            rate_str = f"{r['triggers']}/{r['runs']}"
            print(f"  [{status}] rate={rate_str} expected={r['should_trigger']}: {r['query'][:70]}", file=sys.stderr)

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
