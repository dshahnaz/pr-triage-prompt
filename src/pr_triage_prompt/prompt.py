"""Scrub, assemble, and budget the Markdown prompt."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pr_triage_prompt.analyzers import analyze_with_repo, get_analyzer
from pr_triage_prompt.models import (
    FileChangeSummary,
    JiraTicket,
    ModuleSummary,
    PromptBundle,
    PullRequest,
)
from pr_triage_prompt.modules import resolve_module

SCHEMA_MARKER = "<!-- pr-triage-prompt schema v2 -->"

AGENT_TASK_FOOTER = (
    "## Task for the agent\n"
    "\n"
    "You have access to a knowledge base of test-suite documents. Each document has a "
    "top-level suite name, a `## Components` section, and a `## Test Coverage` section "
    "with per-case entries under `### testXxx` headers describing **Purpose**, "
    "**Key Operations**, and **API Endpoints**.\n"
    "\n"
    "Using **only** the retrieved test-suite context, list which **test cases** are "
    "most likely to exercise the code changed above. Lean on the *Retrieval keys* "
    "section (components, packages, classes, operations) and the Jira components to "
    "match against suite `## Components` and per-case `**Key Operations**` /"
    " `**API Endpoints**` lines.\n"
    "\n"
    "**Output format** — one line per case, exactly:\n"
    "\n"
    "    <SuiteName> → <testCaseName> — <one-sentence justification citing a specific "
    "class, function, operation, or component from the changes above>\n"
    "\n"
    "Rules:\n"
    "- Do not invent test names. If nothing in the KB is relevant, reply exactly `none`.\n"
    "- Prefer coverage: include every case that plausibly exercises any changed class "
    "or operation — do not stop at the single best match.\n"
    "- Do not include setup/fixture cases unless they directly exercise the change.\n"
)

_SECTION_BOUNDARY = re.compile(r"(?m)^\s*##\s+\S")


def scrub_pr_body(body: str) -> str:
    """Keep only the human-written Change Description; drop pipeline/auto-merge/AI-assisted boilerplate."""
    if not body:
        return ""
    text = body.replace("\r\n", "\n").replace("\r", "\n")

    # Drop any `## Auto-merge`, `## Pipeline parameters`, `## Change Tracking ID` block
    # up to the next `## ` header or end-of-string.
    drop_headers = {"auto-merge", "pipeline parameters", "change tracking id"}
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^\s*##\s+(.*?)\s*#*\s*$", line)
        if m and m.group(1).strip().rstrip(".").lower() in drop_headers:
            i += 1
            while i < len(lines) and not re.match(r"^\s*##\s+\S", lines[i]):
                i += 1
            continue
        out.append(line)
        i += 1

    result = "\n".join(out)
    # Drop trailing `AI-Assisted (%): ...` line.
    result = re.sub(r"\n+AI-Assisted \(.+?\):.*$", "", result, flags=re.IGNORECASE | re.DOTALL)
    return result.strip() + "\n"


def _group_files_by_module(summaries: list[FileChangeSummary]) -> list[ModuleSummary]:
    ordered: list[ModuleSummary] = []
    index: dict[tuple[str, str], ModuleSummary] = {}
    for f in summaries:
        key = (f.module_path or "", f.module_name or "")
        module = index.get(key)
        if module is None:
            module = ModuleSummary(
                module_name=f.module_name or "(unknown)",
                module_path=f.module_path or "",
                language=f.language,
                files=[],
            )
            index[key] = module
            ordered.append(module)
        module.files.append(f)
    return ordered


def _format_header(
    pr: PullRequest,
    jira: JiraTicket | None,
    file_summaries: list[FileChangeSummary],
) -> list[str]:
    jira_id = pr.jira_id or "—"
    lines = [
        SCHEMA_MARKER,
        "",
        f"# PR #{pr.number} — {pr.title}",
        "",
        f"**Repo:** {pr.repo}   **SHA:** {pr.sha}   **Jira:** {jira_id}",
    ]
    components = jira.components if (jira and jira.components) else []
    if components:
        lines.append(f"**Components:** {', '.join(components)}")
    packages = sorted({f.package for f in file_summaries if f.package})
    if packages:
        lines.append(f"**Packages:** {', '.join(packages)}")
    lines.append("")
    return lines


def _format_jira_block(jira: JiraTicket | None) -> list[str]:
    lines: list[str] = ["## Jira ticket", ""]
    if jira is None or not jira.has_content:
        lines.append("_(no Jira ticket data supplied)_")
        lines.append("")
        return lines
    if jira.summary:
        lines.append(f"**Summary:** {jira.summary}")
        lines.append("")
    if jira.description:
        lines.append(jira.description.strip())
        lines.append("")
    meta = []
    if jira.issuetype:
        meta.append(f"Type: {jira.issuetype}")
    if jira.status:
        meta.append(f"Status: {jira.status}")
    if jira.components:
        meta.append(f"Components: {', '.join(jira.components)}")
    if jira.labels:
        meta.append(f"Labels: {', '.join(jira.labels)}")
    if meta:
        lines.append("_" + "  |  ".join(meta) + "_")
        lines.append("")
    return lines


def _format_pr_body(pr: PullRequest) -> list[str]:
    scrubbed = scrub_pr_body(pr.body)
    return ["## PR description", "", scrubbed.rstrip(), ""]


def _format_summary_table(modules: list[ModuleSummary]) -> list[str]:
    lines = [
        "## Changes — summary",
        "",
        "| Module | Language | Files | Classes changed | Functions changed | +/- |",
        "|---|---|---|---|---|---|",
    ]
    for m in modules:
        classes = ", ".join(m.classes_changed) or "—"
        funcs = ", ".join(m.functions_changed) or "—"
        module_cell = m.module_name
        if m.module_path:
            module_cell += f" (`{m.module_path}`)"
        lines.append(
            f"| {module_cell} | {m.language} | {len(m.files)} | {classes} | {funcs} "
            f"| +{m.additions}/-{m.deletions} |"
        )
    lines.append("")
    return lines


def _format_module_section(module: ModuleSummary) -> list[str]:
    header = f"### {module.module_name}"
    if module.module_path:
        header += f" (`{module.module_path}`)"
    lines: list[str] = [header, ""]
    for f in module.files:
        delta = f"+{f.additions}/-{f.deletions}"
        lines.append(f"- `{f.path}` ({f.status}, {delta})")
        if f.package:
            lines.append(f"    - Package: `{f.package}`")
        if f.classes_changed:
            lines.append(f"    - Classes: {', '.join(f'`{c}`' for c in f.classes_changed)}")
        if f.functions_changed:
            lines.append(
                f"    - Functions/methods: {', '.join(f'`{fn}`' for fn in f.functions_changed)}"
            )
        if f.excerpt:
            lines.append("    - Excerpt:")
            for row in f.excerpt.splitlines():
                lines.append(f"      `{row.rstrip()}`")
    lines.append("")
    return lines


def _format_retrieval_keys(
    jira: JiraTicket | None,
    file_summaries: list[FileChangeSummary],
) -> list[str]:
    components = jira.components if (jira and jira.components) else []
    packages = sorted({f.package for f in file_summaries if f.package})
    classes: list[str] = []
    seen_c: set[str] = set()
    funcs: list[str] = []
    seen_f: set[str] = set()
    for f in file_summaries:
        for c in f.classes_changed:
            if c not in seen_c:
                seen_c.add(c)
                classes.append(c)
        for fn in f.functions_changed:
            if fn not in seen_f:
                seen_f.add(fn)
                funcs.append(fn)
    if not (components or packages or classes or funcs):
        return []
    lines = ["## Retrieval keys (for the test-suite knowledge base)", ""]
    if components:
        lines.append(f"- Components: {', '.join(components)}")
    if packages:
        lines.append(f"- Packages: {', '.join(packages)}")
    if classes:
        lines.append(f"- Classes: {', '.join(classes)}")
    if funcs:
        lines.append(f"- Operations: {', '.join(funcs)}")
    lines.append("")
    return lines


def _format_dropped(modules: list[ModuleSummary]) -> list[str]:
    if not modules:
        return []
    names = ", ".join(m.module_name for m in modules)
    return [f"_{len(modules)} additional modules omitted for budget: {names}_", ""]


def _token_counter():
    """Return a callable `counter(text) -> int`.

    Default: deterministic word-based estimate (1 token ≈ 0.75 words) — keeps the CLI
    offline and reproducible. Opt into a HuggingFace tokenizer by setting the
    PR_TRIAGE_TOKENIZER env var to a model name (e.g. ``BAAI/bge-small-en-v1.5``).
    """
    import os

    model = os.environ.get("PR_TRIAGE_TOKENIZER", "").strip()
    if model:
        try:
            from tokenizers import Tokenizer

            tok = Tokenizer.from_pretrained(model)

            def count(text: str) -> int:
                return len(tok.encode(text).ids)

            return count
        except Exception:
            pass
    return lambda text: max(1, int(len(text.split()) / 0.75))


def _analyze_files(pr: PullRequest, repo_root: Path | None) -> list[FileChangeSummary]:
    summaries: list[FileChangeSummary] = []
    for f in pr.files:
        analyzer = get_analyzer(f.filename)
        if analyzer is None:
            summary = FileChangeSummary(
                path=f.filename,
                language="Other",
                status=f.status,
                additions=f.additions,
                deletions=f.deletions,
            )
        else:
            summary = analyze_with_repo(analyzer, Path(f.filename), f.patch, f.status, repo_root)
            # Prefer the GitHub-provided counts when the analyzer saw fewer + lines
            # than the PR metadata promised (happens for binary/rename patches).
            summary.additions = max(summary.additions, f.additions)
            summary.deletions = max(summary.deletions, f.deletions)
        module = resolve_module(f.filename, repo_root, hint_name=summary.package)
        summary.module_name = module.module_name
        summary.module_path = module.module_path
        summaries.append(summary)
    return summaries


def _render_pr_body(
    pr: PullRequest,
    jira: JiraTicket | None,
    modules: list[ModuleSummary],
    file_summaries: list[FileChangeSummary],
    *,
    token_budget: int,
    count,
    include_header_marker: bool = True,
    strict_budget: bool = False,
) -> tuple[str, list[ModuleSummary]]:
    """Render one PR's markdown block (no agent-task footer).

    If `include_header_marker` is False, the leading schema marker is omitted — the caller
    is expected to supply it once at the top of the document. When `strict_budget` is
    False (default) every module is emitted in full regardless of `token_budget`.

    Returns (markdown, dropped_modules).
    """
    head: list[str] = []
    for line in _format_header(pr, jira, file_summaries):
        if line == SCHEMA_MARKER and not include_header_marker:
            continue
        head.append(line)
    head.extend(_format_jira_block(jira))
    head.extend(_format_pr_body(pr))
    head.extend(_format_summary_table(modules))
    head.extend(_format_retrieval_keys(jira, file_summaries))

    head_text = "\n".join(head)

    rendered_modules: list[str] = []
    dropped: list[ModuleSummary] = []
    if strict_budget:
        head_tokens = count(head_text)
        remaining = token_budget - head_tokens
        for m in modules:
            block = "\n".join(_format_module_section(m))
            block_tokens = count(block)
            if block_tokens <= remaining:
                rendered_modules.append(block)
                remaining -= block_tokens
            else:
                dropped.append(m)
    else:
        for m in modules:
            rendered_modules.append("\n".join(_format_module_section(m)))

    body_parts: list[str] = [head_text.rstrip(), ""]
    if rendered_modules:
        body_parts.append("\n".join(rendered_modules).rstrip())
        body_parts.append("")
    body_parts.extend(_format_dropped(dropped))
    return "\n".join(body_parts).rstrip() + "\n", dropped


def build_prompt(
    pr: PullRequest,
    jira: JiraTicket | None = None,
    *,
    repo_root: Path | None = None,
    token_budget: int = 4000,
    strict_budget: bool = False,
) -> PromptBundle:
    """Build the Markdown prompt + structured bundle.

    By default nothing is trimmed — `token_budget` is reported as an informational
    target. Pass `strict_budget=True` to drop overflowing modules into a one-line
    summary (the historic behavior).
    """
    file_summaries = _analyze_files(pr, repo_root)
    modules = _group_files_by_module(file_summaries)

    count = _token_counter()
    footer_tokens = count(AGENT_TASK_FOOTER)
    body_md, dropped = _render_pr_body(
        pr, jira, modules, file_summaries,
        token_budget=token_budget - footer_tokens,
        count=count,
        strict_budget=strict_budget,
    )

    markdown = body_md + "\n" + AGENT_TASK_FOOTER.rstrip() + "\n"
    token_count = count(markdown)

    return PromptBundle(
        markdown=markdown,
        modules=modules,
        files=file_summaries,
        dropped_modules=[m.module_name for m in dropped],
        token_count=token_count,
        token_budget=token_budget,
    )


@dataclass
class BatchItem:
    """One PR+Jira pair passed to `build_combined_prompt`."""

    pr: PullRequest
    jira: JiraTicket | None = None
    repo_root: Path | None = None


def build_combined_prompt(
    items: list[BatchItem],
    *,
    token_budget: int = 16000,
    per_pr_token_budget: int = 4000,
    strict_budget: bool = False,
) -> PromptBundle:
    """Build one combined prompt covering many PRs with a single agent-task footer.

    By default every PR is emitted in full and the budgets are informational targets.
    When `strict_budget=True`, each PR's module list is greedy-packed against
    `per_pr_token_budget` and PRs that don't fit the remaining `token_budget` are
    collapsed to a one-line "N additional PRs omitted" notice.
    """
    count = _token_counter()
    footer_tokens = count(AGENT_TASK_FOOTER)
    header_parts = [
        SCHEMA_MARKER,
        "",
        f"# Batch prompt — {len(items)} PR{'s' if len(items) != 1 else ''}",
        "",
    ]
    repos = sorted({it.pr.repo for it in items if it.pr.repo})
    if repos:
        header_parts.append("**Repos:** " + ", ".join(repos))
    components_in_scope: list[str] = []
    seen_c: set[str] = set()
    for it in items:
        if it.jira and it.jira.components:
            for c in it.jira.components:
                if c not in seen_c:
                    seen_c.add(c)
                    components_in_scope.append(c)
    if components_in_scope:
        header_parts.append("**Components in scope:** " + ", ".join(components_in_scope))
    header_parts.append("")
    header_md = "\n".join(header_parts)
    header_tokens = count(header_md)

    remaining = token_budget - header_tokens - footer_tokens
    rendered: list[str] = []
    all_files: list[FileChangeSummary] = []
    all_modules: list[ModuleSummary] = []
    dropped_prs: list[tuple[int, str | None]] = []
    total_dropped_modules: list[str] = []

    for item in items:
        file_summaries = _analyze_files(item.pr, item.repo_root)
        modules = _group_files_by_module(file_summaries)
        body_md, dropped_modules = _render_pr_body(
            item.pr, item.jira, modules, file_summaries,
            token_budget=per_pr_token_budget,
            count=count,
            include_header_marker=False,
            strict_budget=strict_budget,
        )
        body_md = "---\n\n" + body_md
        if strict_budget:
            block_tokens = count(body_md)
            if block_tokens > remaining:
                dropped_prs.append((item.pr.number, item.pr.jira_id))
                continue
            remaining -= block_tokens
        rendered.append(body_md)
        all_files.extend(file_summaries)
        all_modules.extend(modules)
        total_dropped_modules.extend(m.module_name for m in dropped_modules)

    omitted_line = ""
    if dropped_prs:
        parts = [f"#{n}" + (f" ({j})" if j else "") for n, j in dropped_prs]
        omitted_line = (
            f"\n---\n\n_{len(dropped_prs)} additional PR"
            f"{'s' if len(dropped_prs) != 1 else ''} omitted for budget: "
            f"{', '.join(parts)}_\n"
        )

    parts = [header_md.rstrip(), ""]
    if rendered:
        parts.append("\n".join(rendered).rstrip())
        parts.append("")
    if omitted_line:
        parts.append(omitted_line.rstrip())
        parts.append("")
    parts.append(AGENT_TASK_FOOTER.rstrip())
    parts.append("")

    markdown = "\n".join(parts)
    token_count = count(markdown)

    return PromptBundle(
        markdown=markdown,
        modules=all_modules,
        files=all_files,
        dropped_modules=[f"PR #{n}" for n, _ in dropped_prs] + total_dropped_modules,
        token_count=token_count,
        token_budget=token_budget,
    )
