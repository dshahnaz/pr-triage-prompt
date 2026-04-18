"""Byte-exact golden test: PR #23861 fixture → checked-in markdown."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PR_FIXTURE = REPO_ROOT / "examples" / "pr_23861.json"
JIRA_FIXTURE = REPO_ROOT / "examples" / "jira_VCOPS-75787.json"
GOLDEN = REPO_ROOT / "examples" / "prompt_23861.md"


def test_golden_matches(tmp_path: Path) -> None:
    out_path = tmp_path / "prompt.md"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pr_triage_prompt.cli",
            "build",
            str(PR_FIXTURE),
            "--jira-file",
            str(JIRA_FIXTURE),
            "--out",
            str(out_path),
        ],
        check=True,
        cwd=REPO_ROOT,
    )
    expected = GOLDEN.read_text(encoding="utf-8")
    actual = out_path.read_text(encoding="utf-8")
    assert actual == expected, (
        f"Golden mismatch. Regenerate with:\n"
        f"  pr-triage build {PR_FIXTURE.relative_to(REPO_ROOT)} "
        f"--jira-file {JIRA_FIXTURE.relative_to(REPO_ROOT)} "
        f"--out {GOLDEN.relative_to(REPO_ROOT)}"
    )
