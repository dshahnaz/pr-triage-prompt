"""Full-file analysis picks up symbols whose declarations are outside the patch hunks."""

from pathlib import Path

from pr_triage_prompt.analyzers.java import JavaAnalyzer
from pr_triage_prompt.analyzers.python import PythonAnalyzer


def test_java_modified_method_body_outside_hunk(tmp_path: Path) -> None:
    repo = tmp_path
    file_rel = Path("src/Foo.java")
    (repo / "src").mkdir(parents=True)
    full = (
        "package com.example;\n"
        "\n"
        "public class Foo {\n"
        "    public int one() { return 1; }\n"
        "    public int two() {\n"
        "        int x = 0;\n"
        "        int y = 1;\n"
        "        int z = 2;\n"
        "        return x + y + z;\n"
        "    }\n"
        "    public int three() { return 3; }\n"
        "}\n"
    )
    (repo / file_rel).write_text(full, encoding="utf-8")

    # Patch that only touches line 7 inside `two()`; git did NOT include the signature
    # in the hunk header, so the patch-only analyzer would miss `two`.
    patch = (
        "@@ -6,3 +6,3 @@\n"
        "         int x = 0;\n"
        "-        int y = 1;\n"
        "+        int y = 42;\n"
        "         int z = 2;\n"
    )
    summary = JavaAnalyzer().analyze_file(file_rel, patch, "modified", repo)
    assert "Foo" in summary.classes_changed
    assert "Foo.two" in summary.functions_changed
    # Methods NOT touched must not appear.
    assert "Foo.one" not in summary.functions_changed
    assert "Foo.three" not in summary.functions_changed
    # Package picked up from the file.
    assert summary.package == "com.example"


def test_python_modified_method_outside_hunk(tmp_path: Path) -> None:
    repo = tmp_path
    file_rel = Path("pkg/mod.py")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "__init__.py").write_text("")
    full = (
        "class A:\n"
        "    def first(self):\n"
        "        return 1\n"
        "    def second(self):\n"
        "        x = 0\n"
        "        y = 1\n"
        "        return x + y\n"
        "    def third(self):\n"
        "        return 3\n"
    )
    (repo / file_rel).write_text(full)
    # Hunk touches line 6 (`y = 1`) without showing the `def second` line.
    patch = (
        "@@ -5,3 +5,3 @@\n"
        "         x = 0\n"
        "-        y = 1\n"
        "+        y = 99\n"
        "         return x + y\n"
    )
    summary = PythonAnalyzer().analyze_file(file_rel, patch, "modified", repo)
    assert "A.second" in summary.functions_changed
    assert "A.first" not in summary.functions_changed
    assert "A.third" not in summary.functions_changed
    assert summary.package == "pkg.mod"
