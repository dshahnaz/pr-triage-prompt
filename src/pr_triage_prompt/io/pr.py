"""PR loader — file-based + live GitHub REST."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from pr_triage_prompt.models import FileChange, PullRequest

_PR_REF_RE = re.compile(r"^([A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+)#(\d+)$")
_JIRA_HINT_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


@dataclass
class PRRef:
    owner_repo: str
    number: int


def parse_pr_ref(value: str) -> PRRef | None:
    m = _PR_REF_RE.match(value.strip())
    if not m:
        return None
    return PRRef(owner_repo=m.group(1), number=int(m.group(2)))


def load_pr_file(path: Path) -> PullRequest:
    data = json.loads(path.read_text(encoding="utf-8"))
    return PullRequest.model_validate(data)


def _extract_jira_id(title: str, body: str) -> str | None:
    for text in (title, body):
        m = _JIRA_HINT_RE.search(text or "")
        if m:
            return m.group(1)
    return None


def fetch_pr_live(
    owner_repo: str,
    number: int,
    token: str,
    *,
    base_url: str = "https://api.github.com",
    timeout: float = 15.0,
) -> PullRequest:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    with httpx.Client(base_url=base_url, headers=headers, timeout=timeout) as client:
        pr_resp = client.get(f"/repos/{owner_repo}/pulls/{number}")
        pr_resp.raise_for_status()
        pr = pr_resp.json()

        files: list[dict] = []
        page = 1
        while True:
            files_resp = client.get(
                f"/repos/{owner_repo}/pulls/{number}/files",
                params={"per_page": 100, "page": page},
            )
            files_resp.raise_for_status()
            chunk = files_resp.json()
            if not isinstance(chunk, list) or not chunk:
                break
            files.extend(chunk)
            if len(chunk) < 100:
                break
            page += 1

    title = pr.get("title") or ""
    body = pr.get("body") or ""
    return PullRequest(
        number=int(pr["number"]),
        sha=pr["head"]["sha"],
        repo=owner_repo,
        title=title,
        body=body,
        jira_id=_extract_jira_id(title, body),
        files=[
            FileChange(
                filename=f.get("filename", ""),
                status=f.get("status", "modified"),
                additions=int(f.get("additions") or 0),
                deletions=int(f.get("deletions") or 0),
                patch=f.get("patch") or "",
            )
            for f in files
        ],
    )
