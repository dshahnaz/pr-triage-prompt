"""Pydantic models for the pr-triage-prompt input/output contract."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FileChange(BaseModel):
    """One file entry as emitted by GitHub's `.../pulls/{n}/files` endpoint."""

    model_config = ConfigDict(extra="ignore")

    filename: str
    status: str = "modified"
    additions: int = 0
    deletions: int = 0
    patch: str = ""


class PullRequest(BaseModel):
    """Normalized PR payload. Matches the shape of `examples/pr_23861.json`."""

    model_config = ConfigDict(extra="ignore")

    number: int
    sha: str
    repo: str
    title: str
    body: str = ""
    jira_id: str | None = None
    files: list[FileChange] = Field(default_factory=list)


class JiraTicket(BaseModel):
    """Jira ticket — every field optional, because tenants differ and fixtures may be empty."""

    model_config = ConfigDict(extra="ignore")

    key: str | None = None
    summary: str | None = None
    description: str | None = None
    issuetype: str | None = None
    status: str | None = None
    components: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)

    @property
    def has_content(self) -> bool:
        return bool(self.summary or self.description or self.issuetype or self.status)


class FileChangeSummary(BaseModel):
    """What an analyzer returns for a single changed file."""

    model_config = ConfigDict(extra="ignore")

    path: str
    language: str
    status: str
    additions: int
    deletions: int
    classes_changed: list[str] = Field(default_factory=list)
    functions_changed: list[str] = Field(default_factory=list)
    excerpt: str = ""
    module_path: str | None = None
    module_name: str | None = None


class ModuleSummary(BaseModel):
    """Aggregate of file changes grouped under one build-descriptor module."""

    model_config = ConfigDict(extra="ignore")

    module_name: str
    module_path: str
    language: str
    files: list[FileChangeSummary] = Field(default_factory=list)

    @property
    def additions(self) -> int:
        return sum(f.additions for f in self.files)

    @property
    def deletions(self) -> int:
        return sum(f.deletions for f in self.files)

    @property
    def classes_changed(self) -> list[str]:
        seen: dict[str, None] = {}
        for f in self.files:
            for c in f.classes_changed:
                seen.setdefault(c, None)
        return list(seen)

    @property
    def functions_changed(self) -> list[str]:
        seen: dict[str, None] = {}
        for f in self.files:
            for fn in f.functions_changed:
                seen.setdefault(fn, None)
        return list(seen)


class PromptBundle(BaseModel):
    """Result of building a prompt. `markdown` is the pasteable artifact."""

    model_config = ConfigDict(extra="ignore")

    markdown: str
    modules: list[ModuleSummary] = Field(default_factory=list)
    files: list[FileChangeSummary] = Field(default_factory=list)
    dropped_modules: list[str] = Field(default_factory=list)
    token_count: int = 0
    token_budget: int = 0

    @property
    def json_payload(self) -> dict[str, Any]:
        return {
            "modules": [m.model_dump() for m in self.modules],
            "files": [f.model_dump() for f in self.files],
            "dropped_modules": list(self.dropped_modules),
            "token_count": self.token_count,
            "token_budget": self.token_budget,
        }
