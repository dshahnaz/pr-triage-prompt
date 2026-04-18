from pathlib import Path

from pr_triage_prompt.config import DEFAULT_TOKEN_BUDGET, Config, load_config, redact


def test_defaults_when_file_missing(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "does-not-exist.toml")
    assert cfg.github_token_env == "GITHUB_TOKEN"
    assert cfg.default_token_budget == DEFAULT_TOKEN_BUDGET


def test_load_overrides(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text(
        'github_token_env = "GH_PAT"\n'
        'jira_base_url = "https://j.example"\n'
        'jira_token_env = "J_TOK"\n'
        'jira_username = "me@example.com"\n'
        'cache_dir = "/tmp/pr-triage"\n'
        "default_token_budget = 2000\n",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.github_token_env == "GH_PAT"
    assert cfg.jira_base_url == "https://j.example"
    assert cfg.jira_username == "me@example.com"
    assert cfg.cache_dir == Path("/tmp/pr-triage")
    assert cfg.default_token_budget == 2000


def test_redact_scrubs_tokens() -> None:
    out = redact("Authorization: Bearer abcd1234", "abcd1234")
    assert "abcd1234" not in out
    assert "***" in out


def test_config_github_token_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "secret-gh")
    cfg = Config()
    assert cfg.github_token() == "secret-gh"
