from pr_triage_prompt.models import FileChange, JiraTicket, PullRequest
from pr_triage_prompt.prompt import BatchItem, build_combined_prompt


def _mk_pr(number: int, jira_id: str | None = None) -> PullRequest:
    return PullRequest(
        number=number,
        sha=f"sha{number}",
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


def test_combined_prompt_has_one_schema_marker_and_one_footer() -> None:
    items = [BatchItem(pr=_mk_pr(1)), BatchItem(pr=_mk_pr(2)), BatchItem(pr=_mk_pr(3))]
    bundle = build_combined_prompt(items, token_budget=16000)
    md = bundle.markdown
    assert md.count("<!-- pr-triage-prompt schema v1 -->") == 1
    assert md.count("## Task for the agent") == 1
    # Each PR appears as its own section.
    assert md.count("# PR #1 — PR 1") == 1
    assert md.count("# PR #2 — PR 2") == 1
    assert md.count("# PR #3 — PR 3") == 1


def test_combined_prompt_batch_title_and_repos() -> None:
    items = [BatchItem(pr=_mk_pr(1)), BatchItem(pr=_mk_pr(2))]
    bundle = build_combined_prompt(items, token_budget=16000)
    assert "# Batch prompt — 2 PRs" in bundle.markdown
    assert "**Repos:** a/b" in bundle.markdown


def test_combined_prompt_tight_budget_drops_later_prs() -> None:
    items = [BatchItem(pr=_mk_pr(n)) for n in range(1, 6)]
    bundle = build_combined_prompt(items, token_budget=400, per_pr_token_budget=200)
    assert "additional PR" in bundle.markdown
    assert any(mod.startswith("PR #") for mod in bundle.dropped_modules)


def test_combined_prompt_jira_per_pr() -> None:
    items = [
        BatchItem(
            pr=_mk_pr(1, jira_id="ABC-1"),
            jira=JiraTicket(key="ABC-1", summary="First ticket", issuetype="Bug"),
        ),
        BatchItem(pr=_mk_pr(2)),
    ]
    bundle = build_combined_prompt(items, token_budget=16000)
    assert "First ticket" in bundle.markdown
    # PR 2 has no Jira → placeholder shows.
    assert bundle.markdown.count("_(no Jira ticket data supplied)_") >= 1


def test_combined_prompt_single_pr_title() -> None:
    items = [BatchItem(pr=_mk_pr(42))]
    bundle = build_combined_prompt(items, token_budget=16000)
    assert "# Batch prompt — 1 PR" in bundle.markdown
    # No trailing "s" on "PR".
    assert "1 PRs" not in bundle.markdown
