"""Centralized logging helpers for the CLI.

All output goes to stderr; the report table on stdout is the only thing on stdout.
Respects:
- `NO_COLOR` env var (disables color regardless of TTY state)
- `--no-color` flag via `set_color(False)`
- `--quiet` / `-q` via `set_quiet(True)` — suppresses `info`, `progress`, `phase`
- `--verbose` / `-v` via `set_verbose(True)` — enables the `verbose` helper
"""

from __future__ import annotations

import os
import sys

_COLOR_ENABLED: bool = sys.stderr.isatty() and "NO_COLOR" not in os.environ
_QUIET: bool = False
_VERBOSE: bool = False

# ANSI color codes.
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_RED = "\033[31m"


def set_color(enabled: bool) -> None:
    global _COLOR_ENABLED
    _COLOR_ENABLED = enabled and sys.stderr.isatty() and "NO_COLOR" not in os.environ


def set_quiet(enabled: bool) -> None:
    global _QUIET
    _QUIET = enabled


def set_verbose(enabled: bool) -> None:
    global _VERBOSE
    _VERBOSE = enabled


def is_verbose() -> bool:
    return _VERBOSE


def _paint(text: str, code: str) -> str:
    if not _COLOR_ENABLED:
        return text
    return f"{code}{text}{_RESET}"


def _emit(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def info(msg: str) -> None:
    """Neutral informational line (e.g. startup banner). Suppressed by --quiet."""
    if _QUIET:
        return
    _emit(msg)


def note(msg: str) -> None:
    """Background note — one-off, informational, not a problem. Always shown."""
    _emit(_paint(f"note: {msg}", _DIM))


def warn(msg: str) -> None:
    """Recoverable problem; execution continues. Always shown."""
    _emit(_paint(f"warn: {msg}", _YELLOW + _BOLD))


def error(msg: str) -> None:
    """Unrecoverable. Caller is expected to exit non-zero. Always shown."""
    _emit(_paint(f"error: {msg}", _RED + _BOLD))


def progress(msg: str) -> None:
    """Per-step progress. Suppressed by --quiet."""
    if _QUIET:
        return
    _emit(_paint(f"→ {msg}", _CYAN))


def phase(label: str, msg: str) -> None:
    """Indented sub-line under a progress header. Suppressed by --quiet.

    Renders as ``    <label:10>  <msg>``. ``label`` is expected to be short
    (checkout, jira, wrote, analyzer, …).
    """
    if _QUIET:
        return
    padded = f"{label:<9}"
    _emit("    " + _paint(padded, _DIM) + "  " + msg)


def verbose(msg: str) -> None:
    """Extra detail for --verbose. Unlike the others, honors stderr TTY state for color too."""
    if not _VERBOSE or _QUIET:
        return
    _emit("    " + _paint(f"· {msg}", _DIM))
