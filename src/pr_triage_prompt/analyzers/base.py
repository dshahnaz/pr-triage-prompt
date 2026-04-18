"""Analyzer Protocol + registry."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from pr_triage_prompt.models import FileChangeSummary

_REGISTRY: dict[str, LanguageAnalyzer] = {}


@runtime_checkable
class LanguageAnalyzer(Protocol):
    """Contract for a language analyzer.

    Implementations should be idempotent and safe to call without file-system access.
    """

    extensions: tuple[str, ...]
    language: str

    def analyze(self, file_path: Path, patch: str, status: str) -> FileChangeSummary: ...


def register_analyzer(cls: type) -> type:
    """Class decorator: instantiate and register under each declared extension."""
    instance = cls()
    for ext in instance.extensions:
        _REGISTRY[ext.lower()] = instance
    return cls


def get_analyzer(filename: str) -> LanguageAnalyzer | None:
    ext = Path(filename).suffix.lower()
    return _REGISTRY.get(ext)


def registered_analyzers() -> dict[str, LanguageAnalyzer]:
    return dict(_REGISTRY)


def collect_excerpt(added_lines: list[str], max_lines: int = 5) -> str:
    """Pick a short representative excerpt from added lines for the prompt."""
    picked: list[str] = []
    for line in added_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "#", "/*", "*", "<!--")):
            continue
        picked.append(line.rstrip())
        if len(picked) >= max_lines:
            break
    return "\n".join(picked)
