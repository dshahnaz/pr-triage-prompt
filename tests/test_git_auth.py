"""Git token selection + header injection for HTTPS clones."""

from __future__ import annotations

from pr_triage_prompt.checkout import _auth_config_args, _redact_cmd
from pr_triage_prompt.config import Config


def test_git_token_for_github_uses_github_token_env(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "gh-secret")
    cfg = Config()
    assert cfg.git_token_for("https://github.com/a/b.git") == "gh-secret"


def test_git_token_for_other_host_uses_git_token_env(monkeypatch) -> None:
    monkeypatch.setenv("GHE_TOKEN", "ghe-secret")
    cfg = Config(git_token_env="GHE_TOKEN")
    assert cfg.git_token_for("https://git.example.com/a/b.git") == "ghe-secret"


def test_git_token_for_other_host_without_env_is_none() -> None:
    cfg = Config()
    assert cfg.git_token_for("https://git.example.com/a/b.git") is None


def test_ssh_url_never_gets_token(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "gh-secret")
    cfg = Config()
    assert cfg.git_token_for("git@github.com:a/b.git") is None
    assert cfg.git_token_for("ssh://git@github.com/a/b.git") is None


def test_auth_config_args_skips_ssh_and_empty_token() -> None:
    assert _auth_config_args("git@github.com:a/b.git", "tok") == []
    assert _auth_config_args("https://github.com/a/b.git", None) == []


def test_auth_config_args_injects_header_for_https() -> None:
    args = _auth_config_args("https://github.com/a/b.git", "tok123")
    assert args[0] == "-c"
    assert "http.https://github.com/.extraheader=Authorization: Bearer tok123" in args[1]


def test_redact_masks_bearer_token() -> None:
    cmd = [
        "git",
        "-c",
        "http.https://github.com/.extraheader=Authorization: Bearer supersecret",
        "clone",
        "https://github.com/a/b.git",
    ]
    out = _redact_cmd(cmd)
    assert "supersecret" not in " ".join(out)
    assert "Bearer ***" in " ".join(out)
