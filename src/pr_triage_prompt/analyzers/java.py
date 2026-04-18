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
_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;")
_RESERVED = {"if", "for", "while", "switch", "catch", "return", "throw", "new"}


def extract_java_package(text: str) -> str | None:
    for line in text.splitlines():
        m = _PACKAGE_RE.match(line)
        if m:
            return m.group(1)
        s = line.strip()
        if s and not s.startswith(("//", "/*", "*")):
            # Hit real code before finding `package` — file has no declaration.
            return None
    return None


def _added_content(analysis: PatchAnalysis) -> list[str]:
    added = analysis.added_line_numbers
    return [content for (lineno, content) in analysis.post_image() if lineno in added]


def _hunk_for_line(analysis: PatchAnalysis, lineno: int) -> Hunk | None:
    for h in analysis.hunks:
        if h.post_start <= lineno < h.post_start + max(h.post_len, 1):
            return h
    return None


def _strip_strings(s: str) -> str:
    return re.sub(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", '""', s)


def _walk_java_lines(lines: list[str], changed_line_numbers: set[int]) -> tuple[list[str], list[str]]:
    """Walk Java source, report (classes_changed, functions_changed).

    A class/method is "changed" if any line in its body appears in
    `changed_line_numbers`. Uses brace tracking to scope methods to their
    enclosing class; inner classes pop cleanly when the outer brace closes.
    """
    classes: list[str] = []
    funcs: list[str] = []
    seen_cls: set[str] = set()
    seen_fn: set[str] = set()
    class_stack: list[tuple[int, str]] = []
    method_stack: list[tuple[int, str]] = []
    brace_depth = 0

    for lineno, raw in enumerate(lines, start=1):
        stripped = _strip_strings(raw)
        current_class_name = class_stack[-1][1] if class_stack else None

        m_cls = _CLASS_RE.match(raw)
        m_meth = _METHOD_RE.match(raw)
        m_ctor = _CTOR_RE.match(raw)

        if m_cls:
            class_stack.append((brace_depth, m_cls.group(1)))
        elif m_meth and m_meth.group(1) not in _RESERVED and current_class_name:
            qname = f"{current_class_name}.{m_meth.group(1)}"
            method_stack.append((brace_depth, qname))
        elif m_ctor and current_class_name and m_ctor.group(1) == current_class_name:
            qname = f"{current_class_name}.<init>"
            method_stack.append((brace_depth, qname))

        if lineno in changed_line_numbers:
            cc = class_stack[-1][1] if class_stack else None
            if cc and cc not in seen_cls:
                seen_cls.add(cc)
                classes.append(cc)
            if method_stack and method_stack[-1][1] not in seen_fn:
                seen_fn.add(method_stack[-1][1])
                funcs.append(method_stack[-1][1])

        # Update brace depth from this line.
        for ch in stripped:
            if ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth -= 1
                while class_stack and class_stack[-1][0] >= brace_depth:
                    class_stack.pop()
                while method_stack and method_stack[-1][0] >= brace_depth:
                    method_stack.pop()

    return classes, funcs


@register_analyzer
class JavaAnalyzer:
    extensions: tuple[str, ...] = (".java",)
    language: str = "Java"

    def analyze(self, file_path: Path, patch: str, status: str) -> FileChangeSummary:
        analysis = parse_patch(patch)
        post_lines_pairs = analysis.post_image()
        added = analysis.added_line_numbers

        # Reconstruct a sparse view of the file from the hunks so the brace-tracking
        # walker works on what we can see. Gaps between hunks are invisible, which is
        # exactly why the full-file `analyze_file` path is preferred when source is present.
        max_line = max((lineno for lineno, _ in post_lines_pairs), default=0)
        line_map: dict[int, str] = dict(post_lines_pairs)
        changed: set[int] = set()
        for lineno, _ in post_lines_pairs:
            hunk = _hunk_for_line(analysis, lineno)
            if lineno in added or (hunk and (hunk.added_lines or hunk.removed_lines)):
                changed.add(lineno)
        sparse_lines = [line_map.get(i, "") for i in range(1, max_line + 1)]
        classes, funcs = _walk_java_lines(sparse_lines, changed)

        # Context hints from the hunk header ("@@ … @@ public void fooBar()").
        for h in analysis.hunks:
            if not h.context_hint:
                continue
            m = _METHOD_RE.match(h.context_hint)
            if m and m.group(1) not in _RESERVED and m.group(1) not in funcs:
                funcs.append(m.group(1))

        added_content = _added_content(analysis)
        excerpt = collect_excerpt(added_content)

        # Package declaration — only reliable for added files where the full patch
        # begins at line 1, but try regardless.
        package = extract_java_package("\n".join(content for _, content in post_lines_pairs))

        return FileChangeSummary(
            path=str(file_path),
            language=self.language,
            status=status,
            additions=sum(len(h.added_lines) for h in analysis.hunks),
            deletions=sum(len(h.removed_lines) for h in analysis.hunks),
            classes_changed=classes,
            functions_changed=funcs,
            excerpt=excerpt,
            package=package,
        )

    def analyze_file(
        self, file_path: Path, patch: str, status: str, repo_root: Path
    ) -> FileChangeSummary:
        abs_path = repo_root / file_path
        text = abs_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        analysis = parse_patch(patch)
        changed: set[int] = set(analysis.added_line_numbers)
        # For modified files we also want lines surrounding removed content to count, but
        # pre-image lines map to a different file. Post-image additions are the best signal.

        classes, funcs = _walk_java_lines(lines, changed)

        for h in analysis.hunks:
            if not h.context_hint:
                continue
            m = _METHOD_RE.match(h.context_hint)
            if m and m.group(1) not in _RESERVED and m.group(1) not in funcs:
                funcs.append(m.group(1))

        added_content = [content for (n, content) in analysis.post_image() if n in analysis.added_line_numbers]
        excerpt = collect_excerpt(added_content)
        package = extract_java_package(text)

        return FileChangeSummary(
            path=str(file_path),
            language=self.language,
            status=status,
            additions=sum(len(h.added_lines) for h in analysis.hunks),
            deletions=sum(len(h.removed_lines) for h in analysis.hunks),
            classes_changed=classes,
            functions_changed=funcs,
            excerpt=excerpt,
            package=package,
        )
