"""One clone per repo; switch sparse checkout + SHA per PR.

Cache layout (v0.6+):

    ~/.cache/pr-triage/
        <repo-slug>/           # single clone per repo (partial, blob:none)
            .git/              # partial-clone git dir
            <sparse files>     # working tree for the currently-checked-out PR

Legacy layout (v0.5 and earlier) had ``<repo-slug>/<sha>/`` per-SHA directories.
On first v0.6 run we auto-clean those because they're obsolete.
"""

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
    last_sha: str | None
    path: Path
    size_bytes: int


PhaseCallback = Callable[[str, str], None]


def _slug(repo: str) -> str:
    return repo.replace("/", "__")


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _auth_config_args(clone_url: str, token: str | None) -> list[str]:
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
    out: list[str] = []
    for arg in cmd:
        if "extraheader=Authorization: Bearer " in arg:
            prefix = arg.split("Bearer ", 1)[0]
            out.append(prefix + "Bearer ***")
        else:
            out.append(arg)
    return out


def _run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=cwd, check=check, capture_output=True, text=True, env=_git_env()
    )


def _dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            with contextlib.suppress(OSError):
                total += p.stat().st_size
    return total


def _sparse_patterns(paths: Iterable[str]) -> list[str]:
    """Exact file paths only. Non-cone sparse-checkout treats bare patterns as gitignore-style;
    listing files directly includes only those files and the ancestor directory entries
    git needs to materialize them. No parent-dir globs — those would pull everything under.
    """
    return sorted({p for p in paths if p})


def cache_dir_for(cache_root: Path, repo: str) -> Path:
    """Path to the single per-repo clone."""
    return cache_root / _slug(repo)


def _is_legacy_sha_dir(p: Path) -> bool:
    """A legacy v0.5 per-SHA dir is a subdir with hex name that looks like a git worktree."""
    if not p.is_dir():
        return False
    name = p.name
    if not (len(name) >= 7 and all(c in "0123456789abcdef" for c in name)):
        return False
    return (p / ".git").exists()


def _cleanup_legacy(cache_root: Path, repo_slug: str) -> list[str]:
    """Remove any pre-0.6 ``<slug>/<sha>/`` directories; return the names we deleted."""
    repo_dir = cache_root / repo_slug
    if not repo_dir.is_dir():
        return []
    # If the repo_dir already looks like a clone (has .git), legacy dirs shouldn't exist here.
    # We only clean up when there's no top-level .git AND children look like legacy per-SHA dirs.
    if (repo_dir / ".git").exists():
        return []
    removed: list[str] = []
    for child in list(repo_dir.iterdir()):
        if _is_legacy_sha_dir(child):
            shutil.rmtree(child, ignore_errors=True)
            removed.append(child.name)
    # If the repo_dir is now empty, remove it too so we can clone cleanly.
    with contextlib.suppress(OSError):
        if not any(repo_dir.iterdir()):
            repo_dir.rmdir()
    return removed


def _sha_exists_locally(repo_dir: Path, sha: str) -> bool:
    proc = _run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=repo_dir, check=False)
    return proc.returncode == 0


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
    """Return a path to a sparse checkout of ``repo@sha``.

    One clone per repo is maintained under ``cache_root/<slug>``. Subsequent PRs on
    the same repo switch SHA in place (fetch if missing, re-set sparse patterns,
    checkout). SHAs are stored in the clone's object store so repeated switches are
    fast.
    """

    def _notify(event: str, message: str) -> None:
        if on_phase is not None:
            on_phase(event, message)

    def _run_git(args: list[str], cwd: Path | None = None) -> None:
        if verbose_cmd is not None:
            verbose_cmd(_redact_cmd(["git", *args]))
        _run(["git", *args], cwd=cwd)

    auth = _auth_config_args(clone_url, git_token)
    slug = _slug(repo)
    legacy_removed = _cleanup_legacy(cache_root, slug)
    if legacy_removed:
        _notify(
            "migrate",
            f"removed {len(legacy_removed)} legacy per-SHA dir{'s' if len(legacy_removed) != 1 else ''}",
        )

    target = cache_dir_for(cache_root, repo)
    if no_cache and target.exists():
        shutil.rmtree(target)

    overall_start = time.perf_counter()
    needs_clone = not (target / ".git").exists()
    if needs_clone:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        _notify("clone", f"cloning {repo} (one-time setup)")
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
    else:
        _notify("reuse", f"reusing {repo} clone")

    if not _sha_exists_locally(target, sha):
        _notify("fetch", f"fetching {sha[:12]} (lazy blob fetch)")
        _run_git([*auth, "fetch", "--filter=blob:none", "origin", sha], cwd=target)

    patterns = _sparse_patterns(paths)
    _notify("sparse", f"sparse-setting {len(patterns)} file{'s' if len(patterns) != 1 else ''}")
    if patterns:
        _run_git(["sparse-checkout", "set", "--no-cone", *patterns], cwd=target)
    else:
        _run_git(["sparse-checkout", "set", "--no-cone", "NOTHING_SENTINEL_b7c0f2"], cwd=target)

    _notify("checkout", f"checking out {sha[:12]}")
    _run_git([*auth, "checkout", sha], cwd=target)

    elapsed = time.perf_counter() - overall_start
    size_mb = _dir_size(target) / (1024 * 1024)
    _notify("done", f"ok ({size_mb:.1f} MB, {elapsed:.1f}s)")
    return target


def list_cache(cache_root: Path) -> list[CacheEntry]:
    """Enumerate per-repo clones. ``last_sha`` is whatever's currently checked out."""
    entries: list[CacheEntry] = []
    if not cache_root.exists():
        return entries
    for repo_dir in sorted(cache_root.iterdir()):
        if not repo_dir.is_dir():
            continue
        if not (repo_dir / ".git").exists():
            continue
        repo = repo_dir.name.replace("__", "/")
        last_sha: str | None = None
        with contextlib.suppress(Exception):
            proc = _run(["git", "rev-parse", "HEAD"], cwd=repo_dir, check=False)
            if proc.returncode == 0:
                last_sha = proc.stdout.strip() or None
        entries.append(
            CacheEntry(
                repo=repo,
                last_sha=last_sha,
                path=repo_dir,
                size_bytes=_dir_size(repo_dir),
            )
        )
    return entries


def clear_cache(cache_root: Path) -> None:
    if cache_root.exists():
        shutil.rmtree(cache_root)
