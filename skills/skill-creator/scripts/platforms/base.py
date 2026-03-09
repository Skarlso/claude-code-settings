"""Abstract base classes for platform adapters used in trigger evaluation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RegisteredSkill:
    """A temporary skill registered for one trigger-eval run."""

    name: str
    detection_token: str
    detection_mode: str
    detection_details: str
    cleanup_paths: list[Path] = field(default_factory=list)


@dataclass
class QueryRunResult:
    """Structured result from a platform query execution."""

    response_text: str
    raw_output: str
    metadata: dict[str, Any] = field(default_factory=dict)


class PlatformAdapter(ABC):
    """Defines the interface for running trigger evaluations on a specific platform."""

    @abstractmethod
    def find_project_root(self) -> Path:
        """Return the platform's project root directory."""
        ...

    @abstractmethod
    def register_skill(self, skill_name: str, description: str, sentinel: str) -> RegisteredSkill:
        """Register a temporary skill for testing."""
        ...

    def unregister_skill(self, registration: RegisteredSkill) -> None:
        """Remove any paths created by register_skill()."""
        for path in sorted(registration.cleanup_paths, key=lambda item: len(item.parts), reverse=True):
            if path.is_file():
                path.unlink(missing_ok=True)
                continue
            if path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    # Ignore non-empty directories created outside this run.
                    pass

    @abstractmethod
    def run_query(self, query: str, timeout: int, model: str | None) -> QueryRunResult | None:
        """Run a query and return the structured execution result.

        Returns None on failure or timeout.
        """
        ...

    def detect_trigger(self, run_result: QueryRunResult, registration: RegisteredSkill) -> bool:
        """Return True if the skill was triggered.

        The default implementation is a heuristic that checks for a sentinel string
        in the assistant's response text.
        """
        return registration.detection_token in run_result.response_text
