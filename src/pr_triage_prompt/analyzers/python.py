"""Python analyzer — regex-based."""

from __future__ import annotations

import re
from pathlib import Path

from pr_triage_prompt.analyzers.base import collect_excerpt, register_analyzer
from pr_triage_prompt.analyzers.patch import PatchAnalysis, parse_patch
from pr_triage_prompt.models import FileChangeSummary

_CLASS_RE = re.compile(r"^(\s*)class\s+([A-Za-z_][A-Za-z0-9_]*)\s*[:(]")
_FUNC_RE = re.compile(r"^(\s*)(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def _hunk_has_changes(analysis: PatchAnalysis, lineno: int) -> bool:
    for h in analysis.hunks:
        if h.post_start <= lineno < h.post_start + max(h.post_len, 1):
            return bool(h.added_lines or h.removed_lines)
    return False


def _python_package_from_path(file_path: Path, repo_root: Path) -> str | None:
    """Derive a dotted module path from `repo_root/file_path` by walking parents that
    contain __init__.py; stop at the last such directory. Returns None for top-level scripts.
    """
    try:
        rel = (repo_root / file_path).resolve().relative_to(repo_root.resolve())
    except ValueError:
        return None
    parts = list(rel.parts)
    if not parts or not parts[-1].endswith(".py"):
        return None
    parts[-1] = parts[-1][:-3]  # drop ".py"
    if parts[-1] == "__init__":
        parts.pop()
    # Simple heuristic: include each directory that has __init__.py.
    pkg_parts: list[str] = []
    ancestors = list((repo_root / rel.parent).relative_to(repo_root).parts)
    d = repo_root
    for seg in ancestors:
        d = d / seg
        if (d / "__init__.py").exists():
            pkg_parts.append(seg)
    pkg_parts.append(parts[-1])
    if not pkg_parts:
        return None
    return ".".join(pkg_parts)


@register_analyzer
class PythonAnalyzer:
    extensions: tuple[str, ...] = (".py",)
    language: str = "Python"

    def analyze(self, file_path: Path, patch: str, status: str) -> FileChangeSummary:
        analysis = parse_patch(patch)
        post_lines = analysis.post_image()
        added = analysis.added_line_numbers

        classes: list[str] = []
        funcs: list[str] = []
        seen_classes: set[str] = set()
        seen_funcs: set[str] = set()

        # Track current class by indentation.
        class_stack: list[tuple[int, str]] = []  # (indent_len, name)

        for lineno, content in post_lines:
            if not content.strip():
                continue

            indent = len(content) - len(content.lstrip(" "))
            while class_stack and indent <= class_stack[-1][0]:
                class_stack.pop()

            m_cls = _CLASS_RE.match(content)
            if m_cls:
                name = m_cls.group(2)
                cls_indent = len(m_cls.group(1))
                class_stack.append((cls_indent, name))
                if (lineno in added or _hunk_has_changes(analysis, lineno)) and name not in seen_classes:
                    seen_classes.add(name)
                    classes.append(name)
                continue

            m_fn = _FUNC_RE.match(content)
            if m_fn:
                name = m_fn.group(2)
                if lineno in added or _hunk_has_changes(analysis, lineno):
                    label = f"{class_stack[-1][1]}.{name}" if class_stack else name
                    if label not in seen_funcs:
                        seen_funcs.add(label)
                        funcs.append(label)

        for h in analysis.hunks:
            if not h.context_hint:
                continue
            m = _FUNC_RE.match(h.context_hint)
            if m:
                name = m.group(2)
                if name not in seen_funcs:
                    seen_funcs.add(name)
                    funcs.append(name)
            m_cls = _CLASS_RE.match(h.context_hint)
            if m_cls:
                name = m_cls.group(2)
                if name not in seen_classes:
                    seen_classes.add(name)
                    classes.append(name)

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

        # Walk every line of the full file with a simple indent-scoped class stack.
        classes: list[str] = []
        funcs: list[str] = []
        seen_cls: set[str] = set()
        seen_fn: set[str] = set()
        class_stack: list[tuple[int, str]] = []
        func_stack: list[tuple[int, str]] = []

        for lineno, raw in enumerate(text.splitlines(), start=1):
            content = raw
            if not content.strip():
                continue
            indent = len(content) - len(content.lstrip(" "))
            while class_stack and indent <= class_stack[-1][0]:
                class_stack.pop()
            while func_stack and indent <= func_stack[-1][0]:
                func_stack.pop()

            m_cls = _CLASS_RE.match(content)
            m_fn = _FUNC_RE.match(content)
            if m_cls:
                class_stack.append((indent, m_cls.group(2)))
            elif m_fn:
                name = m_fn.group(2)
                qname = f"{class_stack[-1][1]}.{name}" if class_stack else name
                func_stack.append((indent, qname))

            if lineno in added:
                if class_stack and class_stack[-1][1] not in seen_cls:
                    seen_cls.add(class_stack[-1][1])
                    classes.append(class_stack[-1][1])
                if func_stack and func_stack[-1][1] not in seen_fn:
                    seen_fn.add(func_stack[-1][1])
                    funcs.append(func_stack[-1][1])

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
            package=_python_package_from_path(file_path, repo_root),
        )
