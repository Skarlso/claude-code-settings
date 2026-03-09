#!/usr/bin/env python3
"""Layered validation for portable skills and platform-specific overlays."""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from scripts.utils import load_skill_frontmatter, parse_top_level_yaml_text

_NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")


@dataclass
class ValidationReport:
    """Structured validation result."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        if self.valid and not self.warnings:
            return "Skill is valid."
        if self.valid:
            return f"Skill is valid with {len(self.warnings)} warning(s)."
        return f"Skill is invalid with {len(self.errors)} error(s)."


def _ensure_string_list(value, field_name: str, report: ValidationReport) -> None:
    """Validate that a field is a list[str]."""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        report.errors.append(f"{field_name} must be a list of strings.")


def _validate_core_frontmatter(frontmatter: dict, report: ValidationReport) -> None:
    """Validate universal skill fields."""
    if "name" not in frontmatter:
        report.errors.append("Missing 'name' in frontmatter.")
    if "description" not in frontmatter:
        report.errors.append("Missing 'description' in frontmatter.")

    name = frontmatter.get("name", "")
    if not isinstance(name, str):
        report.errors.append(f"Name must be a string, got {type(name).__name__}.")
    else:
        normalized = name.strip()
        if not normalized:
            report.errors.append("Name cannot be empty.")
        elif not _NAME_PATTERN.match(normalized):
            report.errors.append(
                f"Name '{normalized}' should be kebab-case (lowercase letters, digits, and hyphens only)."
            )
        elif normalized.startswith("-") or normalized.endswith("-") or "--" in normalized:
            report.errors.append(
                f"Name '{normalized}' cannot start/end with hyphen or contain consecutive hyphens."
            )
        elif len(normalized) > 64:
            report.errors.append(f"Name is too long ({len(normalized)} characters). Maximum is 64.")

    description = frontmatter.get("description", "")
    if not isinstance(description, str):
        report.errors.append(f"Description must be a string, got {type(description).__name__}.")
    else:
        normalized = description.strip()
        if not normalized:
            report.errors.append("Description cannot be empty.")
        if "<" in normalized or ">" in normalized:
            report.errors.append("Description cannot contain angle brackets (< or >).")
        if len(normalized) > 1024:
            report.errors.append(
                f"Description is too long ({len(normalized)} characters). Maximum is 1024."
            )
        elif len(normalized) > 200:
            report.warnings.append(
                "Description exceeds 200 characters. Claude Code currently recommends shorter descriptions."
            )


def _validate_optional_frontmatter(frontmatter: dict, report: ValidationReport) -> None:
    """Validate recognized optional fields and overlays."""
    if "compatibility" in frontmatter and not isinstance(frontmatter["compatibility"], str):
        report.errors.append(f"Compatibility must be a string, got {type(frontmatter['compatibility']).__name__}.")
    if "license" in frontmatter and not isinstance(frontmatter["license"], str):
        report.errors.append(f"License must be a string, got {type(frontmatter['license']).__name__}.")

    allowed_tools = frontmatter.get("allowed-tools")
    if allowed_tools is not None and not isinstance(allowed_tools, (str, list)):
        report.errors.append(
            f"allowed-tools must be a string or list, got {type(allowed_tools).__name__}."
        )
    elif allowed_tools is not None:
        report.warnings.append(
            "allowed-tools is runtime-specific. Do not rely on it as the universal compatibility baseline."
        )

    metadata = frontmatter.get("metadata")
    if metadata is not None and not isinstance(metadata, (dict, str)):
        report.errors.append(f"metadata must be a mapping-like value, got {type(metadata).__name__}.")
    elif isinstance(metadata, dict):
        for namespace, payload in metadata.items():
            if not isinstance(payload, dict):
                report.errors.append(f"metadata.{namespace} must be a mapping.")
                continue
            requires = payload.get("requires")
            if requires is not None and not isinstance(requires, dict):
                report.errors.append(f"metadata.{namespace}.requires must be a mapping.")
            elif isinstance(requires, dict):
                for key in ("bins", "anyBins", "env", "config"):
                    if key in requires:
                        _ensure_string_list(requires[key], f"metadata.{namespace}.requires.{key}", report)
            if "os" in payload and not isinstance(payload["os"], (str, list)):
                report.errors.append(f"metadata.{namespace}.os must be a string or list of strings.")
            if "primaryEnv" in payload and not isinstance(payload["primaryEnv"], str):
                report.errors.append(f"metadata.{namespace}.primaryEnv must be a string.")
    elif isinstance(metadata, str) and metadata:
        if "requires:" in metadata:
            for key in ("bins", "anyBins", "env", "config"):
                if f"{key}:" in metadata and "[" not in metadata and "-" not in metadata:
                    report.warnings.append(
                        f"metadata requires.{key} uses nested YAML that the lightweight validator cannot fully type-check."
                    )

    for boolean_field in ("user-invocable", "disable-model-invocation"):
        if boolean_field in frontmatter and not isinstance(frontmatter[boolean_field], bool):
            report.errors.append(f"{boolean_field} must be a boolean.")

    for string_field in ("homepage", "command-dispatch", "command-tool", "command-arg-mode", "agent", "model", "argument-hint", "context"):
        if string_field in frontmatter and not isinstance(frontmatter[string_field], str):
            report.errors.append(f"{string_field} must be a string.")


def _validate_codex_overlay(skill_path: Path, report: ValidationReport) -> None:
    """Validate Codex-specific overlay files when present."""
    codex_overlay = skill_path / "agents" / "openai.yaml"
    if not codex_overlay.exists():
        return

    try:
        overlay = parse_top_level_yaml_text(codex_overlay.read_text())
    except ValueError:
        text = codex_overlay.read_text()
        overlay = {}
        allow_match = re.search(r"^\s*allow_implicit_invocation:\s*(true|false)\s*$", text, re.MULTILINE)
        if allow_match:
            overlay["allow_implicit_invocation"] = allow_match.group(1) == "true"
        if "dependencies:" in text:
            overlay["dependencies"] = "raw"
        if "interface:" in text:
            overlay["interface"] = "raw"

    allow_implicit = overlay.get("allow_implicit_invocation")
    if allow_implicit is not None and not isinstance(allow_implicit, bool):
        report.errors.append("agents/openai.yaml field allow_implicit_invocation must be a boolean.")

    dependencies = overlay.get("dependencies")
    if dependencies is not None and not isinstance(dependencies, (dict, str)):
        report.errors.append("agents/openai.yaml field dependencies must be a mapping.")
    elif isinstance(dependencies, dict):
        tools = dependencies.get("tools")
        if tools is not None:
            _ensure_string_list(tools, "agents/openai.yaml dependencies.tools", report)
    elif dependencies == "raw":
        report.warnings.append(
            "agents/openai.yaml dependencies use nested YAML that the lightweight validator cannot fully type-check."
        )

    interface = overlay.get("interface")
    if interface is not None and not isinstance(interface, (dict, str)):
        report.errors.append("agents/openai.yaml field interface must be a mapping.")
    elif interface == "raw":
        report.warnings.append(
            "agents/openai.yaml interface uses nested YAML that the lightweight validator cannot fully type-check."
        )


def validate_skill(skill_path) -> ValidationReport:
    """Validate a skill's portable baseline plus known platform overlays."""
    skill_path = Path(skill_path)
    report = ValidationReport()

    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        report.errors.append("SKILL.md not found.")
        return report

    try:
        frontmatter, _, _ = load_skill_frontmatter(skill_path)
    except ValueError as exc:
        report.errors.append(str(exc))
        return report

    _validate_core_frontmatter(frontmatter, report)
    _validate_optional_frontmatter(frontmatter, report)
    _validate_codex_overlay(skill_path, report)

    if (skill_path / "resources").exists() and (skill_path / "references").exists():
        report.warnings.append(
            "Both resources/ and references/ exist. Keep one canonical layout unless you intentionally mirror for cross-platform compatibility."
        )

    return report


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.quick_validate <skill_directory>")
        sys.exit(1)

    report = validate_skill(sys.argv[1])
    print(report.summary())
    for error in report.errors:
        print(f"ERROR: {error}")
    for warning in report.warnings:
        print(f"WARNING: {warning}")
    sys.exit(0 if report.valid else 1)


if __name__ == "__main__":
    main()
