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


def test_tight_budget_drops_modules() -> None:
    pr = _mk_pr(num_modules=6)
    bundle = build_prompt(pr, jira=None, token_budget=200)
    assert bundle.dropped_modules, "Expected at least one module dropped under a tight budget"
    assert "additional modules omitted" in bundle.markdown


def test_loose_budget_keeps_everything() -> None:
    pr = _mk_pr(num_modules=3)
    bundle = build_prompt(pr, jira=None, token_budget=8000)
    assert bundle.dropped_modules == []


def test_schema_marker_and_footer_always_present() -> None:
    pr = _mk_pr(num_modules=1)
    bundle = build_prompt(pr, jira=None, token_budget=8000)
    assert bundle.markdown.startswith("<!-- pr-triage-prompt schema v1 -->")
    assert "Task for the agent" in bundle.markdown
    assert "Using only the retrieved test-suite context" in bundle.markdown
