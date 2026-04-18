"""Checkout cache: one clone per repo, legacy migration, sparse-pattern shape."""

from pathlib import Path

from pr_triage_prompt.checkout import (
    _cleanup_legacy,
    _sparse_patterns,
    cache_dir_for,
    clear_cache,
    list_cache,
)


def test_sparse_patterns_are_exact_files_only() -> None:
    """v0.6: no parent-directory globs — only the listed file paths."""
    patterns = _sparse_patterns(["a/b/c.java", "a/b/d/e.java"])
    assert patterns == ["a/b/c.java", "a/b/d/e.java"]
    # Make sure no "a/" or "a/b/" ancestor entries leaked in.
    assert not any(p.endswith("/") for p in patterns)


def test_sparse_patterns_deduplicates_and_filters_empty() -> None:
    assert _sparse_patterns(["x.py", "x.py", ""]) == ["x.py"]


def test_cache_dir_for_is_per_repo_not_per_sha(tmp_path: Path) -> None:
    p1 = cache_dir_for(tmp_path, "vcf/mops")
    p2 = cache_dir_for(tmp_path, "vcf/mops")
    assert p1 == p2 == tmp_path / "vcf__mops"


def test_list_cache_empty(tmp_path: Path) -> None:
    assert list_cache(tmp_path) == []
    assert list_cache(tmp_path / "does-not-exist") == []


def test_list_cache_skips_dirs_without_git(tmp_path: Path) -> None:
    # Repo-looking dir without .git (an incomplete clone or legacy leftover) is skipped.
    (tmp_path / "a__b").mkdir()
    entries = list_cache(tmp_path)
    assert entries == []


def test_clear_cache_removes_root(tmp_path: Path) -> None:
    (tmp_path / "a__b").mkdir()
    clear_cache(tmp_path)
    assert not tmp_path.exists()


def test_cleanup_legacy_removes_per_sha_dirs(tmp_path: Path) -> None:
    """Legacy v0.5 layout: <slug>/<sha>/.git → should be removed on first v0.6 run."""
    slug_dir = tmp_path / "vcf__mops"
    sha_dir = slug_dir / "deadbeefcafe"
    (sha_dir / ".git").mkdir(parents=True)
    (sha_dir / "README").write_text("x")
    # Second SHA, also legacy.
    sha2 = slug_dir / "abcdef123456"
    (sha2 / ".git").mkdir(parents=True)

    removed = _cleanup_legacy(tmp_path, "vcf__mops")
    assert sorted(removed) == ["abcdef123456", "deadbeefcafe"]
    assert not sha_dir.exists()
    assert not sha2.exists()
    # The now-empty slug dir should have been cleaned up too, so a fresh clone can be placed there.
    assert not slug_dir.exists()


def test_cleanup_legacy_noop_when_slug_is_already_a_clone(tmp_path: Path) -> None:
    slug_dir = tmp_path / "vcf__mops"
    (slug_dir / ".git").mkdir(parents=True)
    (slug_dir / "some-other-dir").mkdir()  # not hex — not legacy
    removed = _cleanup_legacy(tmp_path, "vcf__mops")
    assert removed == []
    assert slug_dir.exists()
    assert (slug_dir / ".git").exists()


def test_cleanup_legacy_noop_when_no_repo_dir(tmp_path: Path) -> None:
    assert _cleanup_legacy(tmp_path, "vcf__mops") == []
