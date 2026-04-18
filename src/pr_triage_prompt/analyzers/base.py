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

    def analyze_file(
        self, file_path: Path, patch: str, status: str, repo_root: Path
    ) -> FileChangeSummary:
        """Richer analysis using the checked-out source.

        Default implementation falls back to patch-only `analyze`; language analyzers
        override to pick up symbols that live outside the visible patch hunks (e.g. a
        method modified in its body whose declaration is earlier in the file).
        """
        ...


def analyze_with_repo(
    analyzer: LanguageAnalyzer,
    file_path: Path,
    patch: str,
    status: str,
    repo_root: Path | None,
) -> FileChangeSummary:
    """Dispatch helper: use the full-file path when we have the checkout, else patch-only."""
    if repo_root is not None and hasattr(analyzer, "analyze_file"):
        try:
            return analyzer.analyze_file(file_path, patch, status, repo_root)
        except FileNotFoundError:
            # File may be missing from sparse checkout — fall back.
            pass
    return analyzer.analyze(file_path, patch, status)


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
