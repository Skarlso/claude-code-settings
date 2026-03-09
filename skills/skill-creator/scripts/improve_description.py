#!/usr/bin/env python3
"""Improve a skill description based on eval results.

The optimizer runtime is pluggable so the description improver can run on the
same host/runtime family as the skill under evaluation instead of depending on
the Anthropic SDK.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import anthropic
except ImportError:  # pragma: no cover - optional dependency
    anthropic = None

from scripts.utils import parse_skill_md


@dataclass
class ProviderResponse:
    """Normalized optimizer response."""

    provider: str
    text: str
    raw_response: str
    stderr: str = ""
    thinking: str = ""


def _extract_tagged_description(text: str) -> str:
    """Extract the final description from <new_description> tags if present."""
    match = re.search(r"<new_description>(.*?)</new_description>", text, re.DOTALL)
    return match.group(1).strip().strip('"') if match else text.strip().strip('"')


def _build_improvement_prompt(
    skill_name: str,
    skill_content: str,
    current_description: str,
    eval_results: dict,
    history: list[dict],
    test_results: dict | None,
) -> str:
    failed_triggers = [
        r for r in eval_results["results"]
        if r["should_trigger"] and not r["pass"]
    ]
    false_triggers = [
        r for r in eval_results["results"]
        if not r["should_trigger"] and not r["pass"]
    ]

    train_score = f"{eval_results['summary']['passed']}/{eval_results['summary']['total']}"
    if test_results:
        test_score = f"{test_results['summary']['passed']}/{test_results['summary']['total']}"
        scores_summary = f"Train: {train_score}, Test: {test_score}"
    else:
        scores_summary = f"Train: {train_score}"

    prompt = f"""You are optimizing a skill description for an AI agent skill called "{skill_name}". A "skill" is a prompt-like capability with progressive disclosure: the agent first sees the skill name and description, and only reads the full SKILL.md plus bundled resources if it decides the skill is relevant.

The description appears in the agent's available skills list. When a user sends a query, the agent decides whether to invoke the skill based solely on the title and on this description. Your goal is to write a description that triggers for relevant queries, and doesn't trigger for irrelevant ones.

Here's the current description:
<current_description>
"{current_description}"
</current_description>

Current scores ({scores_summary}):
<scores_summary>
"""
    if failed_triggers:
        prompt += "FAILED TO TRIGGER (should have triggered but didn't):\n"
        for result in failed_triggers:
            prompt += f'  - "{result["query"]}" (triggered {result["triggers"]}/{result["runs"]} times)\n'
        prompt += "\n"

    if false_triggers:
        prompt += "FALSE TRIGGERS (triggered but shouldn't have):\n"
        for result in false_triggers:
            prompt += f'  - "{result["query"]}" (triggered {result["triggers"]}/{result["runs"]} times)\n'
        prompt += "\n"

    if history:
        prompt += "PREVIOUS ATTEMPTS (do NOT repeat these — try something structurally different):\n\n"
        for attempt in history:
            train_value = f"{attempt.get('train_passed', attempt.get('passed', 0))}/{attempt.get('train_total', attempt.get('total', 0))}"
            test_value = None
            if attempt.get("test_passed") is not None:
                test_value = f"{attempt.get('test_passed', '?')}/{attempt.get('test_total', '?')}"
            score_str = f"train={train_value}" + (f", test={test_value}" if test_value else "")
            prompt += f'<attempt {score_str}>\n'
            prompt += f'Description: "{attempt["description"]}"\n'
            if "results" in attempt:
                prompt += "Train results:\n"
                for result in attempt["results"]:
                    status = "PASS" if result["pass"] else "FAIL"
                    prompt += f'  [{status}] "{result["query"][:80]}" (triggered {result["triggers"]}/{result["runs"]})\n'
            if attempt.get("note"):
                prompt += f'Note: {attempt["note"]}\n'
            prompt += "</attempt>\n\n"

    prompt += f"""</scores_summary>

Skill content (for context on what the skill does):
<skill_content>
{skill_content}
</skill_content>

Based on the failures, write a new and improved description that is more likely to trigger correctly. Do not overfit to the exact queries above. Generalize from them into broader user intents and situations where this skill should or should not be used.

Constraints:
1. Avoid overfitting to the exact eval prompts.
2. Keep the description concise because it competes with other skills for limited metadata space.
3. Prefer roughly 100-200 words, and never exceed 1024 characters.

Helpful guidance:
- Phrase the description in the imperative: "Use this skill for..." rather than "This skill does..."
- Focus on user intent and problem shape, not implementation details.
- Make it distinctive enough to win against adjacent skills when appropriate.
- If repeated iterations keep failing, try a different structure instead of appending more keywords.

