from pr_triage_prompt.prompt import scrub_pr_body


def test_drops_pipeline_and_automerge_blocks() -> None:
    body = (
        "## Change Description\n"
        "Real human content.\n"
        "\n"
        "## Change Tracking ID\n"
        "_Don't remove!_\n"
        "Jira ID: ABC-1\n"
        "\n"
        "## Auto-merge.\n"
        "- Auto-merge: yes\n"
        "\n"
        "## Pipeline parameters ##\n"
        "```\n"
        "draft_enable_ci: false\n"
        "```\n"
        "\nAI-Assisted (%): 100.00"
    )
    scrubbed = scrub_pr_body(body)
    assert "Auto-merge" not in scrubbed
    assert "Pipeline parameters" not in scrubbed
    assert "Change Tracking ID" not in scrubbed
    assert "AI-Assisted" not in scrubbed
    assert "Real human content." in scrubbed
    # Change Description header is kept so the reader sees a meaningful section label.
    assert "## Change Description" in scrubbed


def test_preserves_carriage_returns_gone() -> None:
    body = "line1\r\nline2\r\n## Auto-merge.\r\n- x\r\n"
    scrubbed = scrub_pr_body(body)
    assert "\r" not in scrubbed
    assert "Auto-merge" not in scrubbed


def test_empty_body_returns_empty() -> None:
    assert scrub_pr_body("") == ""
