"""PR → Markdown prompt generator for test-suite-bound LLM agents."""

from pr_triage_prompt.models import (
    FileChangeSummary,
    JiraTicket,
    ModuleSummary,
    PromptBundle,
    PullRequest,
)

__version__ = "0.4.0"


def __getattr__(name: str):  # pragma: no cover - trivial
    if name == "build_prompt":
        from pr_triage_prompt.prompt import build_prompt

        return build_prompt
    raise AttributeError(f"module 'pr_triage_prompt' has no attribute {name!r}")


__all__ = [
    "FileChangeSummary",
    "JiraTicket",
    "ModuleSummary",
    "PromptBundle",
    "PullRequest",
    "__version__",
    "build_prompt",
]