Respond with only the new description text in <new_description> tags, nothing else."""
    return prompt


def _build_shorten_prompt(previous_response: str, char_count: int) -> str:
    """Build a follow-up prompt that forces the description under the hard limit."""
    return f"""Your previous response produced a description that is {char_count} characters long, which exceeds the hard 1024 character limit.

Previous response:
<previous_response>
{previous_response}
</previous_response>

Rewrite it to be under 1024 characters while preserving the most important trigger words and intent coverage.

Respond with only the new description in <new_description> tags."""


def _run_subprocess(
    cmd: list[str],
    prompt: str,
    timeout: int = 300,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess prompt-driven LLM command."""
    return subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _call_anthropic(prompt: str, model: str | None) -> ProviderResponse:
    """Call Anthropic via SDK as an explicit fallback provider."""
    if anthropic is None:
        raise RuntimeError("Anthropic SDK is not installed.")
    if not model:
        raise RuntimeError("Anthropic optimizer requires --model.")

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=16000,
        thinking={
            "type": "enabled",
            "budget_tokens": 10000,
        },
        messages=[{"role": "user", "content": prompt}],
    )

    thinking_text = ""
    text = ""
    for block in response.content:
        if block.type == "thinking":
            thinking_text = block.thinking
        elif block.type == "text":
            text = block.text

    return ProviderResponse(
        provider="anthropic",
        text=text,
        raw_response=text,
        thinking=thinking_text,
    )


def _call_codex(prompt: str, model: str | None) -> ProviderResponse:
    """Call Codex CLI in non-interactive mode."""
    cmd = [
        "codex",
        "exec",
        "--json",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
    ]
    if model:
        cmd.extend(["--model", model])

    result = _run_subprocess(cmd, prompt)
    last_text: str | None = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "agent_message"
        ):
            last_text = event["item"].get("text", "")

    if last_text is None:
        raise RuntimeError(f"Codex optimizer did not return an agent message. stderr={result.stderr.strip()}")

    return ProviderResponse(
        provider="codex",
        text=last_text,
        raw_response=result.stdout,
        stderr=result.stderr,
    )


def _call_claude_code(prompt: str, model: str | None) -> ProviderResponse:
    """Call Claude Code in print mode."""
    cmd = [
        "claude",
        "-p",
        "--output-format",
        "text",
    ]
    if model:
        cmd.extend(["--model", model])

    env = {key: value for key, value in os.environ.items() if key != "CLAUDECODE"}
    result = _run_subprocess(cmd, prompt, env=env)
    text = result.stdout.strip()
    if not text:
        raise RuntimeError(f"Claude Code optimizer returned empty output. stderr={result.stderr.strip()}")

    return ProviderResponse(
        provider="claude-code",
        text=text,
        raw_response=result.stdout,
        stderr=result.stderr,
    )


def _call_openclaw(prompt: str, openclaw_agent: str) -> ProviderResponse:
    """Call OpenClaw in local agent mode."""
    cmd = [
        "openclaw",
        "agent",
        "--local",
        "--agent",
        openclaw_agent,
        "--message",
        prompt,
        "--json",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"OpenClaw optimizer failed: {result.stderr.strip()}")

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenClaw optimizer returned invalid JSON.") from exc

    text = ""
    payloads = payload.get("payloads", [])
    if payloads:
        text = payloads[0].get("text", "")
    if not text:
        raise RuntimeError("OpenClaw optimizer returned empty payload text.")

    return ProviderResponse(
        provider="openclaw",
        text=text,
        raw_response=result.stdout,
        stderr=result.stderr,
    )


def resolve_optimizer_platform(optimizer_platform: str, eval_platform: str) -> str:
    """Resolve the optimizer runtime to use."""
    if optimizer_platform != "auto":
        return optimizer_platform

    if eval_platform in {"claude-code", "openclaw", "codex"}:
        return eval_platform

    if shutil.which("codex"):
        return "codex"
    if shutil.which("claude"):
        return "claude-code"
    if shutil.which("openclaw"):
        return "openclaw"
    if anthropic is not None:
        return "anthropic"

    raise RuntimeError("Unable to resolve an optimizer runtime. Install codex/claude/openclaw or Anthropics SDK.")


