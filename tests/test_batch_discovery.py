import json
from pathlib import Path

from pr_triage_prompt.io.batch import discover_context


def _write_pr(dir: Path, number: int, jira_id: str | None) -> None:
    (dir / f"pr_{number}.json").write_text(
        json.dumps(
            {
                "number": number,
                "sha": f"sha{number}",
                "repo": "a/b",
                "title": f"PR {number}",
                "body": "body",
                "jira_id": jira_id,
                "files": [],
            }
        ),
        encoding="utf-8",
    )


def _write_jira_file(dir: Path, filename: str, key: str | None, summary: str | None = "S") -> None:
    (dir / filename).write_text(
        json.dumps({"key": key, "summary": summary}) if key or summary else "",
        encoding="utf-8",
    )


def test_discover_matches_by_filename(tmp_path: Path) -> None:
    _write_pr(tmp_path, 1, jira_id="ABC-1")
    _write_jira_file(tmp_path, "jira_ABC-1.json", key="ABC-1")
    items = discover_context(tmp_path)
    assert len(items) == 1
    assert items[0].jira_match == "filename"
    assert items[0].jira is not None
    assert items[0].jira.key == "ABC-1"


def test_discover_content_fallback(tmp_path: Path) -> None:
    _write_pr(tmp_path, 2, jira_id="ABC-2")
    # Filename doesn't match the jira_id, but the file contains key=ABC-2.
    _write_jira_file(tmp_path, "jira_export_20261201.json", key="ABC-2")
    items = discover_context(tmp_path)
    assert len(items) == 1
    assert items[0].jira_match == "content"
    assert items[0].jira is not None
    assert items[0].jira.key == "ABC-2"


def test_discover_no_jira_file(tmp_path: Path) -> None:
    _write_pr(tmp_path, 3, jira_id="ABC-3")
    items = discover_context(tmp_path)
    assert len(items) == 1
    assert items[0].jira_match == "none"
    assert items[0].jira is None


def test_discover_pr_without_jira_id(tmp_path: Path) -> None:
    _write_pr(tmp_path, 4, jira_id=None)
    _write_jira_file(tmp_path, "jira_ABC-9.json", key="ABC-9")
    items = discover_context(tmp_path)
    assert items[0].jira_match == "none"


def test_discover_multiple_prs_sorted(tmp_path: Path) -> None:
    _write_pr(tmp_path, 10, jira_id="ABC-10")
    _write_pr(tmp_path, 2, jira_id="ABC-2")
    _write_pr(tmp_path, 1, jira_id=None)
    items = discover_context(tmp_path)
    # Sorted by filename → pr_1, pr_10, pr_2 (lexicographic).
    assert [it.pr.number for it in items] == [1, 10, 2]


def test_discover_ignores_malformed_pr(tmp_path: Path) -> None:
    (tmp_path / "pr_bad.json").write_text("not json", encoding="utf-8")
    _write_pr(tmp_path, 1, jira_id=None)
    items = discover_context(tmp_path)
    assert [it.pr.number for it in items] == [1]


def test_discover_ignores_empty_jira_placeholder(tmp_path: Path) -> None:
    _write_pr(tmp_path, 5, jira_id="ABC-5")
    # Empty file -> load_jira_file returns a blank JiraTicket; match is still "filename"
    # but jira.has_content is False, so prompt will show "(no Jira ticket data supplied)".
    (tmp_path / "jira_ABC-5.json").write_text("", encoding="utf-8")
    items = discover_context(tmp_path)
    assert items[0].jira_match == "filename"
    assert items[0].jira is not None
    assert not items[0].jira.has_content
