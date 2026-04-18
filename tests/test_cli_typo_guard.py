"""The main() entry strips `pr-triage pr-triage ...` duplication with a stderr note."""

from __future__ import annotations

import sys

from pr_triage_prompt.cli import _strip_duplicate_program_name


def test_strip_duplicate_warns(capsys) -> None:
    cleaned = _strip_duplicate_program_name(["prog", "pr-triage", "--version"])
    assert cleaned == ["prog", "--version"]
    captured = capsys.readouterr()
    assert "ignoring duplicated 'pr-triage'" in captured.err


def test_no_warn_when_no_duplicate(capsys) -> None:
    cleaned = _strip_duplicate_program_name(["prog", "--version"])
    assert cleaned == ["prog", "--version"]
    captured = capsys.readouterr()
    assert captured.err == ""


def test_no_warn_when_first_token_is_subcommand(capsys) -> None:
    cleaned = _strip_duplicate_program_name(["prog", "batch", "ctx", "--out-dir", "x"])
    assert cleaned == ["prog", "batch", "ctx", "--out-dir", "x"]
    captured = capsys.readouterr()
    assert captured.err == ""


def test_version_runs_after_stripping_duplicate(tmp_path, capfd) -> None:
    """Full integration: simulate argv with the duplicated token, call main(), assert --version works."""
    import subprocess

    res = subprocess.run(
        [sys.executable, "-m", "pr_triage_prompt.cli", "pr-triage", "--version"],
        capture_output=True, text=True, check=False,
    )
    assert res.returncode == 0, res.stderr
    assert "pr-triage 0." in res.stdout
    assert "ignoring duplicated 'pr-triage'" in res.stderr