def _request_provider_response(
    prompt: str,
    optimizer_platform: str,
    model: str | None,
    openclaw_agent: str,
) -> ProviderResponse:
    """Dispatch the optimizer request to the selected provider."""
    if optimizer_platform == "codex":
        return _call_codex(prompt, model)
    if optimizer_platform == "claude-code":
        return _call_claude_code(prompt, model)
    if optimizer_platform == "openclaw":
        return _call_openclaw(prompt, openclaw_agent)
    if optimizer_platform == "anthropic":
        return _call_anthropic(prompt, model)
    raise RuntimeError(f"Unsupported optimizer platform: {optimizer_platform}")


def improve_description(
    skill_name: str,
    skill_content: str,
    current_description: str,
    eval_results: dict,
    history: list[dict],
    model: str | None,
    optimizer_platform: str = "auto",
    eval_platform: str = "claude-code",
    openclaw_agent: str = "main",
    test_results: dict | None = None,
    log_dir: Path | None = None,
    iteration: int | None = None,
) -> str:
    """Rewrite the skill description with a runtime-appropriate optimizer."""
    resolved_optimizer = resolve_optimizer_platform(optimizer_platform, eval_platform)
    prompt = _build_improvement_prompt(
        skill_name=skill_name,
        skill_content=skill_content,
        current_description=current_description,
        eval_results=eval_results,
        history=history,
        test_results=test_results,
    )

    response = _request_provider_response(
        prompt=prompt,
        optimizer_platform=resolved_optimizer,
        model=model,
        openclaw_agent=openclaw_agent,
    )
    description = _extract_tagged_description(response.text)

    transcript: dict = {
        "iteration": iteration,
        "optimizer_platform": resolved_optimizer,
        "prompt": prompt,
        "thinking": response.thinking,
        "response": response.text,
        "raw_response": response.raw_response,
        "stderr": response.stderr,
        "parsed_description": description,
        "char_count": len(description),
        "over_limit": len(description) > 1024,
    }

    if len(description) > 1024:
        shorten_prompt = _build_shorten_prompt(response.text, len(description))
        shorten_response = _request_provider_response(
            prompt=shorten_prompt,
            optimizer_platform=resolved_optimizer,
            model=model,
            openclaw_agent=openclaw_agent,
        )
        shortened = _extract_tagged_description(shorten_response.text)

        transcript["rewrite_prompt"] = shorten_prompt
        transcript["rewrite_thinking"] = shorten_response.thinking
        transcript["rewrite_response"] = shorten_response.text
        transcript["rewrite_raw_response"] = shorten_response.raw_response
        transcript["rewrite_stderr"] = shorten_response.stderr
        transcript["rewrite_description"] = shortened
        transcript["rewrite_char_count"] = len(shortened)
        description = shortened

    transcript["final_description"] = description

    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"improve_iter_{iteration or 'unknown'}.json"
        log_file.write_text(json.dumps(transcript, indent=2))

    return description


def main():
    parser = argparse.ArgumentParser(description="Improve a skill description based on eval results")
    parser.add_argument("--eval-results", required=True, help="Path to eval results JSON (from run_eval.py)")
    parser.add_argument("--skill-path", required=True, help="Path to skill directory")
    parser.add_argument("--history", default=None, help="Path to history JSON (previous attempts)")
    parser.add_argument("--model", default=None, help="Model override for runtimes that support it")
    parser.add_argument(
        "--optimizer-platform",
        choices=["auto", "claude-code", "openclaw", "codex", "anthropic"],
        default="auto",
        help="Runtime used to rewrite descriptions",
    )
    parser.add_argument("--openclaw-agent", default="main", help="OpenClaw agent id when using the OpenClaw optimizer")
    parser.add_argument("--verbose", action="store_true", help="Print selected optimizer details to stderr")
    args = parser.parse_args()

    skill_path = Path(args.skill_path)
    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    eval_results = json.loads(Path(args.eval_results).read_text())
    history = []
    if args.history:
        history = json.loads(Path(args.history).read_text())

    name, _, content = parse_skill_md(skill_path)
    current_description = eval_results["description"]

    if args.verbose:
        print(f"Current: {current_description}", file=sys.stderr)
        print(f"Score: {eval_results['summary']['passed']}/{eval_results['summary']['total']}", file=sys.stderr)

    new_description = improve_description(
        skill_name=name,
        skill_content=content,
        current_description=current_description,
        eval_results=eval_results,
        history=history,
        model=args.model,
        optimizer_platform=args.optimizer_platform,
        openclaw_agent=args.openclaw_agent,
    )

    if args.verbose:
        print(f"Improved: {new_description}", file=sys.stderr)

    output = {
        "description": new_description,
        "history": history + [{
            "description": current_description,
            "passed": eval_results["summary"]["passed"],
            "failed": eval_results["summary"]["failed"],
            "total": eval_results["summary"]["total"],
            "results": eval_results["results"],
        }],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
