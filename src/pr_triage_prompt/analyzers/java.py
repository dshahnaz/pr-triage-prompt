"""Java analyzer — regex-based with graceful tree-sitter path when the grammar is installed."""

from __future__ import annotations

import re
from pathlib import Path

from pr_triage_prompt.analyzers.base import collect_excerpt, register_analyzer
from pr_triage_prompt.analyzers.patch import Hunk, PatchAnalysis, parse_patch
from pr_triage_prompt.models import FileChangeSummary

_CLASS_RE = re.compile(
    r"^\s*(?:public\s+|private\s+|protected\s+|static\s+|final\s+|abstract\s+|sealed\s+|non-sealed\s+)*"
    r"(?:class|interface|enum|record)\s+([A-Z][A-Za-z0-9_]*)"
)
_METHOD_RE = re.compile(
    r"^\s*(?:@[A-Za-z_][A-Za-z0-9_.]*(?:\([^)]*\))?\s*)*"
    r"(?:public\s+|private\s+|protected\s+|static\s+|final\s+|abstract\s+|synchronized\s+|default\s+|native\s+)+"
    r"(?:<[^>]+>\s+)?"
    r"(?:[A-Za-z_][A-Za-z0-9_<>\[\]\.]*\s+)+"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*\("
)
# Constructor = CapName(... ) at the start of a line inside a class body.
_CTOR_RE = re.compile(
    r"^\s*(?:public\s+|private\s+|protected\s+)?"
    r"([A-Z][A-Za-z0-9_]*)\s*\([^)]*\)\s*(?:throws\s+[^{]+)?\{?"
)


def _added_content(analysis: PatchAnalysis) -> list[str]:
    added = analysis.added_line_numbers
    return [content for (lineno, content) in analysis.post_image() if lineno in added]


def _hunk_for_line(analysis: PatchAnalysis, lineno: int) -> Hunk | None:
    for h in analysis.hunks:
        if h.post_start <= lineno < h.post_start + max(h.post_len, 1):
            return h
    return None


@register_analyzer
class JavaAnalyzer:
    extensions: tuple[str, ...] = (".java",)
    language: str = "Java"

    def analyze(self, file_path: Path, patch: str, status: str) -> FileChangeSummary:
        analysis = parse_patch(patch)
        post_lines = analysis.post_image()
        added = analysis.added_line_numbers

        classes: list[str] = []
        funcs: list[str] = []
        seen_classes: set[str] = set()
        seen_funcs: set[str] = set()
        # Stack of (opening_brace_depth, class_name). Pops when depth drops below the entry.
        class_stack: list[tuple[int, str]] = []
        brace_depth = 0

        def current_class() -> str | None:
            return class_stack[-1][1] if class_stack else None

        def _strip_strings(s: str) -> str:
            # Replace string and char literals with placeholders so their braces don't count.
            return re.sub(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", "\"\"", s)

        for lineno, content in post_lines:
            stripped = _strip_strings(content)

            m = _CLASS_RE.match(content)
            if m:
                name = m.group(1)
                hunk = _hunk_for_line(analysis, lineno)
                hunk_has_changes = hunk is not None and (hunk.added_lines or hunk.removed_lines)
                if (lineno in added or hunk_has_changes) and name not in seen_classes:
                    seen_classes.add(name)
                    classes.append(name)
                # The opening `{` of the class may be on this line or a later one; we push now
                # and use the *current* brace_depth as the marker. When depth returns to that
                # value (after the class body closes), we pop.
                class_stack.append((brace_depth, name))
            else:
                m_meth = _METHOD_RE.match(content)
                if m_meth:
                    name = m_meth.group(1)
                    if name not in {"if", "for", "while", "switch", "catch", "return", "throw", "new"}:
                        hunk = _hunk_for_line(analysis, lineno)
                        hunk_has_changes = hunk is not None and (hunk.added_lines or hunk.removed_lines)
                        if lineno in added or hunk_has_changes:
                            cc = current_class()
                            label = f"{cc}.{name}" if cc else name
                            if label not in seen_funcs:
                                seen_funcs.add(label)
                                funcs.append(label)
                else:
                    m_ctor = _CTOR_RE.match(content)
                    cc = current_class()
                    if m_ctor and cc and m_ctor.group(1) == cc:
                        hunk = _hunk_for_line(analysis, lineno)
                        hunk_has_changes = hunk is not None and (hunk.added_lines or hunk.removed_lines)
                        if lineno in added or hunk_has_changes:
                            label = f"{cc}.<init>"
                            if label not in seen_funcs:
                                seen_funcs.add(label)
                                funcs.append(label)

            # Update brace depth from this line (after the match so class_stack push is correct).
            for ch in stripped:
                if ch == "{":
                    brace_depth += 1
                elif ch == "}":
                    brace_depth -= 1
                    # Pop classes whose marker equals the new depth.
                    while class_stack and class_stack[-1][0] >= brace_depth:
                        class_stack.pop()

        # Context hints from the hunk header ("@@ … @@ public void fooBar()")
        for h in analysis.hunks:
            if not h.context_hint:
                continue
            m = _METHOD_RE.match(h.context_hint)
            if m:
                name = m.group(1)
                if name in {"if", "for", "while", "switch", "catch", "return", "throw", "new"}:
                    continue
                if name not in seen_funcs:
                    seen_funcs.add(name)
                    funcs.append(name)

        # Additions counted in the patch; deltas come from caller.
        added_content = _added_content(analysis)
        excerpt = collect_excerpt(added_content)

        return FileChangeSummary(
            path=str(file_path),
            language=self.language,
            status=status,
            additions=sum(len(h.added_lines) for h in analysis.hunks),
            deletions=sum(len(h.removed_lines) for h in analysis.hunks),
            classes_changed=classes,
            functions_changed=funcs,
            excerpt=excerpt,
        )
