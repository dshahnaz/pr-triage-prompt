"""Resolve a changed file to its nearest build-descriptor module."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass
class ResolvedModule:
    module_name: str
    module_path: str   # relative to repo root if available, else the file's parent dir
    descriptor: str | None  # descriptor filename, e.g. "pom.xml"


# Known descriptor filenames (exact match) in search priority order.
_EXACT_DESCRIPTORS: tuple[str, ...] = (
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "build.xml",
    "package.json",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "go.mod",
    "Cargo.toml",
    "Gemfile",
)

# Glob patterns that match by suffix.
_SUFFIX_DESCRIPTORS: tuple[str, ...] = (".csproj", ".fsproj", ".gemspec")


def _find_nearest_descriptor(repo_root: Path, rel_path: str) -> tuple[Path, str] | None:
    """Walk up from rel_path (inside repo_root) until a descriptor is found."""
    rel = PurePosixPath(rel_path)
    current = rel.parent
    while True:
        dir_abs = repo_root / current if str(current) not in ("", ".") else repo_root
        if dir_abs.is_dir():
            for name in _EXACT_DESCRIPTORS:
                candidate = dir_abs / name
                if candidate.is_file():
                    return candidate, name
            for entry in dir_abs.iterdir():
                if entry.is_file() and any(entry.name.endswith(s) for s in _SUFFIX_DESCRIPTORS):
                    return entry, entry.name
        if str(current) in ("", "."):
            return None
        current = current.parent


def _parse_pom_artifact(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # Grab the first <artifactId>...</artifactId> that is NOT inside a <parent> block.
    # Cheap approximation: strip a leading <parent>...</parent> block.
    stripped = re.sub(r"<parent>.*?</parent>", "", text, count=1, flags=re.DOTALL)
    m = re.search(r"<artifactId>([^<]+)</artifactId>", stripped)
    return m.group(1).strip() if m else None


def _parse_json_name(path: Path) -> str | None:
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    name = data.get("name") if isinstance(data, dict) else None
    return name.strip() if isinstance(name, str) else None


def _parse_pyproject_name(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    try:
        import sys

        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib
        data = tomllib.loads(text)
    except Exception:
        # Fallback: regex
        m = re.search(r'(?m)^\s*name\s*=\s*"([^"]+)"', text)
        return m.group(1) if m else None
    for section in ("project", "tool.poetry"):
        cur: object = data
        for key in section.split("."):
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                cur = None
                break
        if isinstance(cur, dict) and isinstance(cur.get("name"), str):
            return cur["name"].strip()
    return None


def _parse_setup_name(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', text)
    return m.group(1) if m else None


def _parse_gomod_name(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r"(?m)^\s*module\s+(\S+)", text)
    return m.group(1) if m else None


def _parse_cargo_name(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    in_package = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            in_package = s == "[package]"
            continue
        if in_package:
            m = re.match(r'name\s*=\s*"([^"]+)"', s)
            if m:
                return m.group(1)
    return None


def _parse_gradle_name(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # Look for `rootProject.name = 'foo'` or `project.name = "foo"`.
    m = re.search(r"""(?:rootProject|project)\.name\s*=\s*['"]([^'"]+)['"]""", text)
    if m:
        return m.group(1)
    # Or `name = "foo"` at top level.
    m = re.search(r"""(?m)^\s*name\s*=\s*['"]([^'"]+)['"]""", text)
    return m.group(1) if m else None


def _parse_gemspec_name(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r"""\.name\s*=\s*['"]([^'"]+)['"]""", text)
    return m.group(1) if m else None


def _descriptor_module_name(descriptor_path: Path, descriptor_name: str) -> str | None:
    if descriptor_name == "pom.xml":
        return _parse_pom_artifact(descriptor_path)
    if descriptor_name == "package.json":
        return _parse_json_name(descriptor_path)
    if descriptor_name == "pyproject.toml":
        return _parse_pyproject_name(descriptor_path)
    if descriptor_name in ("setup.py", "setup.cfg"):
        return _parse_setup_name(descriptor_path)
    if descriptor_name == "go.mod":
        return _parse_gomod_name(descriptor_path)
    if descriptor_name == "Cargo.toml":
        return _parse_cargo_name(descriptor_path)
    if descriptor_name in ("build.gradle", "build.gradle.kts", "build.xml"):
        return _parse_gradle_name(descriptor_path)
    if descriptor_name.endswith(".csproj") or descriptor_name.endswith(".fsproj"):
        return Path(descriptor_name).stem
    if descriptor_name.endswith(".gemspec"):
        return _parse_gemspec_name(descriptor_path) or Path(descriptor_name).stem
    if descriptor_name == "Gemfile":
        return descriptor_path.parent.name
    return None


def resolve_module(rel_path: str, repo_root: Path | None) -> ResolvedModule:
    """Resolve the module for a changed file.

    When `repo_root` is None (no checkout available), returns a degraded module
    based on path segments so the prompt still has useful grouping.
    """
    rel = PurePosixPath(rel_path)
    if repo_root is not None:
        hit = _find_nearest_descriptor(repo_root, rel_path)
        if hit is not None:
            descriptor_path, descriptor_name = hit
            module_dir = descriptor_path.parent.relative_to(repo_root)
            name = _descriptor_module_name(descriptor_path, descriptor_name)
            if not name:
                name = module_dir.name or rel.parts[0] if rel.parts else "(root)"
            return ResolvedModule(
                module_name=name,
                module_path=str(module_dir) if str(module_dir) != "." else "",
                descriptor=descriptor_name,
            )

    # Degraded mode: use the last non-empty directory segment as the module.
    parts = [p for p in rel.parent.parts if p not in ("", ".")]
    if not parts:
        return ResolvedModule(module_name="(root)", module_path="", descriptor=None)
    # Prefer a segment that looks module-ish (common test/module roots).
    for segment in reversed(parts):
        if segment.lower() not in ("src", "main", "java", "test", "tests", "resources"):
            return ResolvedModule(
                module_name=segment,
                module_path="/".join(parts[: parts.index(segment) + 1]),
                descriptor=None,
            )
    return ResolvedModule(module_name=parts[-1], module_path="/".join(parts), descriptor=None)
