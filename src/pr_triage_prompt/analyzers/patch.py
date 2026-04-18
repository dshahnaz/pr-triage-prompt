"""Unified-diff parser.

Produces, from a single file's `patch` string, the set of line numbers touched
on both the pre-image and post-image. Analyzers intersect symbol line-ranges
with these sets to decide "changed".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


@dataclass
class Hunk:
    pre_start: int
    pre_len: int
    post_start: int
    post_len: int
    context_hint: str = ""
    """Text that git appends to the hunk header, usually the enclosing function signature."""
    removed_lines: set[int] = field(default_factory=set)   # pre-image line numbers with `-`
    added_lines: set[int] = field(default_factory=set)     # post-image line numbers with `+`
    post_lines: list[tuple[int, str]] = field(default_factory=list)
    """Post-image line numbers with their content (no leading +/space)."""


@dataclass
class PatchAnalysis:
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def added_line_numbers(self) -> set[int]:
        out: set[int] = set()
        for h in self.hunks:
            out |= h.added_lines
        return out

    @property
    def removed_line_numbers(self) -> set[int]:
        out: set[int] = set()
        for h in self.hunks:
            out |= h.removed_lines
        return out

    def post_image(self) -> list[tuple[int, str]]:
        """Concatenated (post_line_no, content) pairs across all hunks.

        This is *only* the post-image context the patch touches — not the full file.
        Good enough for symbol detection when combined with added_line_numbers.
        """
        out: list[tuple[int, str]] = []
        for h in self.hunks:
            out.extend(h.post_lines)
        return out

    def touches_post_range(self, start: int, end: int) -> bool:
        return any(start <= n <= end for n in self.added_line_numbers)

    def touches_pre_range(self, start: int, end: int) -> bool:
        return any(start <= n <= end for n in self.removed_line_numbers)


def parse_patch(patch: str) -> PatchAnalysis:
    """Parse a unified diff `patch` string into hunks with touched line sets."""
    result = PatchAnalysis()
    if not patch:
        return result

    lines = patch.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _HUNK_HEADER.match(line)
        if not m:
            i += 1
            continue
        pre_start = int(m.group(1))
        pre_len = int(m.group(2)) if m.group(2) is not None else 1
        post_start = int(m.group(3))
        post_len = int(m.group(4)) if m.group(4) is not None else 1
        context_hint = (m.group(5) or "").strip()
        hunk = Hunk(
            pre_start=pre_start,
            pre_len=pre_len,
            post_start=post_start,
            post_len=post_len,
            context_hint=context_hint,
        )
        pre_cursor = pre_start
        post_cursor = post_start
        i += 1
        while i < len(lines):
            body = lines[i]
            if body.startswith("@@"):
                break
            if not body:
                # a truly blank line is part of context (the leading space may have been stripped)
                hunk.post_lines.append((post_cursor, ""))
                pre_cursor += 1
                post_cursor += 1
                i += 1
                continue
            tag = body[0]
            content = body[1:]
            if tag == "+":
                hunk.added_lines.add(post_cursor)
                hunk.post_lines.append((post_cursor, content))
                post_cursor += 1
            elif tag == "-":
                hunk.removed_lines.add(pre_cursor)
                pre_cursor += 1
            elif tag == "\\":
                # "\ No newline at end of file" — skip
                pass
            else:
                # context line (leading space or other)
                hunk.post_lines.append((post_cursor, content))
                pre_cursor += 1
                post_cursor += 1
            i += 1
        result.hunks.append(hunk)
    return result
