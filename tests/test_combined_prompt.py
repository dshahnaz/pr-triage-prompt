"""Combined prompt is now a flat aggregation — no per-PR sections."""

from pr_triage_prompt.models import FileChange, JiraTicket, PullRequest
from pr_triage_prompt.prompt import BatchItem, build_combined_prompt


def _mk_pr(number: int, jira_id: str | None = None) -> PullRequest:
    return PullRequest(
        number=number,
        sha=f"sha{number}abc{number}",
        repo="a/b",
        title=f"PR {number}",
        body="body",
        jira_id=jira_id,
        files=[
            FileChange(
                filename=f"mod{number}/Foo{number}.java",
                status="added",
                additions=3,
                deletions=0,
                patch=f"@@ -0,0 +1,3 @@\n+public class Foo{number} {{\n+}}\n+\n",
            )
        ],
    )


def test_combined_has_one_schema_marker_and_one_footer() -> None:
    items = [BatchItem(pr=_mk_pr(1)), BatchItem(pr=_mk_pr(2)), BatchItem(pr=_mk_pr(3))]
    bundle = build_combined_prompt(items)
    md = bundle.markdown
    assert md.count("<!-- pr-triage-prompt schema v3 -->") == 1
    assert md.count("## Task") == 1  # footer present (either full or short heading)


def test_combined_has_no_per_pr_sections() -> None:
    items = [BatchItem(pr=_mk_pr(1)), BatchItem(pr=_mk_pr(2))]
    md = build_combined_prompt(items).markdown
    # The new combined shape flattens: no `# PR #<N>` headings appear.
    assert "# PR #1" not in md
    assert "# PR #2" not in md


def test_combined_batch_title_counts_files_and_prs() -> None:
    items = [BatchItem(pr=_mk_pr(1)), BatchItem(pr=_mk_pr(2))]
    md = build_combined_prompt(items).markdown
    assert "# Batch — 2 changed files across 2 PRs" in md
    assert "**Repos:** a/b" in md


def test_combined_lists_every_changed_file_once() -> None:
    items = [BatchItem(pr=_mk_pr(1)), BatchItem(pr=_mk_pr(2))]
    md = build_combined_prompt(items).markdown
    assert "Foo1.java" in md
    assert "Foo2.java" in md


def test_combined_dedupes_same_file_across_prs() -> None:
    same_patch = "@@ -0,0 +1,3 @@\n+public class Dup {\n+    public void one() {}\n+}\n"
    pr1 = PullRequest(
        number=1, sha="s1", repo="a/b", title="t1", body="", jira_id=None,
        files=[FileChange(filename="shared/Dup.java", status="added", additions=3, deletions=0, patch=same_patch)],
    )
    pr2 = PullRequest(
        number=2, sha="s2", repo="a/b", title="t2", body="", jira_id=None,
        files=[FileChange(filename="shared/Dup.java", status="added", additions=3, deletions=0, patch=same_patch)],
    )
    md = build_combined_prompt([BatchItem(pr=pr1), BatchItem(pr=pr2)]).markdown
    # The shared file should appear once in the module section.
    assert md.count("`shared/Dup.java`") == 1


def test_combined_compact_shows_jira_summaries_list() -> None:
    items = [
        BatchItem(
            pr=_mk_pr(1, jira_id="ABC-1"),
            jira=JiraTicket(key="ABC-1", summary="First ticket"),
        ),
        BatchItem(
            pr=_mk_pr(2, jira_id="ABC-2"),
            jira=JiraTicket(key="ABC-2", summary="Second ticket"),
        ),
    ]
    md = build_combined_prompt(items, detail="compact").markdown
    assert "**Jira summaries:**" in md
    assert "- ABC-1: First ticket" in md
    assert "- ABC-2: Second ticket" in md


def test_combined_minimal_drops_jira_summaries_list() -> None:
    items = [
        BatchItem(pr=_mk_pr(1, jira_id="ABC-1"),
                  jira=JiraTicket(key="ABC-1", summary="First")),
    ]
    md = build_combined_prompt(items, detail="minimal").markdown
    assert "Jira summaries" not in md


def test_combined_single_pr_title() -> None:
    items = [BatchItem(pr=_mk_pr(42))]
    md = build_combined_prompt(items).markdown
    assert "# Batch — 1 changed file across 1 PR" in md
