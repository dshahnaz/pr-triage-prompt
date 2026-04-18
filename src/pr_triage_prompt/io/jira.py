"""Jira loader — file-based + live REST. Tolerates empty/missing fields."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from pr_triage_prompt.models import JiraTicket


def _as_string(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip() or None
    if isinstance(v, dict):
        for key in ("name", "value", "displayName"):
            inner = v.get(key)
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
    return None


def _from_jira_payload(data: dict[str, Any]) -> JiraTicket:
    """Accept both our simplified shape and the raw Jira REST shape."""
    if not isinstance(data, dict):
        return JiraTicket()

    # Our own shape (flat).
    if "summary" in data or "description" in data or "issuetype" in data or (
        "key" in data and "fields" not in data
    ):
        return JiraTicket(
            key=_as_string(data.get("key")),
            summary=_as_string(data.get("summary")),
            description=_as_string(data.get("description")),
            issuetype=_as_string(data.get("issuetype")),
            status=_as_string(data.get("status")),
            components=[c for c in (data.get("components") or []) if isinstance(c, str)],
            labels=[lbl for lbl in (data.get("labels") or []) if isinstance(lbl, str)],
        )

    # Raw Jira REST shape: { key, fields: { summary, description, issuetype, status, ... } }
    fields = data.get("fields") or {}
    components_raw = fields.get("components") or []
    components = [_as_string(c) for c in components_raw if c]
    labels_raw = fields.get("labels") or []
    labels = [lbl for lbl in labels_raw if isinstance(lbl, str)]
    return JiraTicket(
        key=_as_string(data.get("key")),
        summary=_as_string(fields.get("summary")),
        description=_as_string(fields.get("description")),
        issuetype=_as_string(fields.get("issuetype")),
        status=_as_string(fields.get("status")),
        components=[c for c in components if c],
        labels=labels,
    )


def load_jira_file(path: Path) -> JiraTicket:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return JiraTicket()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return JiraTicket()
    if not isinstance(data, dict):
        return JiraTicket()
    return _from_jira_payload(data)


def fetch_jira_live(
    base_url: str,
    key: str,
    token: str,
    *,
    username: str | None = None,
    timeout: float = 15.0,
) -> JiraTicket:
    """Fetch a Jira issue by key. Uses basic auth if `username` is set, else bearer."""
    url = base_url.rstrip("/") + f"/rest/api/2/issue/{key}"
    if username:
        auth: tuple[str, str] | None = (username, token)
        headers: dict[str, str] = {"Accept": "application/json"}
    else:
        auth = None
        headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=timeout, headers=headers, auth=auth) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return _from_jira_payload(resp.json())
