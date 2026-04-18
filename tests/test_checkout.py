from pathlib import Path

from pr_triage_prompt.checkout import _sparse_patterns, cache_dir_for, clear_cache, list_cache


def test_sparse_patterns_include_parents() -> None:
    patterns = _sparse_patterns(["a/b/c.java", "a/b/d/e.java"])
    assert "a/" in patterns
    assert "a/b/" in patterns
    assert "a/b/d/" in patterns
    assert "a/b/c.java" in patterns
    assert "a/b/d/e.java" in patterns


def test_cache_dir_slug_replaces_slash(tmp_path: Path) -> None:
    p = cache_dir_for(tmp_path, "vcf/mops", "deadbeef")
    assert p == tmp_path / "vcf__mops" / "deadbeef"


def test_list_cache_enumerates_dirs(tmp_path: Path) -> None:
    (tmp_path / "a__b" / "sha1").mkdir(parents=True)
    (tmp_path / "a__b" / "sha1" / "x.txt").write_bytes(b"hello")
    (tmp_path / "c__d" / "sha2").mkdir(parents=True)
    entries = list_cache(tmp_path)
    assert [e.repo for e in entries] == ["a/b", "c/d"]
    assert entries[0].size_bytes >= 5


def test_clear_cache_removes_root(tmp_path: Path) -> None:
    (tmp_path / "a__b" / "sha").mkdir(parents=True)
    clear_cache(tmp_path)
    assert not tmp_path.exists()
