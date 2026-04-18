"""Language analyzer registry. Import a language module to register it."""

from __future__ import annotations

# Import built-in analyzers for their registration side effects.
from pr_triage_prompt.analyzers import java, python, typescript  # noqa: F401
from pr_triage_prompt.analyzers.base import (
    FileChangeSummary,
    LanguageAnalyzer,
    analyze_with_repo,
    get_analyzer,
    register_analyzer,
    registered_analyzers,
)

__all__ = [
    "FileChangeSummary",
    "LanguageAnalyzer",
    "analyze_with_repo",
    "get_analyzer",
    "register_analyzer",
    "registered_analyzers",
]
