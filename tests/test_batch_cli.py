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


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pr_triage_prompt.cli", *args],
        cwd=cwd, capture_output=True, text=True, check=False,
    )


def test_batch_emits_per_pr_and_combined(tmp_path: Path) -> None:
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "pr_1.json").write_text(_pr_json(1, "ABC-1", "Alpha"))
    (ctx / "pr_2.json").write_text(_pr_json(2, "ABC-2", "Beta"))
    (ctx / "jira_ABC-1.json").write_text(
        json.dumps({"key": "ABC-1", "summary": "First", "issuetype": "Bug"})
    )
    # Jira for PR 2 lives under a non-conventional filename; content-match must kick in.
    (ctx / "jira_export.json").write_text(json.dumps({"key": "ABC-2", "summary": "Second"}))

    out = tmp_path / "out"
    res = _run_cli("batch", str(ctx), "--out-dir", str(out), cwd=REPO_ROOT)
    assert res.returncode == 0, res.stderr
    # Phased progress now lives on stderr; the report's Jira column uses the match reason.
    assert "filename match" in res.stderr
    assert "matched by top-level `key`" in res.stderr
    assert "filename" in res.stdout
    assert "content" in res.stdout

    assert (out / "prompt_1.md").is_file()
    assert (out / "prompt_2.md").is_file()
    assert (out / "prompt.md").is_file()

    combined = (out / "prompt.md").read_text(encoding="utf-8")
    assert combined.count("<!-- pr-triage-prompt schema v2 -->") == 1
    assert combined.count("## Task for the agent") == 1
    assert "# Batch prompt — 2 PRs" in combined
    assert "First" in combined
    assert "Second" in combined


def test_batch_per_pr_only(tmp_path: Path) -> None:
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "pr_1.json").write_text(_pr_json(1, None, "Alpha"))
    out = tmp_path / "out"
    res = _run_cli(
        "batch", str(ctx), "--out-dir", str(out), "--emit", "per-pr", cwd=REPO_ROOT
    )
    assert res.returncode == 0, res.stderr
    assert (out / "prompt_1.md").is_file()
    assert not (out / "prompt.md").exists()


def test_batch_combined_only_json_format(tmp_path: Path) -> None:
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "pr_1.json").write_text(_pr_json(1, None, "Alpha"))
    out = tmp_path / "out"
    res = _run_cli(
        "batch",
        str(ctx),
        "--out-dir",
        str(out),
        "--emit",
        "combined",
        "--combined-name",
        "all.md",
        "--format",
        "json",
        cwd=REPO_ROOT,
    )
    assert res.returncode == 0, res.stderr
    assert (out / "all.json").is_file()
    payload = json.loads((out / "all.json").read_text())
    assert "modules" in payload
    assert "files" in payload
    assert "token_count" in payload


def test_batch_errors_on_empty_dir(tmp_path: Path) -> None:
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    out = tmp_path / "out"
    res = _run_cli("batch", str(ctx), "--out-dir", str(out), cwd=REPO_ROOT)
    assert res.returncode == 1
    assert "no pr_*.json" in res.stderr
