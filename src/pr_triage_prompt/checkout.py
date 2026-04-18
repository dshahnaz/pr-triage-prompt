"""Sparse git clone/checkout cache, keyed by (repo, sha)."""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class CacheEntry:
    repo: str
    sha: str
    path: Path
    size_bytes: int


PhaseCallback = Callable[[str, str], None]


def _slug(repo: str) -> str:
    return repo.replace("/", "__")


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    # Never block waiting for an interactive credential prompt — fail fast instead.
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _auth_config_args(clone_url: str, token: str | None) -> list[str]:
    """Return ``["-c", "http.<scheme>://<host>/.extraheader=Authorization: Bearer <token>"]``
    for HTTPS remotes when a token is supplied. SSH / file-scheme URLs get no args."""
    if not token:
        return []
    parsed = urlparse(clone_url)
    if parsed.scheme not in ("http", "https"):
        return []
    if not parsed.hostname:
        return []
    base = f"{parsed.scheme}://{parsed.hostname}/"
    return ["-c", f"http.{base}.extraheader=Authorization: Bearer {token}"]


def _redact_cmd(cmd: list[str]) -> list[str]:
    """Replace the token in a git -c http.extraheader=… argument with '***' for logging."""
    out: list[str] = []
    for arg in cmd:
        if "extraheader=Authorization: Bearer " in arg:
            prefix = arg.split("Bearer ", 1)[0]
            out.append(prefix + "Bearer ***")
        else:
            out.append(arg)
    return out


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True, env=_git_env())


def _dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            with contextlib.suppress(OSError):
                total += p.stat().st_size
    return total


def _sparse_patterns(paths: Iterable[str]) -> list[str]:
    """Build sparse-checkout patterns: each file path + every parent directory."""
    patterns: set[str] = set()
    for p in paths:
        parts = p.split("/")
        patterns.add(p)
        for i in range(1, len(parts)):
            patterns.add("/".join(parts[:i]) + "/")
    return sorted(patterns)


def cache_dir_for(cache_root: Path, repo: str, sha: str) -> Path:
    return cache_root / _slug(repo) / sha


def ensure_checkout(
    *,
    cache_root: Path,
    repo: str,
    sha: str,
    clone_url: str,
    paths: list[str],
    no_cache: bool = False,
    git_token: str | None = None,
    on_phase: PhaseCallback | None = None,
    verbose_cmd: Callable[[list[str]], None] | None = None,
) -> Path:
    """Return a path to a sparse checkout of ``repo@sha`` that contains ``paths``.

    Phases are reported via ``on_phase(event, message)`` with ``event`` in
    ``{"start", "sparse", "checkout", "done", "cache-hit"}``. ``verbose_cmd``, when
    provided, is called with each git command (auth-redacted) before it runs.
    """

    def _notify(event: str, message: str) -> None:
        if on_phase is not None:
            on_phase(event, message)

    def _run_git(args: list[str], cwd: Path | None = None) -> None:
        if verbose_cmd is not None:
            verbose_cmd(_redact_cmd(["git", *args]))
        _run(["git", *args], cwd=cwd)

    target = cache_dir_for(cache_root, repo, sha)
    if no_cache and target.exists():
        shutil.rmtree(target)

    auth = _auth_config_args(clone_url, git_token)

    if target.exists():
        size_mb = _dir_size(target) / (1024 * 1024)
        _notify("cache-hit", f"cache hit ({size_mb:.1f} MB)")
        return target

    start = time.perf_counter()
    target.parent.mkdir(parents=True, exist_ok=True)
    _notify(
        "start",
        f"cloning {repo}@{sha[:12]} into {_display_path(target)}",
    )
    _run_git(
        [
            *auth,
            "clone",
            "--filter=blob:none",
            "--sparse",
            "--no-checkout",
            clone_url,
            str(target),
        ]
    )
    _run_git(["sparse-checkout", "init", "--no-cone"], cwd=target)

    patterns = _sparse_patterns(paths)
    _notify("sparse", f"sparse-setting {len(patterns)} pattern{'s' if len(patterns) != 1 else ''}")
    _run_git(["sparse-checkout", "set", "--no-cone", *patterns], cwd=target)

    _notify("checkout", f"checking out {sha[:12]}")
    _run_git([*auth, "checkout", sha], cwd=target)

    elapsed = time.perf_counter() - start
    size_mb = _dir_size(target) / (1024 * 1024)
    _notify("done", f"ok ({size_mb:.1f} MB, {elapsed:.1f}s)")
    return target


def _display_path(path: Path) -> str:
    home = str(Path.home())
    s = str(path)
    if s.startswith(home):
        return "~" + s[len(home):]
    return s


def list_cache(cache_root: Path) -> list[CacheEntry]:
    entries: list[CacheEntry] = []
    if not cache_root.exists():
        return entries
    for repo_dir in sorted(cache_root.iterdir()):
        if not repo_dir.is_dir():
            continue
        repo = repo_dir.name.replace("__", "/")
        for sha_dir in sorted(repo_dir.iterdir()):
            if not sha_dir.is_dir():
                continue
            entries.append(
                CacheEntry(
                    repo=repo,
                    sha=sha_dir.name,
                    path=sha_dir,
                    size_bytes=_dir_size(sha_dir),
                )
            )
    return entries


def clear_cache(cache_root: Path) -> None:
    if cache_root.exists():
        shutil.rmtree(cache_root)
