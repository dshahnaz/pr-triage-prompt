from pr_triage_prompt.models import FileChange, PullRequest
from pr_triage_prompt.prompt import build_prompt


def _mk_pr(num_modules: int) -> PullRequest:
    files = []
    for i in range(num_modules):
        patch = "@@ -0,0 +1,3 @@\n+public class Big" + str(i) + " {\n+}\n+\n"
        # Put each file in its own top-level directory so modules differ.
        files.append(
            FileChange(
                filename=f"module{i}/src/main/java/Big{i}.java",
                status="added",
                additions=3,
                deletions=0,
                patch=patch,
            )
        )
    return PullRequest(
        number=1,
        sha="abc",
        repo="a/b",
        title="Test",
        body="desc",
        jira_id=None,
        files=files,
    )


def test_non_strict_keeps_everything_even_when_over_budget() -> None:
    pr = _mk_pr(num_modules=6)
    bundle = build_prompt(pr, jira=None, token_budget=200)
    assert bundle.dropped_modules == []
    assert "additional modules omitted" not in bundle.markdown
    # And the bundle records an over-budget state for the caller to surface.
    assert bundle.token_count > bundle.token_budget


def test_strict_budget_drops_overflow_modules() -> None:
    pr = _mk_pr(num_modules=6)
    bundle = build_prompt(pr, jira=None, token_budget=200, strict_budget=True)
    assert bundle.dropped_modules, "Expected at least one module dropped under strict mode"
    assert "additional modules omitted" in bundle.markdown


def test_loose_budget_keeps_everything_in_both_modes() -> None:
    pr = _mk_pr(num_modules=3)
    assert build_prompt(pr, jira=None, token_budget=8000).dropped_modules == []
    assert build_prompt(pr, jira=None, token_budget=8000, strict_budget=True).dropped_modules == []


def test_schema_marker_and_footer_always_present() -> None:
    pr = _mk_pr(num_modules=1)
    bundle = build_prompt(pr, jira=None, token_budget=8000)
    assert bundle.markdown.startswith("<!-- pr-triage-prompt schema v3 -->")
    assert "Task for the agent" in bundle.markdown
    assert "Using **only** the retrieved test-suite context" in bundle.markdown
