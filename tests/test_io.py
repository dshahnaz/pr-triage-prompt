import json
from pathlib import Path

import httpx
import pytest

from pr_triage_prompt.io.jira import fetch_jira_live, load_jira_file
from pr_triage_prompt.io.pr import fetch_pr_live, load_pr_file, parse_pr_ref


def test_load_pr_file_roundtrips(tmp_path: Path) -> None:
    payload = {
        "number": 1,
        "sha": "abc",
        "repo": "a/b",
        "title": "t",
        "body": "hi",
        "jira_id": "X-1",
        "files": [
            {"filename": "a.py", "status": "modified", "additions": 1, "deletions": 0, "patch": "@@"}
        ],
    }
    p = tmp_path / "pr.json"
    p.write_text(json.dumps(payload))
    pr = load_pr_file(p)
    assert pr.number == 1
    assert pr.files[0].filename == "a.py"


def test_parse_pr_ref() -> None:
    ref = parse_pr_ref("owner/repo#42")
    assert ref is not None
    assert ref.owner_repo == "owner/repo"
    assert ref.number == 42
    assert parse_pr_ref("/not/a/ref") is None
    assert parse_pr_ref("plain-path.json") is None


def test_load_jira_empty_file_returns_blank_ticket(tmp_path: Path) -> None:
    p = tmp_path / "j.json"
    p.write_text("")
    t = load_jira_file(p)
    assert t.summary is None
    assert not t.has_content


def test_load_jira_flat_shape(tmp_path: Path) -> None:
    p = tmp_path / "j.json"
    p.write_text(json.dumps({"key": "X-1", "summary": "S", "description": "D", "issuetype": "Bug"}))
    t = load_jira_file(p)
    assert t.key == "X-1"
    assert t.summary == "S"
    assert t.issuetype == "Bug"


def test_load_jira_raw_rest_shape(tmp_path: Path) -> None:
    p = tmp_path / "j.json"
    p.write_text(
        json.dumps(
            {
                "key": "X-2",
                "fields": {
                    "summary": "S2",
                    "description": "D2",
                    "issuetype": {"name": "Task"},
                    "status": {"name": "In Progress"},
                    "labels": ["a", "b"],
                    "components": [{"name": "Core"}, {"name": "UI"}],
                },
            }
        )
    )
    t = load_jira_file(p)
    assert t.summary == "S2"
    assert t.issuetype == "Task"
    assert t.status == "In Progress"
    assert t.components == ["Core", "UI"]
    assert t.labels == ["a", "b"]


def test_fetch_pr_live_pages_files(httpx_mock) -> None:
    base = "https://api.github.com"
    httpx_mock.add_response(
        url=f"{base}/repos/a/b/pulls/1",
        json={"number": 1, "title": "Fix [ABC-9]", "body": "", "head": {"sha": "deadbeef"}},
    )
    httpx_mock.add_response(
        url=f"{base}/repos/a/b/pulls/1/files?per_page=100&page=1",
        json=[
            {"filename": "x.py", "status": "modified", "additions": 2, "deletions": 1, "patch": "p"}
        ],
    )
    pr = fetch_pr_live("a/b", 1, "tok")
    assert pr.number == 1
    assert pr.jira_id == "ABC-9"
    assert pr.files[0].filename == "x.py"


def test_fetch_jira_live_bearer(httpx_mock) -> None:
    httpx_mock.add_response(
        url="https://jira.example/rest/api/2/issue/X-7",
        json={"key": "X-7", "fields": {"summary": "Hi", "status": {"name": "Open"}}},
    )
    t = fetch_jira_live("https://jira.example", "X-7", "tok")
    assert t.key == "X-7"
    assert t.summary == "Hi"
    assert t.status == "Open"


def test_fetch_jira_live_propagates_http_error(httpx_mock) -> None:
    httpx_mock.add_response(
        url="https://jira.example/rest/api/2/issue/X-8",
        status_code=404,
    )
    with pytest.raises(httpx.HTTPStatusError):
        fetch_jira_live("https://jira.example", "X-8", "tok")
