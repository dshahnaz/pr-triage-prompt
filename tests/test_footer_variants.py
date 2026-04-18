"""Footer variants (full vs short) + fenced markers + agent-instructions sidecar."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from pr_triage_prompt.agent_instructions import AGENT_INSTRUCTIONS, write_agent_instructions
from pr_triage_prompt.models import FileChange, PullRequest
from pr_triage_prompt.prompt import (
    AGENT_TASK_FOOTER,
    AGENT_TASK_FOOTER_SHORT,
    FOOTER_BEGIN_FULL,
    FOOTER_BEGIN_SHORT,
    FOOTER_END,
    build_prompt,
    get_footer,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _mk_pr() -> PullRequest:
    patch = "@@ -0,0 +1,3 @@\n+public class Foo {\n+}\n+\n"
    return PullRequest(
        number=1, sha="sha", repo="a/b", title="T", body="", jira_id=None,
        files=[FileChange(filename="m/Foo.java", status="added", additions=3, deletions=0, patch=patch)],
    )


def test_full_footer_is_the_default() -> None:
    md = build_prompt(_mk_pr()).markdown
    assert FOOTER_BEGIN_FULL in md
    assert FOOTER_BEGIN_SHORT not in md
    assert FOOTER_END in md
    assert "Task for the agent" in md
    assert "Output format" in md


def test_short_footer_swaps_content() -> None:
    md = build_prompt(_mk_pr(), footer="short").markdown
    assert FOOTER_BEGIN_SHORT in md
    assert FOOTER_BEGIN_FULL not in md
    assert FOOTER_END in md
    assert "## Task\n" in md
    assert "List the test cases from the KB" in md
    # Full-footer-only phrases gone.
    assert "Task for the agent" not in md
    assert "Output format" not in md


def test_short_saves_tokens() -> None:
    full = build_prompt(_mk_pr(), footer="full")
    short = build_prompt(_mk_pr(), footer="short")
    assert short.token_count < full.token_count
    # Expect at least ~50 tokens difference — the full footer is ~165 tokens longer.
    assert full.token_count - short.token_count > 50


def test_get_footer_unknown_defaults_to_full() -> None:
    assert get_footer("full") == AGENT_TASK_FOOTER
    assert get_footer("short") == AGENT_TASK_FOOTER_SHORT
    assert get_footer("bogus") == AGENT_TASK_FOOTER


def test_both_footers_are_fenced() -> None:
    for footer in (AGENT_TASK_FOOTER, AGENT_TASK_FOOTER_SHORT):
        assert footer.strip().startswith("<!-- =====")
        assert footer.strip().endswith(FOOTER_END)


def test_agent_instructions_file_has_fences(tmp_path: Path) -> None:
    p = write_agent_instructions(tmp_path / "agent-instructions.md")
    text = p.read_text(encoding="utf-8")
    assert ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>  BEGIN AGENT INSTRUCTIONS" in text
    assert "<<<<<<<<<<<<<<<<<<<<<<<<<<<<<  END AGENT INSTRUCTIONS" in text
    assert "PASTE" not in text  # we don't say PASTE; we say "Copy ONLY"
    assert "Copy ONLY" in text or "copy" in text.lower()


def test_agent_instructions_bytes_match_constant(tmp_path: Path) -> None:
    p = write_agent_instructions(tmp_path / "x.md")
    assert p.read_text(encoding="utf-8") == AGENT_INSTRUCTIONS


def _pr_json(num: int) -> str:
    return json.dumps({
        "number": num, "sha": f"s{num}", "repo": "a/b", "title": f"PR {num}",
        "body": "", "jira_id": None,
        "files": [{"filename": f"m{num}/F{num}.java", "status": "added",
                   "additions": 1, "deletions": 0, "patch": f"@@ -0,0 +1,1 @@\n+class F{num}{{}}\n"}],
    })


def test_batch_writes_agent_instructions_to_out_dir(tmp_path: Path) -> None:
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "pr_1.json").write_text(_pr_json(1))
    out = tmp_path / "out"
    res = subprocess.run(
        [sys.executable, "-m", "pr_triage_prompt.cli", "batch", str(ctx), "--out-dir", str(out)],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    assert res.returncode == 0, res.stderr
    instructions = out / "agent-instructions.md"
    assert instructions.is_file()
    text = instructions.read_text(encoding="utf-8")
    assert "BEGIN AGENT INSTRUCTIONS" in text
    assert "END AGENT INSTRUCTIONS" in text


def test_batch_no_agent_instructions_flag(tmp_path: Path) -> None:
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "pr_1.json").write_text(_pr_json(1))
    out = tmp_path / "out"
    res = subprocess.run(
        [sys.executable, "-m", "pr_triage_prompt.cli",
         "batch", str(ctx), "--out-dir", str(out), "--no-agent-instructions"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    assert res.returncode == 0, res.stderr
    assert not (out / "agent-instructions.md").exists()


def test_batch_short_footer_applies_to_all_prompts(tmp_path: Path) -> None:
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "pr_1.json").write_text(_pr_json(1))
    (ctx / "pr_2.json").write_text(_pr_json(2))
    out = tmp_path / "out"
    res = subprocess.run(
        [sys.executable, "-m", "pr_triage_prompt.cli",
         "batch", str(ctx), "--out-dir", str(out), "--footer", "short"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    assert res.returncode == 0, res.stderr
    for name in ("prompt_1.md", "prompt_2.md", "prompt.md"):
        text = (out / name).read_text(encoding="utf-8")
        assert FOOTER_BEGIN_SHORT in text
        assert FOOTER_BEGIN_FULL not in text
