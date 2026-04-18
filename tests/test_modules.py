from pathlib import Path

from pr_triage_prompt.modules import resolve_module


def _mk_pom(path: Path, artifact: str) -> None:
    path.write_text(
        f"<project><artifactId>{artifact}</artifactId></project>\n",
        encoding="utf-8",
    )


def test_resolve_pom_walk_up(tmp_path: Path) -> None:
    (tmp_path / "mod" / "src" / "main" / "java" / "com" / "x").mkdir(parents=True)
    _mk_pom(tmp_path / "mod" / "pom.xml", "my-module")
    m = resolve_module("mod/src/main/java/com/x/Foo.java", tmp_path)
    assert m.descriptor == "pom.xml"
    assert m.module_name == "my-module"
    assert m.module_path == "mod"


def test_nested_pom_picks_nearest(tmp_path: Path) -> None:
    (tmp_path / "outer" / "inner" / "src").mkdir(parents=True)
    _mk_pom(tmp_path / "outer" / "pom.xml", "outer-artifact")
    _mk_pom(tmp_path / "outer" / "inner" / "pom.xml", "inner-artifact")
    m = resolve_module("outer/inner/src/Foo.java", tmp_path)
    assert m.module_name == "inner-artifact"


def test_pom_with_parent_block_skips_parent_artifact(tmp_path: Path) -> None:
    (tmp_path / "mod").mkdir(parents=True)
    (tmp_path / "mod" / "pom.xml").write_text(
        "<project>\n"
        "  <parent>\n"
        "    <artifactId>parent-artifact</artifactId>\n"
        "  </parent>\n"
        "  <artifactId>child-artifact</artifactId>\n"
        "</project>\n",
        encoding="utf-8",
    )
    m = resolve_module("mod/Foo.java", tmp_path)
    assert m.module_name == "child-artifact"


def test_package_json_name(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "package.json").write_text(
        '{"name": "@scope/thing", "version": "1.0.0"}', encoding="utf-8"
    )
    m = resolve_module("pkg/src/index.ts", tmp_path)
    assert m.module_name == "@scope/thing"
    assert m.descriptor == "package.json"


def test_pyproject_project_name(tmp_path: Path) -> None:
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "pyproject.toml").write_text(
        '[project]\nname = "libname"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    m = resolve_module("lib/src/mod.py", tmp_path)
    assert m.module_name == "libname"


def test_go_mod(tmp_path: Path) -> None:
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "go.mod").write_text(
        "module github.com/example/svc\n\ngo 1.22\n", encoding="utf-8"
    )
    m = resolve_module("svc/main.go", tmp_path)
    assert m.module_name == "github.com/example/svc"


def test_degraded_mode_uses_path_segment() -> None:
    m = resolve_module("ops/tests/dev/VCFPasswordManagement/src/main/java/Foo.java", None)
    # Should pick VCFPasswordManagement (skips src/main/java).
    assert m.module_name == "VCFPasswordManagement"
    assert m.descriptor is None


def test_degraded_mode_root_file() -> None:
    m = resolve_module("Foo.java", None)
    assert m.module_name == "(root)"
