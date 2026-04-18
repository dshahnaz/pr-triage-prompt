from pathlib import Path

from pr_triage_prompt.analyzers.python import PythonAnalyzer


def _analyze(patch: str, status: str = "modified"):
    return PythonAnalyzer().analyze(Path("mod.py"), patch, status)


def test_added_file_extracts_functions_and_classes() -> None:
    patch = (
        "@@ -0,0 +1,8 @@\n"
        "+def top_level():\n"
        "+    return 1\n"
        "+\n"
        "+class Foo:\n"
        "+    def bar(self):\n"
        "+        return 2\n"
        "+    async def baz(self):\n"
        "+        return 3\n"
    )
    summary = _analyze(patch, status="added")
    assert "top_level" in summary.functions_changed
    assert "Foo" in summary.classes_changed
    assert "Foo.bar" in summary.functions_changed
    assert "Foo.baz" in summary.functions_changed


def test_context_hint_catches_enclosing_function() -> None:
    patch = (
        "@@ -20,3 +20,4 @@ def process(items):\n"
        "     count = 0\n"
        "+    extra = True\n"
        "     return count\n"
    )
    summary = _analyze(patch)
    assert "process" in summary.functions_changed


def test_reported_addition_count() -> None:
    patch = (
        "@@ -1,2 +1,3 @@\n"
        " x = 1\n"
        "+y = 2\n"
        " z = 3\n"
    )
    summary = _analyze(patch)
    assert summary.additions == 1
    assert summary.deletions == 0
