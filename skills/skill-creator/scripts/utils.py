"""Shared utilities for skill-creator scripts."""

import ast
import json
import re
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)


def _coerce_frontmatter_value(raw_value: str):
    """Parse a simple scalar or inline collection from frontmatter."""
    value = raw_value.strip()
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() in {"null", "~"}:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    if value.startswith("{") or value.startswith("["):
        for loader in (json.loads, ast.literal_eval):
            try:
                return loader(value)
            except Exception:
                continue
    return value


def parse_top_level_yaml_text(text: str) -> dict:
    """Parse a lightweight top-level YAML-like mapping."""
    frontmatter: dict = {}
    lines = text.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if line.startswith((" ", "\t")):
            index += 1
            continue
        if ":" not in line:
            raise ValueError(f"Invalid frontmatter line: {line}")

        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()

        if value in {"|", ">", "|-", ">-"}:
            continuation: list[str] = []
            index += 1
            while index < len(lines) and lines[index].startswith((" ", "\t")):
                continuation.append(lines[index].strip())
                index += 1
            if value.startswith(">"):
                frontmatter[key] = " ".join(continuation).strip()
            else:
                frontmatter[key] = "\n".join(continuation).strip()
            continue

        if value == "":
            nested_lines: list[str] = []
            index += 1
            while index < len(lines) and lines[index].startswith((" ", "\t")):
                nested_lines.append(lines[index])
                index += 1
            frontmatter[key] = "\n".join(nested_lines).strip()
            continue

        frontmatter[key] = _coerce_frontmatter_value(value)
        index += 1

    return frontmatter


def load_skill_frontmatter(skill_path: Path) -> tuple[dict, str, str]:
    """Load SKILL.md frontmatter as a lightweight top-level mapping."""
    content = (skill_path / "SKILL.md").read_text()
    match = _FRONTMATTER_RE.match(content)
    if not match:
        raise ValueError("SKILL.md missing valid YAML frontmatter")

    frontmatter_text = match.group(1)
    frontmatter = parse_top_level_yaml_text(frontmatter_text)
    return frontmatter, frontmatter_text, content


def parse_skill_md(skill_path: Path) -> tuple[str, str, str]:
    """Parse a SKILL.md file, returning (name, description, full_content)."""
    frontmatter, _, content = load_skill_frontmatter(skill_path)
    name = frontmatter.get("name", "")
    description = frontmatter.get("description", "")

    if not isinstance(name, str):
        raise ValueError("SKILL.md frontmatter field 'name' must be a string")
    if not isinstance(description, str):
        raise ValueError("SKILL.md frontmatter field 'description' must be a string")

    return name.strip(), description.strip(), content
