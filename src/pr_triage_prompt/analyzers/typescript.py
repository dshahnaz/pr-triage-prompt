"""TypeScript / JavaScript analyzer — regex-based."""

from __future__ import annotations

import re
from pathlib import Path

from pr_triage_prompt.analyzers.base import collect_excerpt, register_analyzer
from pr_triage_prompt.analyzers.patch import PatchAnalysis, parse_patch
from pr_triage_prompt.models import FileChangeSummary

_CLASS_RE = re.compile(
    r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)"
)
_INTERFACE_RE = re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)")
# function foo(), function* foo(), async function foo(), export function foo()
_FUNCTION_DECL_RE = re.compile(
    r"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\*?\s+([A-Za-z_$][\w$]*)\s*\("
)
# const foo = (...) =>, let foo = async (...) =>, export const foo = function()
_ARROW_RE = re.compile(
    r"^\s*(?:export\s+(?:default\s+)?)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::\s*[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"
)
# method() { ... } inside a class body — heuristic: word followed by (, then whitespace/whatever, then { on same line or next
_METHOD_RE = re.compile(
    r"^\s*(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+|async\s+|\*\s*)*"
    r"([A-Za-z_$][\w$]*)\s*(?:<[^>]+>)?\s*\([^)]*\)\s*(?::\s*[^{]+)?\s*\{?\s*$"
)
_RESERVED = {"if", "for", "while", "switch", "catch", "return", "throw", "new", "else", "do", "try", "finally"}


def _hunk_has_changes(analysis: PatchAnalysis, lineno: int) -> bool:
    for h in analysis.hunks:
        if h.post_start <= lineno < h.post_start + max(h.post_len, 1):
            return bool(h.added_lines or h.removed_lines)
    return False


@register_analyzer
class TypeScriptAnalyzer:
    extensions: tuple[str, ...] = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
    language: str = "TypeScript/JavaScript"

    def analyze(self, file_path: Path, patch: str, status: str) -> FileChangeSummary:
        analysis = parse_patch(patch)
        post_lines = analysis.post_image()
        added = analysis.added_line_numbers

        classes: list[str] = []
        funcs: list[str] = []
        seen_cls: set[str] = set()
        seen_fn: set[str] = set()
        current_class: str | None = None

        for lineno, content in post_lines:
            touched = lineno in added or _hunk_has_changes(analysis, lineno)

            m = _CLASS_RE.match(content) or _INTERFACE_RE.match(content)
            if m:
                current_class = m.group(1)
                if touched and current_class not in seen_cls:
                    seen_cls.add(current_class)
                    classes.append(current_class)
                continue

            m = _FUNCTION_DECL_RE.match(content) or _ARROW_RE.match(content)
            if m:
                name = m.group(1)
                if name in _RESERVED:
                    continue
                if touched and name not in seen_fn:
                    seen_fn.add(name)
                    funcs.append(name)
                continue

            if current_class:
                m = _METHOD_RE.match(content)
                if m:
                    name = m.group(1)
                    if name in _RESERVED or name == current_class:
                        continue
                    if touched:
                        label = f"{current_class}.{name}"
                        if label not in seen_fn:
                            seen_fn.add(label)
                            funcs.append(label)

        for h in analysis.hunks:
            hint = h.context_hint
            if not hint:
                continue
            m = _FUNCTION_DECL_RE.match(hint) or _ARROW_RE.match(hint)
            if m:
                name = m.group(1)
                if name not in _RESERVED and name not in seen_fn:
                    seen_fn.add(name)
                    funcs.append(name)

        added_content = [c for (n, c) in post_lines if n in added]
        return FileChangeSummary(
            path=str(file_path),
            language=self.language,
            status=status,
            additions=sum(len(h.added_lines) for h in analysis.hunks),
            deletions=sum(len(h.removed_lines) for h in analysis.hunks),
            classes_changed=classes,
            functions_changed=funcs,
            excerpt=collect_excerpt(added_content),
        )

    def analyze_file(
        self, file_path: Path, patch: str, status: str, repo_root: Path
    ) -> FileChangeSummary:
        abs_path = repo_root / file_path
        text = abs_path.read_text(encoding="utf-8", errors="replace")
        analysis = parse_patch(patch)
        added = analysis.added_line_numbers

        classes: list[str] = []
        funcs: list[str] = []
        seen_cls: set[str] = set()
        seen_fn: set[str] = set()
        class_stack: list[tuple[int, str]] = []
        brace_depth = 0

        for lineno, raw in enumerate(text.splitlines(), start=1):
            content = raw
            current_class = class_stack[-1][1] if class_stack else None

            m = _CLASS_RE.match(content) or _INTERFACE_RE.match(content)
            if m:
                class_stack.append((brace_depth, m.group(1)))
            else:
                m_fn = _FUNCTION_DECL_RE.match(content) or _ARROW_RE.match(content)
                if m_fn and m_fn.group(1) not in _RESERVED:
                    if lineno in added and m_fn.group(1) not in seen_fn:
                        seen_fn.add(m_fn.group(1))
                        funcs.append(m_fn.group(1))
                elif current_class:
                    m_meth = _METHOD_RE.match(content)
                    if (
                        m_meth
                        and m_meth.group(1) not in _RESERVED
                        and m_meth.group(1) != current_class
                        and lineno in added
                    ):
                        label = f"{current_class}.{m_meth.group(1)}"
                        if label not in seen_fn:
                            seen_fn.add(label)
                            funcs.append(label)

            if lineno in added and current_class and current_class not in seen_cls:
                seen_cls.add(current_class)
                classes.append(current_class)

            for ch in content:
                if ch == "{":
                    brace_depth += 1
                elif ch == "}":
                    brace_depth -= 1
                    while class_stack and class_stack[-1][0] >= brace_depth:
                        class_stack.pop()

        added_content = [c for (n, c) in analysis.post_image() if n in added]
        return FileChangeSummary(
            path=str(file_path),
            language=self.language,
            status=status,
            additions=sum(len(h.added_lines) for h in analysis.hunks),
            deletions=sum(len(h.removed_lines) for h in analysis.hunks),
            classes_changed=classes,
            functions_changed=funcs,
            excerpt=collect_excerpt(added_content),
        )
