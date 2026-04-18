"""Config loader. Env > CLI flag > ~/.pr-triage/config.toml > defaults."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


DEFAULT_CONFIG_PATH = Path.home() / ".pr-triage" / "config.toml"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "pr-triage"
DEFAULT_TOKEN_BUDGET = 4000


@dataclass
class Config:
    github_token_env: str = "GITHUB_TOKEN"
    jira_base_url: str | None = None
    jira_token_env: str = "JIRA_TOKEN"
    jira_username: str | None = None
    cache_dir: Path = field(default_factory=lambda: DEFAULT_CACHE_DIR)
    default_token_budget: int = DEFAULT_TOKEN_BUDGET
    clone_url_template: str | None = None
    """Git URL template for sparse checkout. `{repo}` is substituted with the PR's
    `<owner>/<repo>` slug. No built-in default — cloning is skipped unless this is set."""

    def resolved_clone_url(self, repo: str) -> str | None:
        if not self.clone_url_template:
            return None
        return self.clone_url_template.format(repo=repo)

    def resolved_cache_dir(self) -> Path:
        return Path(os.path.expanduser(str(self.cache_dir))).resolve()

    def github_token(self) -> str | None:
        return os.environ.get(self.github_token_env)

    def jira_token(self) -> str | None:
        return os.environ.get(self.jira_token_env)


def load_config(path: Path | None = None) -> Config:
    """Load `~/.pr-triage/config.toml` (or `path`); return defaults if absent."""
    cfg_path = path or DEFAULT_CONFIG_PATH
    if not cfg_path.is_file():
        return Config()
    try:
        data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return Config()

    cfg = Config()
    if isinstance(data.get("github_token_env"), str):
        cfg.github_token_env = data["github_token_env"]
    if isinstance(data.get("jira_base_url"), str):
        cfg.jira_base_url = data["jira_base_url"]
    if isinstance(data.get("jira_token_env"), str):
        cfg.jira_token_env = data["jira_token_env"]
    if isinstance(data.get("jira_username"), str):
        cfg.jira_username = data["jira_username"]
    if isinstance(data.get("cache_dir"), str):
        cfg.cache_dir = Path(data["cache_dir"]).expanduser()
    if isinstance(data.get("default_token_budget"), int):
        cfg.default_token_budget = data["default_token_budget"]
    if isinstance(data.get("clone_url_template"), str):
        cfg.clone_url_template = data["clone_url_template"]
    return cfg


def redact(text: str, *tokens: str | None) -> str:
    """Strip any non-empty token value from the given text."""
    out = text
    for t in tokens:
        if t:
            out = out.replace(t, "***")
    return out
