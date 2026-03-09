"""Claude Code platform adapter for skill trigger evaluation.

Registers temporary skills under .claude/skills/ and detects triggering via
the claude -p stream-json output (Skill/Read tool call inspection).
"""

import json
import os
import select
import subprocess
import time
from pathlib import Path

from scripts.platforms.base import PlatformAdapter, QueryRunResult, RegisteredSkill


class ClaudeCodeAdapter(PlatformAdapter):
    """Adapter for Claude Code (claude CLI)."""

    def __init__(self, model: str | None = None):
        self._model = model

    def find_project_root(self) -> Path:
        """Find the project root by walking up from cwd looking for .claude/."""
        current = Path.cwd()
        for parent in [current, *current.parents]:
            if (parent / ".claude").is_dir():
                return parent
        return current

    def register_skill(self, skill_name: str, description: str, sentinel: str) -> RegisteredSkill:
        """Write a temporary skill folder into .claude/skills/."""
        project_root = self.find_project_root()
        skill_dir = project_root / ".claude" / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_md = skill_dir / "SKILL.md"
        indented_desc = "\n  ".join(description.split("\n"))
        skill_md.write_text(
            f"---\n"
            f"name: {skill_name}\n"
            f"description: |\n"
            f"  {indented_desc}\n"
            f"---\n\n"
            f"# {skill_name}\n\n"
            f"This skill handles: {description}\n"
        )
        return RegisteredSkill(
            name=skill_name,
            detection_token=skill_name,
            detection_mode="authoritative",
            detection_details="Parsed Claude Code Skill/Read tool events from stream-json output.",
            cleanup_paths=[skill_md, skill_dir],
        )

    def run_query(self, query: str, timeout: int, model: str | None) -> QueryRunResult | None:
        """Run claude -p and return raw stdout, or None on failure."""
        cmd = [
            "claude",
            "-p", query,
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
        ]
        used_model = model or self._model
        if used_model:
            cmd.extend(["--model", used_model])

        # Remove CLAUDECODE env var to allow nesting claude -p inside a
        # Claude Code session.
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=str(self.find_project_root()),
                env=env,
            )
        except FileNotFoundError:
            return None

        output_lines: list[str] = []
        start_time = time.time()
        buffer = ""

        try:
            while time.time() - start_time < timeout:
                if process.poll() is not None:
                    remaining = process.stdout.read()
                    if remaining:
                        buffer += remaining.decode("utf-8", errors="replace")
                    break
                ready, _, _ = select.select([process.stdout], [], [], 1.0)
                if not ready:
                    continue
                chunk = os.read(process.stdout.fileno(), 8192)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    output_lines.append(line.strip())
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

        raw_output = "\n".join(output_lines)
        return QueryRunResult(response_text=raw_output, raw_output=raw_output)

    def detect_trigger(self, run_result: QueryRunResult, registration: RegisteredSkill) -> bool:
        """Parse Claude's stream-json output for Skill/Read tool calls referencing the temp skill."""
        token = registration.detection_token
        pending_tool_name: str | None = None
        accumulated_json = ""

        for line in run_result.raw_output.splitlines():
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event.get("type") == "stream_event":
                se = event.get("event", {})
                se_type = se.get("type", "")

                if se_type == "content_block_start":
                    cb = se.get("content_block", {})
                    if cb.get("type") == "tool_use":
                        tool_name = cb.get("name", "")
                        if tool_name in ("Skill", "Read"):
                            pending_tool_name = tool_name
                            accumulated_json = ""
                        continue

                elif se_type == "content_block_delta" and pending_tool_name:
                    delta = se.get("delta", {})
                    if delta.get("type") == "input_json_delta":
                        accumulated_json += delta.get("partial_json", "")
                        if token in accumulated_json:
                            return True

                elif se_type in ("content_block_stop", "message_stop"):
                    if pending_tool_name and token in accumulated_json:
                        return True
                    pending_tool_name = None
                    accumulated_json = ""
                    continue

            elif event.get("type") == "assistant":
                message = event.get("message", {})
                for content_item in message.get("content", []):
                    if content_item.get("type") != "tool_use":
                        continue
                    tool_name = content_item.get("name", "")
                    tool_input = content_item.get("input", {})
                    if tool_name == "Skill" and token in tool_input.get("skill", ""):
                        return True
                    if tool_name == "Read" and token in tool_input.get("file_path", ""):
                        return True

            elif event.get("type") == "result":
                continue

        return False
