import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _pr_json(number: int, jira_id: str | None, class_name: str) -> str:
    return json.dumps(
        {
            "number": number,
            "sha": f"sha{number}",
            "repo": "a/b",
            "title": f"PR {number}",
            "body": "body",
            "jira_id": jira_id,
            "files": [
                {
                    "filename": f"mod{number}/{class_name}.java",
                    "status": "added",
                    "additions": 3,
                    "deletions": 0,
                    "patch": f"@@ -0,0 +1,3 @@\n+public class {class_name} {{\n+}}\n+\n",
                }
            ],
        }
    )


def _run(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pr_triage_prompt.cli", *args],
        cwd=cwd, capture_output=True, text=True, check=False,
    )


def test_report_printed_with_tokens_and_budget(tmp_path: Path) -> None:
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "pr_1.json").write_text(_pr_json(1, "ABC-1", "Alpha"))
    (ctx / "jira_ABC-1.json").write_text(json.dumps({"key": "ABC-1", "summary": "S"}))
    out = tmp_path / "out"
    r = _run("batch", str(ctx), "--out-dir", str(out))
    assert r.returncode == 0, r.stderr
    assert "Report:" in r.stdout
    assert "Tokens" in r.stdout
    assert "Budget" in r.stdout
    assert "Over?" in r.stdout
    # The per-PR file row and the combined row should both appear.
    assert "prompt_1.md" in r.stdout
    # Combined row shown as a separate `Kind` column now, not appended to the filename.
    assert "combined" in r.stdout
    assert "Kind" in r.stdout


def test_quiet_suppresses_per_pr_lines_but_keeps_report(tmp_path: Path) -> None:
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "pr_1.json").write_text(_pr_json(1, None, "Alpha"))
    out = tmp_path / "out"
    r = _run("batch", str(ctx), "--out-dir", str(out), "--quiet")
    assert r.returncode == 0, r.stderr
    # Progress now lives on stderr; in --quiet the per-PR header + phase lines are gone.
    assert "PR #1" not in r.stderr
    # (The banner note about clone_url_template still mentions "checkouts" — that's fine;
    # --quiet suppresses progress, not the background note.)
    assert "[1/" not in r.stderr
    assert "    checkout " not in r.stderr  # indented phase label with trailing space
    # The report still goes to stdout.
    assert "Report:" in r.stdout


def test_report_json_sidecar(tmp_path: Path) -> None:
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "pr_1.json").write_text(_pr_json(1, None, "Alpha"))
    (ctx / "pr_2.json").write_text(_pr_json(2, None, "Beta"))
    out = tmp_path / "out"
    r = _run(
        "batch", str(ctx), "--out-dir", str(out),
        "--format", "json", "--combined-name", "all.md",
    )
    assert r.returncode == 0, r.stderr
    sidecar = out / "all.report.json"
    assert sidecar.is_file()
    payload = json.loads(sidecar.read_text())
    assert isinstance(payload, list)
    assert len(payload) == 3  # 2 per-PR + combined
    for row in payload:
        assert {"file", "tokens", "budget", "modules", "jira", "over"} <= row.keys()


def test_non_strict_over_budget_marked_in_report(tmp_path: Path) -> None:
    """With a deliberately tiny budget and non-strict default, content overshoots
    and the report's `Over?` column should read `yes` for the per-PR row."""
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    # Body large enough to guarantee token overflow at budget=50.
    lorem = " ".join(["lorem"] * 200)
    data = json.loads(_pr_json(1, None, "Alpha"))
    data["body"] = lorem
    (ctx / "pr_1.json").write_text(json.dumps(data))
    out = tmp_path / "out"
    r = _run(
        "batch", str(ctx), "--out-dir", str(out),
        "--token-budget", "50",
        "--emit", "per-pr",
    )
    assert r.returncode == 0, r.stderr
    # The per-PR report row (prompt_1.md) must have "yes" in the Over? column.
    lines = [line for line in r.stdout.splitlines() if "prompt_1.md" in line]
    assert lines, r.stdout
    assert "yes" in lines[0]
    # And no "additional modules omitted" line should be in the produced file.
    produced = (out / "prompt_1.md").read_text()
    assert "additional modules omitted" not in produced
