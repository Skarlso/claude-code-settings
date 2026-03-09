"""OpenClaw platform adapter for skill trigger evaluation.

Registers temporary skills under ~/.openclaw/skills/ and detects triggering via
a sentinel phrase embedded in the skill body. OpenClaw's JSON output exposes
which skills were available to the model, but not whether the full skill body
was consulted, so trigger detection remains heuristic.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.platforms.base import PlatformAdapter, QueryRunResult, RegisteredSkill

# Skills are installed globally so all agents can see them during testing.
_OPENCLAW_SKILLS_DIR = Path.home() / ".openclaw" / "skills"


class OpenClawAdapter(PlatformAdapter):
    """Adapter for OpenClaw (openclaw CLI)."""

    def __init__(self, agent_id: str = "main"):
        self._agent_id = agent_id

    def find_project_root(self) -> Path:
        return Path.home() / ".openclaw"

    def register_skill(self, skill_name: str, description: str, sentinel: str) -> RegisteredSkill:
        """Write a temporary skill folder into ~/.openclaw/skills/.

        The skill body instructs the agent to include the sentinel phrase if it
        activates this skill — this is how we detect triggering without stream events.
        """
        skill_dir = _OPENCLAW_SKILLS_DIR / skill_name
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
        return RegisteredSkill(
            name=skill_name,
            detection_token=sentinel,
            detection_mode="heuristic",
            detection_details=(
                "Heuristic response-sentinel detection. OpenClaw exposes available "
                "skill summaries in `systemPromptReport`, but not authoritative "
                "skill-load events for the full SKILL.md body."
            ),
            cleanup_paths=[skill_md, skill_dir],
        )

    def unregister_skill(self, registration: RegisteredSkill) -> None:
        for path in registration.cleanup_paths:
            if path.is_file():
                path.unlink(missing_ok=True)
            elif path.exists():
                shutil.rmtree(path, ignore_errors=True)

    def run_query(self, query: str, timeout: int, model: str | None) -> QueryRunResult | None:
        """Run openclaw agent --local and return response text, or None on failure."""
        cmd = [
            "openclaw", "agent",
            "--local",
            "--agent", self._agent_id,
            "--message", query,
            "--json",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

        if result.returncode != 0:
            print(f"Warning: openclaw exited with code {result.returncode}", file=sys.stderr)
            return None

        try:
            data = json.loads(result.stdout)
            payloads = data.get("payloads", [])
            response_text = payloads[0].get("text", "") if payloads else ""
            entries = (
                data.get("meta", {})
                .get("systemPromptReport", {})
                .get("skills", {})
                .get("entries", [])
            )
            available_skill_names = [entry.get("name", "") for entry in entries if entry.get("name")]
            return QueryRunResult(
                response_text=response_text,
                raw_output=result.stdout,
                metadata={"available_skill_names": available_skill_names},
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def detect_trigger(self, run_result: QueryRunResult, registration: RegisteredSkill) -> bool:
        available_skill_names = set(run_result.metadata.get("available_skill_names", []))
        if registration.name not in available_skill_names:
            return False
        return registration.detection_token in run_result.response_text
