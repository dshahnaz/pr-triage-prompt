"""Schema v2: Components + Packages + Retrieval keys appear in the prompt."""

from pr_triage_prompt.models import FileChange, JiraTicket, PullRequest
from pr_triage_prompt.prompt import build_prompt


def _pr_java(jira: JiraTicket | None = None) -> PullRequest:
    patch = (
        "@@ -0,0 +1,5 @@\n"
        "+package com.example.net;\n"
        "+public class Probe {\n"
        "+    public void ping() { return; }\n"
        "+}\n"
        "+\n"
    )
    return PullRequest(
        number=1,
        sha="abc",
        repo="a/b",
        title="T",
        body="desc",
        jira_id="ABC-1",
        files=[FileChange(filename="x/Probe.java", status="added", additions=5, deletions=0, patch=patch)],
    )


def test_components_header_from_jira() -> None:
    pr = _pr_java()
    jira = JiraTicket(key="ABC-1", summary="S", components=["Network Operations", "Analytics"])
    md = build_prompt(pr, jira).markdown
    assert "**Components:** Network Operations, Analytics" in md


def test_packages_header_from_analyzer() -> None:
    pr = _pr_java()
    md = build_prompt(pr).markdown
    assert "**Packages:** com.example.net" in md


def test_retrieval_keys_section_lists_all_buckets() -> None:
    pr = _pr_java()
    jira = JiraTicket(key="ABC-1", summary="S", components=["Network Operations"])
    md = build_prompt(pr, jira).markdown
    assert "## Retrieval keys" in md
    assert "- Components: Network Operations" in md
    assert "- Packages: com.example.net" in md
    assert "- Classes: Probe" in md
    assert "- Operations: Probe.ping" in md


def test_per_file_package_line_only_in_full_detail() -> None:
    pr = _pr_java()
    md_compact = build_prompt(pr).markdown
    md_full = build_prompt(pr, detail="full").markdown
    assert "    - Package: `com.example.net`" not in md_compact
    assert "    - Package: `com.example.net`" in md_full


def test_no_retrieval_section_when_nothing_to_show() -> None:
    pr = PullRequest(
        number=2, sha="x", repo="a/b", title="empty", body="", jira_id=None,
        files=[FileChange(filename="empty.txt", status="modified", additions=0, deletions=0, patch="")],
    )
    md = build_prompt(pr).markdown
    assert "## Retrieval keys" not in md
