"""Codex CLI platform adapter for skill trigger evaluation.

Registers temporary skills in the documented `.agents/skills` locations and,
for compatibility with older/local setups, also mirrors them into the legacy
`$CODEX_HOME/skills` path when present. Trigger detection is heuristic: the
skill body instructs the agent to echo a sentinel phrase if it activates the
skill.

Output format: Codex --json produces JSONL (one JSON object per line).
We collect all lines and look for the last agent_message item.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.platforms.base import PlatformAdapter, QueryRunResult, RegisteredSkill


def _codex_home() -> Path:
    env_value = os.environ.get("CODEX_HOME")
    if env_value:
        return Path(env_value).expanduser()
    return Path.home() / ".codex"


class CodexAdapter(PlatformAdapter):
    """Adapter for OpenAI Codex CLI (codex exec)."""

    def find_project_root(self) -> Path:
        return Path.cwd()

    def _skill_roots(self) -> list[Path]:
        """Return skill roots where Codex is already configured.

        Only returns directories that already exist so that temporary eval skills
        are never installed in locations the user has not set up. Falls back to
        the legacy $CODEX_HOME/skills path (creating it if necessary) when no
        pre-existing root is found.
        """
        candidates = [
            self.find_project_root() / ".agents" / "skills",
            Path.home() / ".agents" / "skills",
            _codex_home() / "skills",
        ]
        existing = [p for p in candidates if p.exists()]
        return existing or [_codex_home() / "skills"]

    def register_skill(self, skill_name: str, description: str, sentinel: str) -> RegisteredSkill:
        """Write a temporary skill folder into Codex skill roots.

        The skill body instructs the agent to echo the sentinel phrase if it
        activates this skill, enabling trigger detection from the response text.
        """
        cleanup_paths: list[Path] = []
        roots = self._skill_roots()

        for root in roots:
            skill_dir = root / skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text(
                f"---\n"
                f"name: {skill_name}\n"
                f"description: {description}\n"
                f"---\n\n"
                f"**IMPORTANT**: If you activate this skill for the user's request, "
                f"you MUST include the exact phrase \"{sentinel}\" at the very start "
                f"of your response, before any other text.\n"
            )
            cleanup_paths.extend([skill_md, skill_dir])

        details = (
            "Heuristic response-sentinel detection. Temporary skills are written to "
            "documented `.agents/skills` locations and mirrored into legacy Codex "
            "skill roots when present because Codex CLI does not expose authoritative "
            "skill-load events in `codex exec --json` output."
        )
        return RegisteredSkill(
            name=skill_name,
            detection_token=sentinel,
            detection_mode="heuristic",
            detection_details=details,
            cleanup_paths=cleanup_paths,
        )

    def unregister_skill(self, registration: RegisteredSkill) -> None:
        for path in registration.cleanup_paths:
            if path.is_file():
                path.unlink(missing_ok=True)
            elif path.exists():
                shutil.rmtree(path, ignore_errors=True)

    def run_query(self, query: str, timeout: int, model: str | None) -> QueryRunResult | None:
        """Run codex exec --json and return the last agent response text.

        Codex outputs JSONL: one JSON object per line. We collect all lines,
        find the last item.completed event with type agent_message, and return
        its text field.
        """
        cmd = [
            "codex", "exec",
            "--json",
            "--sandbox", "read-only",
            "--skip-git-repo-check",
        ]
        if model:
            cmd.extend(["--model", model])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                input=query,
                text=True,
                timeout=timeout,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

        if result.returncode != 0:
            print(f"Warning: codex exited with code {result.returncode}", file=sys.stderr)
            # Still try to parse output — codex can exit non-zero but produce useful output

        # Parse JSONL: collect all agent_message texts, return the last one
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
            return None

        return QueryRunResult(
            response_text=last_text,
            raw_output=result.stdout,
            metadata={"returncode": result.returncode},
        )
