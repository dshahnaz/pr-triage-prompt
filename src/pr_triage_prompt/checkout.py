"""Sparse git clone/checkout cache, keyed by (repo, sha)."""

from __future__ import annotations

import contextlib
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CacheEntry:
    repo: str
    sha: str
    path: Path
    size_bytes: int


def _slug(repo: str) -> str:
    return repo.replace("/", "__")


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


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
) -> Path:
    """Return a path to a sparse checkout of `repo@sha` that contains `paths`.

    Uses `~/.cache/pr-triage/<repo-slug>/<sha>/`. Re-adds paths to the sparse
    pattern if an existing checkout was made for a different subset of files.
    """
    target = cache_dir_for(cache_root, repo, sha)
    if no_cache and target.exists():
        shutil.rmtree(target)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        _run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--sparse",
                "--no-checkout",
                clone_url,
                str(target),
            ]
        )
        _run(["git", "sparse-checkout", "init", "--no-cone"], cwd=target)
    patterns = _sparse_patterns(paths)
    _run(["git", "sparse-checkout", "set", "--no-cone", *patterns], cwd=target)
    _run(["git", "checkout", sha], cwd=target)
    return target


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
