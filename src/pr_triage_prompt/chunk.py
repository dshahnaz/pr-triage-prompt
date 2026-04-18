"""Split a combined prompt into multiple self-contained Markdown chunks.

Each chunk gets:
- The same `<!-- pr-triage-prompt schema vN -->` marker
- A short `# Batch part K/N` heading + the repo-level header lines
- A slice of module sections sized under the byte budget
- The fixed agent-task footer

Chunks are independently pasteable into the PAIS agent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    index: int  # 1-based
    total: int  # total chunk count; set after all chunks are known
    markdown: str
    size_bytes: int


_MODULE_HDR_RE = re.compile(r"(?m)^### ")


def _extract_sections(markdown: str) -> tuple[str, list[str], str, str]:
    """Parse the combined markdown into (header_md, module_blocks, retrieval_md, footer_md).

    The header runs from the schema marker up to (but not including) the first `### `.
    Module blocks are split at each `### `. Retrieval keys starts at `## Retrieval keys`
    and ends at the footer fence. Footer starts at `<!-- ===== pr-triage-prompt BEGIN task footer`.
    """
    # Find footer.
    footer_start = markdown.find("<!-- ===== pr-triage-prompt BEGIN task footer")
    if footer_start == -1:
        footer_md = ""
        pre_footer = markdown
    else:
        footer_md = markdown[footer_start:].rstrip() + "\n"
        pre_footer = markdown[:footer_start].rstrip() + "\n"

    # Find retrieval keys.
    retrieval_start = pre_footer.find("## Retrieval keys")
    if retrieval_start == -1:
        retrieval_md = ""
        pre_retrieval = pre_footer
    else:
        retrieval_md = pre_footer[retrieval_start:].rstrip() + "\n"
        pre_retrieval = pre_footer[:retrieval_start].rstrip() + "\n"

    # Split remaining into header + module blocks.
    first_module = _MODULE_HDR_RE.search(pre_retrieval)
    if first_module is None:
        return pre_retrieval.rstrip() + "\n", [], retrieval_md, footer_md
    header_md = pre_retrieval[: first_module.start()].rstrip() + "\n"
    body = pre_retrieval[first_module.start() :]
    blocks: list[str] = []
    from itertools import pairwise

    positions = [m.start() for m in _MODULE_HDR_RE.finditer(body)]
    positions.append(len(body))
    for a, b in pairwise(positions):
        blocks.append(body[a:b].rstrip() + "\n")
    return header_md, blocks, retrieval_md, footer_md


def _header_with_part_label(header_md: str, part: int, total: int) -> str:
    """Append a `**Part:** K/N` line inside the header (after the `# ` title)."""
    lines = header_md.splitlines()
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and line.startswith("# "):
            out.append(f"**Part:** {part}/{total}")
            inserted = True
    return "\n".join(out).rstrip() + "\n"


def split_combined(markdown: str, *, max_bytes: int) -> list[Chunk]:
    """Split a combined-prompt markdown into byte-bounded chunks.

    Chunks break between `### <module>` sections. The header, retrieval-keys
    block, and agent-task footer are repeated on every chunk so each is
    self-contained. Retrieval keys appear on the last chunk only (to save
    bytes) unless they were never present.
    """
    if max_bytes <= 0:
        # No chunking — return the whole thing as one chunk.
        text = markdown if markdown.endswith("\n") else markdown + "\n"
        return [Chunk(index=1, total=1, markdown=text, size_bytes=len(text.encode("utf-8")))]

    header_md, blocks, retrieval_md, footer_md = _extract_sections(markdown)

    # Fixed overhead per chunk = header (w/ part label) + footer. Retrieval keys only
    # appear on the last chunk, so they don't count toward the per-chunk budget here.
    footer_bytes = len(footer_md.encode("utf-8")) if footer_md else 0

    # Pack module blocks greedily.
    groups: list[list[str]] = [[]]
    # For sizing we approximate: assume header with `**Part:** X/Y` adds ≤ 30 bytes over base.
    header_bytes = len(header_md.encode("utf-8")) + 30
    per_chunk_fixed = header_bytes + footer_bytes + 4  # +4 for the "\n" joins

    current_used = per_chunk_fixed
    for block in blocks:
        block_bytes = len(block.encode("utf-8"))
        if current_used + block_bytes > max_bytes and groups[-1]:
            groups.append([])
            current_used = per_chunk_fixed
        groups[-1].append(block)
        current_used += block_bytes

    if not groups[0]:
        # No module blocks at all — still emit a single chunk with header + retrieval + footer.
        single = header_md + "\n" + retrieval_md + "\n" + footer_md
        return [Chunk(index=1, total=1, markdown=single, size_bytes=len(single.encode("utf-8")))]

    # Put retrieval keys on the LAST chunk so earlier chunks stay slim. If retrieval
    # doesn't fit on the last chunk alongside its module blocks, still include it
    # (retrieval is a ~single small list; overflow is fine because it's informational).
    total = len(groups)
    chunks: list[Chunk] = []
    for i, group in enumerate(groups, start=1):
        parts: list[str] = [_header_with_part_label(header_md, i, total).rstrip(), ""]
        parts.append("\n".join(group).rstrip())
        parts.append("")
        if i == total and retrieval_md:
            parts.append(retrieval_md.rstrip())
            parts.append("")
        if footer_md:
            parts.append(footer_md.rstrip())
            parts.append("")
        text = "\n".join(parts)
        chunks.append(Chunk(index=i, total=total, markdown=text, size_bytes=len(text.encode("utf-8"))))
    # If retrieval was present but there were zero chunks emitted, push it onto chunk 1.
    if retrieval_md and chunks and retrieval_md not in chunks[-1].markdown:
        # Shouldn't happen given the loop above, but guard.
        text = chunks[-1].markdown.rstrip() + "\n\n" + retrieval_md
        chunks[-1] = Chunk(index=chunks[-1].index, total=total, markdown=text, size_bytes=len(text.encode("utf-8")))
    return chunks
