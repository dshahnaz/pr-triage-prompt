"""Discover PR + Jira fixture pairs in a context folder."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pr_triage_prompt.io.jira import _from_jira_payload, load_jira_file
from pr_triage_prompt.io.pr import load_pr_file
from pr_triage_prompt.models import JiraTicket, PullRequest


@dataclass
class ContextItem:
    pr_path: Path
    pr: PullRequest
    jira_path: Path | None
    jira: JiraTicket | None
    jira_match: str   # "filename", "content", "none"


def _scan_jira_index(ctx_dir: Path) -> dict[str, Path]:
    """Build a {jira_key: path} index by reading every jira_*.json's top-level `key`.

    Used as a fallback when the filename convention doesn't match.
    """
    idx: dict[str, Path] = {}
    for p in sorted(ctx_dir.glob("jira_*.json")):
        try:
            text = p.read_text(encoding="utf-8").strip()
            if not text:
                continue
            data = json.loads(text)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        key = data.get("key")
        if isinstance(key, str) and key and key not in idx:
            idx[key] = p
    return idx


def _match_jira(ctx_dir: Path, jira_id: str | None, index: dict[str, Path]) -> tuple[Path | None, str]:
    """Return (path, match_reason). match_reason in {"filename","content","none"}."""
    if not jira_id:
        return None, "none"
    by_name = ctx_dir / f"jira_{jira_id}.json"
    if by_name.is_file():
        return by_name, "filename"
    hit = index.get(jira_id)
    if hit is not None:
        return hit, "content"
    return None, "none"


def discover_context(ctx_dir: Path) -> list[ContextItem]:
    """List every pr_*.json in `ctx_dir`, matched to a jira_*.json when possible."""
    if not ctx_dir.is_dir():
        raise NotADirectoryError(f"not a directory: {ctx_dir}")

    jira_index = _scan_jira_index(ctx_dir)
    items: list[ContextItem] = []
    for pr_path in sorted(ctx_dir.glob("pr_*.json")):
        try:
            pr = load_pr_file(pr_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        jira_path, reason = _match_jira(ctx_dir, pr.jira_id, jira_index)
        if jira_path is None:
            jira_ticket: JiraTicket | None = None
        else:
            try:
                jira_ticket = load_jira_file(jira_path)
            except OSError:
                jira_ticket = None
                reason = "none"
            if jira_ticket is not None and not jira_ticket.has_content:
                # The file exists but is empty/placeholder — surface as "none" so the
                # caller can decide whether to still pass it through.
                pass
        items.append(
            ContextItem(
                pr_path=pr_path,
                pr=pr,
                jira_path=jira_path,
                jira=jira_ticket,
                jira_match=reason,
            )
        )
    return items


# Re-export for callers that want the raw matcher.
__all__ = ["ContextItem", "_from_jira_payload", "discover_context"]
