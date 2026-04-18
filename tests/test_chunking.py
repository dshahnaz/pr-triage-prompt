"""Chunking: combined prompt split into ≤N KB parts, each self-contained."""

from pr_triage_prompt.chunk import split_combined
from pr_triage_prompt.models import FileChange, PullRequest
from pr_triage_prompt.prompt import BatchItem, build_combined_prompt


def _mk_items(n: int) -> list[BatchItem]:
    items: list[BatchItem] = []
    for i in range(1, n + 1):
        patch = f"@@ -0,0 +1,3 @@\n+public class Big{i} {{\n+}}\n+\n"
        pr = PullRequest(
            number=i, sha=f"s{i}", repo="a/b", title=f"PR {i}", body="",
            jira_id=None,
            files=[FileChange(
                filename=f"mod{i}/Big{i}.java", status="added",
                additions=3, deletions=0, patch=patch,
            )],
        )
        items.append(BatchItem(pr=pr))
    return items


def test_no_chunk_when_max_bytes_zero() -> None:
    combined = build_combined_prompt(_mk_items(3)).markdown
    chunks = split_combined(combined, max_bytes=0)
    assert len(chunks) == 1
    assert chunks[0].index == 1 and chunks[0].total == 1
    assert chunks[0].markdown == combined + ("" if combined.endswith("\n") else "\n")


def test_chunking_produces_multiple_parts_under_budget() -> None:
    # 20 modules x ~200 bytes each plus header and footer much greater than 2048 bytes, must split.
    combined = build_combined_prompt(_mk_items(20)).markdown
    chunks = split_combined(combined, max_bytes=2048)
    assert len(chunks) >= 2
    for ch in chunks:
        # Each chunk under ~2x budget (greedy pack; last module may push slightly over,
        # and retrieval keys on last chunk can as well).
        assert ch.size_bytes < 2048 * 2


def test_every_chunk_has_schema_marker_and_footer() -> None:
    combined = build_combined_prompt(_mk_items(10)).markdown
    chunks = split_combined(combined, max_bytes=1500)
    assert len(chunks) >= 2
    for ch in chunks:
        assert "<!-- pr-triage-prompt schema v3 -->" in ch.markdown
        assert "BEGIN task footer" in ch.markdown
        assert "END task footer" in ch.markdown
        # Part label on every chunk.
        assert f"**Part:** {ch.index}/{ch.total}" in ch.markdown


def test_retrieval_keys_only_on_last_chunk() -> None:
    combined = build_combined_prompt(_mk_items(10)).markdown
    chunks = split_combined(combined, max_bytes=1500)
    assert len(chunks) >= 2
    for i, ch in enumerate(chunks, start=1):
        if i < len(chunks):
            assert "## Retrieval keys" not in ch.markdown
        else:
            assert "## Retrieval keys" in ch.markdown
