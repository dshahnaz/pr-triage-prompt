"""Log module behavior: TTY detection, NO_COLOR, quiet/verbose levels."""

from __future__ import annotations

import re

from pr_triage_prompt import log

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _no_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def _reset_state() -> None:
    log.set_quiet(False)
    log.set_verbose(False)
    log.set_color(False)  # tests run non-TTY anyway


def test_warn_always_shown_even_in_quiet(capsys) -> None:
    _reset_state()
    log.set_quiet(True)
    log.warn("something is odd")
    captured = capsys.readouterr()
    assert "warn: something is odd" in _no_ansi(captured.err)


def test_progress_suppressed_by_quiet(capsys) -> None:
    _reset_state()
    log.set_quiet(True)
    log.progress("working on it")
    log.phase("checkout", "cloning")
    log.info("startup")
    captured = capsys.readouterr()
    assert captured.err == ""


def test_phase_indent_and_label_alignment(capsys) -> None:
    _reset_state()
    log.phase("checkout", "cloning repo")
    log.phase("jira", "matched by key")
    captured = _no_ansi(capsys.readouterr().err)
    # Both lines start with 4 spaces, then a 9-char padded label, then "  " separator.
    lines = captured.splitlines()
    assert lines[0].startswith("    checkout  "), lines[0]
    assert lines[1].startswith("    jira       "), lines[1]


def test_verbose_off_by_default(capsys) -> None:
    _reset_state()
    log.verbose("deep detail")
    assert capsys.readouterr().err == ""


def test_verbose_shown_when_enabled(capsys) -> None:
    _reset_state()
    log.set_verbose(True)
    log.verbose("deep detail")
    assert "deep detail" in capsys.readouterr().err


def test_error_always_shown(capsys) -> None:
    _reset_state()
    log.set_quiet(True)
    log.error("boom")
    assert "error: boom" in _no_ansi(capsys.readouterr().err)


def test_everything_writes_to_stderr(capsys) -> None:
    _reset_state()
    log.info("hello")
    log.note("fyi")
    log.warn("careful")
    log.error("broken")
    log.progress("going")
    log.phase("p", "q")
    captured = capsys.readouterr()
    assert captured.out == ""


def test_no_color_env_disables_color(monkeypatch, capsys) -> None:
    _reset_state()
    monkeypatch.setenv("NO_COLOR", "1")
    # set_color honors NO_COLOR even when asked to enable.
    log.set_color(True)
    log.warn("hey")
    err = capsys.readouterr().err
    assert "\x1b[" not in err
