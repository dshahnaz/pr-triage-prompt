"""Typer CLI for pr-triage-prompt."""

from __future__ import annotations

import json
import sys
from enum import Enum
from pathlib import Path

import typer

from pr_triage_prompt import __version__, log
from pr_triage_prompt.checkout import clear_cache, ensure_checkout, list_cache
from pr_triage_prompt.config import Config, load_config
from pr_triage_prompt.io.batch import discover_context
from pr_triage_prompt.io.jira import fetch_jira_live, load_jira_file
from pr_triage_prompt.io.pr import fetch_pr_live, load_pr_file, parse_pr_ref
from pr_triage_prompt.models import JiraTicket, PullRequest
from pr_triage_prompt.prompt import BatchItem, build_combined_prompt, build_prompt

app = typer.Typer(
    add_completion=False,
    help="Turn a GitHub PR + Jira ticket into a Markdown prompt for an LLM agent.",
    no_args_is_help=True,
)
cache_app = typer.Typer(add_completion=False, help="Manage the sparse-checkout cache.")
app.add_typer(cache_app, name="cache")


class OutputFormat(str, Enum):
    md = "md"
    json = "json"


class EmitMode(str, Enum):
    per_pr = "per-pr"
    combined = "combined"
    both = "both"


class ReportPaths(str, Enum):
    rel = "rel"
    abs = "abs"


def _apply_log_flags(quiet: bool, verbose: bool, no_color: bool) -> None:
    log.set_quiet(quiet)
    log.set_verbose(verbose)
    if no_color:
        log.set_color(False)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"pr-triage {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print version and exit.",
    ),
) -> None:
    if ctx.invoked_subcommand is None and not version:
        typer.echo(ctx.get_help())
        raise typer.Exit()


def _load_pr(pr_ref: str, cfg: Config) -> PullRequest:
    parsed = parse_pr_ref(pr_ref)
    if parsed is None:
        path = Path(pr_ref).expanduser()
        if not path.is_file():
            typer.echo(f"error: '{pr_ref}' is neither owner/repo#number nor an existing file", err=True)
            raise typer.Exit(2)
        return load_pr_file(path)
    token = cfg.github_token()
    if not token:
        typer.echo(
            f"error: live PR fetch needs a GitHub token in ${cfg.github_token_env}",
            err=True,
        )
        raise typer.Exit(2)
    return fetch_pr_live(parsed.owner_repo, parsed.number, token)


def _maybe_checkout(
    cfg: Config, pr_repo: str, pr_sha: str, file_paths: list[str], no_cache: bool
) -> tuple[Path | None, str]:
    """Return (repo_root, status) where status is 'yes' | 'no' | 'fail'.

    Progress is routed through ``log.phase("checkout", …)``; git auth is injected
    automatically from the configured token env var (see ``Config.git_token_for``).
    """
    clone_url = cfg.resolved_clone_url(pr_repo)
    if clone_url is None:
        log.phase("checkout", "skipped (no clone_url_template set)")
        return None, "no"

    def _on_phase(event: str, msg: str) -> None:
        log.phase("checkout", msg)

    def _verbose_cmd(cmd: list[str]) -> None:
        log.verbose("$ " + " ".join(cmd))

    token = cfg.git_token_for(clone_url)
    try:
        repo_root = ensure_checkout(
            cache_root=cfg.resolved_cache_dir(),
            repo=pr_repo,
            sha=pr_sha,
            clone_url=clone_url,
            paths=file_paths,
            no_cache=no_cache,
            git_token=token,
            on_phase=_on_phase,
            verbose_cmd=_verbose_cmd,
        )
        return repo_root, "yes"
    except Exception as exc:
        stderr_tail = ""
        if hasattr(exc, "stderr") and exc.stderr:  # CalledProcessError
            stderr_tail = " :: " + str(exc.stderr).strip().splitlines()[-1][:200]
        log.warn(
            f"sparse checkout failed for {pr_repo}@{pr_sha[:12]} "
            f"({type(exc).__name__}){stderr_tail}"
        )
        return None, "fail"


def _load_jira(
    jira_file: Path | None, jira_key: str | None, cfg: Config, pr_hint: str | None
) -> JiraTicket | None:
    if jira_file is not None:
        return load_jira_file(jira_file)
    key = jira_key or pr_hint
    if not key:
        return None
    if not cfg.jira_base_url:
        return None
    token = cfg.jira_token()
    if not token:
        typer.echo(
            f"warning: Jira key {key} available but ${cfg.jira_token_env} is unset; skipping Jira fetch",
            err=True,
        )
        return None
    return fetch_jira_live(cfg.jira_base_url, key, token, username=cfg.jira_username)


@app.command("build")
def build(
    pr_ref: str = typer.Argument(..., help="PR JSON path, or owner/repo#number for live fetch."),
    jira_file: Path | None = typer.Option(None, "--jira-file", help="Jira ticket JSON path."),
    jira_key: str | None = typer.Option(None, "--jira", help="Jira key for live fetch."),
    out: Path | None = typer.Option(None, "--out", help="Output file path."),
    fmt: OutputFormat = typer.Option(OutputFormat.md, "--format", help="Output format."),
    token_budget: int | None = typer.Option(
        None, "--token-budget", help="Override token budget (informational by default)."
    ),
    strict_budget: bool = typer.Option(
        False,
        "--strict-budget",
        help="Drop overflowing modules to stay near the budget (old behavior).",
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="Force-refresh the sparse-checkout cache."),
    clone_url: str | None = typer.Option(
        None,
        "--clone-url",
        help="Git URL template (with `{repo}`) for the sparse checkout. "
        "Overrides `clone_url_template` in ~/.pr-triage/config.toml.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print git commands + per-file analyzer timings."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable colored output."),
) -> None:
    """Build a Markdown prompt from a PR (+ Jira ticket)."""
    _apply_log_flags(quiet=False, verbose=verbose, no_color=no_color)
    cfg = load_config()
    if clone_url:
        cfg.clone_url_template = clone_url
    if cfg.clone_url_template is None:
        log.note(
            "no clone_url_template set in ~/.pr-triage/config.toml; sparse checkouts are skipped "
            "(module names + modified-function detection degraded)."
        )
    pr = _load_pr(pr_ref, cfg)
    jira = _load_jira(jira_file, jira_key, cfg, pr.jira_id)

    repo_root, _ = _maybe_checkout(cfg, pr.repo, pr.sha, [f.filename for f in pr.files], no_cache)

    budget = token_budget or cfg.default_token_budget
    bundle = build_prompt(
        pr, jira, repo_root=repo_root, token_budget=budget, strict_budget=strict_budget,
    )

    if fmt is OutputFormat.md:
        payload = bundle.markdown
    else:
        payload = json.dumps(bundle.json_payload, indent=2, sort_keys=True) + "\n"

    if out is None:
        sys.stdout.write(payload)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        dropped_note = (
            f" · {len(bundle.dropped_modules)} dropped" if bundle.dropped_modules else ""
        )
        modules_word = "module" if len(bundle.modules) == 1 else "modules"
        log.info(
            f"wrote {out}  —  {bundle.token_count} tokens / "
            f"budget {bundle.token_budget} · {len(bundle.modules)} {modules_word}{dropped_note}"
        )


@app.command("batch")
def batch(
    context_dir: Path = typer.Argument(
        ..., exists=True, file_okay=False, dir_okay=True,
        help="Folder containing pr_*.json and jira_*.json fixtures.",
    ),
    out_dir: Path = typer.Option(..., "--out-dir", help="Directory to write prompts into."),
    emit: EmitMode = typer.Option(
        EmitMode.both, "--emit", help="What to emit: per-pr, combined, or both.",
    ),
    combined_name: str = typer.Option(
        "prompt.md", "--combined-name", help="Filename for the combined prompt."
    ),
    token_budget: int | None = typer.Option(
        None, "--token-budget", help="Per-PR token budget (informational by default)."
    ),
    combined_budget: int = typer.Option(
        16000, "--combined-budget", help="Token budget for the combined prompt."
    ),
    strict_budget: bool = typer.Option(
        False,
        "--strict-budget",
        help="Drop overflowing modules/PRs to stay near budgets (old behavior).",
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="Force-refresh the sparse-checkout cache."),
    clone_url: str | None = typer.Option(
        None,
        "--clone-url",
        help="Git URL template (with `{repo}`) for the sparse checkout. "
        "Overrides `clone_url_template` in ~/.pr-triage/config.toml.",
    ),
    fmt: OutputFormat = typer.Option(OutputFormat.md, "--format", help="Output format."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress per-PR progress lines; always prints the final report."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print git commands + per-file analyzer timings."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable colored output."),
    report_paths: ReportPaths = typer.Option(
        ReportPaths.rel, "--report-paths",
        help="Show paths in the report as rel (relative to --out-dir) or abs.",
    ),
) -> None:
    """Build prompts from every pr_*.json in a context folder.

    For each PR, looks up its Jira ticket by `jira_<jira_id>.json` (with a content-based
    fallback on the `key` field). Writes per-PR files and/or one combined prompt.
    """
    _apply_log_flags(quiet=quiet, verbose=verbose, no_color=no_color)
    cfg = load_config()
    if clone_url:
        cfg.clone_url_template = clone_url
    items = discover_context(context_dir)
    if not items:
        log.error(f"no pr_*.json files in {context_dir}")
        raise typer.Exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    budget = token_budget or cfg.default_token_budget

    log.info(
        f"pr-triage {__version__}  ·  {len(items)} PR{'s' if len(items) != 1 else ''} "
        f"in {context_dir}  →  {out_dir}"
    )
    if cfg.clone_url_template is None:
        log.note(
            "no clone_url_template set in ~/.pr-triage/config.toml; sparse checkouts are skipped "
            "(module names + modified-function detection degraded)."
        )

    # Per-PR pass.
    report_rows: list[dict[str, object]] = []
    batch_items: list[BatchItem] = []
    matched_with_content = 0
    total = len(items)
    for idx, item in enumerate(items, start=1):
        title = item.pr.title
        if len(title) > 70:
            title = title[:67] + "…"
        log.progress(f"[{idx}/{total}] PR #{item.pr.number}  {item.pr.repo}  \"{title}\"")

        repo_root, checkout_status = _maybe_checkout(
            cfg, item.pr.repo, item.pr.sha, [f.filename for f in item.pr.files], no_cache
        )
        jira_note = item.jira_match
        if item.jira is not None and item.jira.has_content:
            matched_with_content += 1
        if item.pr.jira_id:
            if jira_note == "filename":
                log.phase("jira", f"{item.pr.jira_id} → jira_{item.pr.jira_id}.json (filename match)")
            elif jira_note == "content":
                log.phase("jira", f"{item.pr.jira_id} → matched by top-level `key` in another jira_*.json")
            else:
                log.phase("jira", f"{item.pr.jira_id} — no matching jira_*.json in context")
        else:
            log.phase("jira", "no Jira ID in PR")

        bundle = build_prompt(
            item.pr, item.jira,
            repo_root=repo_root, token_budget=budget, strict_budget=strict_budget,
        )
        batch_items.append(BatchItem(pr=item.pr, jira=item.jira, repo_root=repo_root))

        if emit in (EmitMode.per_pr, EmitMode.both):
            if fmt is OutputFormat.md:
                pr_out = out_dir / f"prompt_{item.pr.number}.md"
                pr_out.write_text(bundle.markdown, encoding="utf-8")
            else:
                pr_out = out_dir / f"prompt_{item.pr.number}.json"
                pr_out.write_text(
                    json.dumps(bundle.json_payload, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            modules_word = "module" if len(bundle.modules) == 1 else "modules"
            files_word = "file" if len(item.pr.files) == 1 else "files"
            dropped_tag = (
                f" · {len(bundle.dropped_modules)} dropped" if bundle.dropped_modules else ""
            )
            log.phase(
                "wrote",
                f"{pr_out.name}  —  {bundle.token_count} tokens · "
                f"{len(bundle.modules)} {modules_word} · {len(item.pr.files)} {files_word}"
                f"{dropped_tag}",
            )
            report_rows.append({
                "file": str(pr_out),
                "kind": "per-pr",
                "tokens": bundle.token_count,
                "budget": bundle.token_budget,
                "modules": len(bundle.modules),
                "files": len(item.pr.files),
                "jira": jira_note,
                "checkout": checkout_status,
                "over": bundle.token_count > bundle.token_budget,
                "pr_number": item.pr.number,
            })

    # Combined pass.
    if emit in (EmitMode.combined, EmitMode.both):
        combined = build_combined_prompt(
            batch_items,
            token_budget=combined_budget,
            per_pr_token_budget=budget,
            strict_budget=strict_budget,
        )
        if fmt is OutputFormat.md:
            combined_path = out_dir / combined_name
            combined_path.write_text(combined.markdown, encoding="utf-8")
        else:
            combined_path = out_dir / (Path(combined_name).stem + ".json")
            combined_path.write_text(
                json.dumps(combined.json_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        dropped_prs = sum(1 for m in combined.dropped_modules if m.startswith("PR #"))
        log.progress(
            f"combined: {combined_path.name}  —  {combined.token_count} tokens / "
            f"budget {combined.token_budget}"
            + (f" · {dropped_prs} PRs dropped" if dropped_prs else "")
        )
        report_rows.append({
            "file": str(combined_path),
            "kind": "combined",
            "tokens": combined.token_count,
            "budget": combined.token_budget,
            "modules": len(combined.modules),
            "files": sum(len(it.pr.files) for it in items),
            "jira": f"{matched_with_content}/{len(items)} matched",
            "checkout": "",
            "over": combined.token_count > combined.token_budget,
            "pr_number": None,
        })

    _print_report(report_rows, out_dir=out_dir, relative=(report_paths is ReportPaths.rel))

    if fmt is OutputFormat.json:
        sidecar = out_dir / (Path(combined_name).stem + ".report.json")
        sidecar.write_text(
            json.dumps(report_rows, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _truncate_file(path: str, width: int = 60) -> str:
    if len(path) <= width:
        return path
    return "…" + path[-(width - 1):]


def _render_path(raw: str, out_dir: Path, relative: bool) -> str:
    if not relative:
        return _truncate_file(raw)
    # Resolve both sides so symlinks like /tmp → /private/tmp don't block the match.
    try:
        raw_resolved = Path(raw).resolve()
        base_resolved = out_dir.resolve()
        rel = raw_resolved.relative_to(base_resolved)
        return str(rel)
    except (ValueError, OSError):
        return _truncate_file(raw)


def _print_report(
    rows: list[dict[str, object]],
    *,
    out_dir: Path,
    relative: bool,
) -> None:
    """Fixed-width report (stdout): Prompt | Kind | Tokens | Budget | Files | Modules | Checkout | Jira | Over?."""
    if not rows:
        return
    display_rows: list[dict[str, str]] = []
    for r in rows:
        display_rows.append(
            {
                "file": _render_path(str(r["file"]), out_dir, relative),
                "kind": str(r.get("kind", "")),
                "tokens": str(r["tokens"]),
                "budget": str(r["budget"]),
                "files": str(r.get("files", "")),
                "modules": str(r["modules"]),
                "checkout": str(r.get("checkout", "")),
                "jira": str(r["jira"]),
                "over": "yes" if r["over"] else "",
            }
        )
    headers = {
        "file": "Prompt",
        "kind": "Kind",
        "tokens": "Tokens",
        "budget": "Budget",
        "files": "Files",
        "modules": "Modules",
        "checkout": "Checkout",
        "jira": "Jira",
        "over": "Over?",
    }
    widths = {
        k: max(len(headers[k]), *(len(row[k]) for row in display_rows))
        for k in headers
    }

    def _fmt(row: dict[str, str]) -> str:
        return (
            f"  {row['file']:<{widths['file']}}"
            f"  {row['kind']:<{widths['kind']}}"
            f"  {row['tokens']:>{widths['tokens']}}"
            f"  {row['budget']:>{widths['budget']}}"
            f"  {row['files']:>{widths['files']}}"
            f"  {row['modules']:>{widths['modules']}}"
            f"  {row['checkout']:<{widths['checkout']}}"
            f"  {row['jira']:<{widths['jira']}}"
            f"  {row['over']:<{widths['over']}}"
        )

    print("", flush=True)
    print("Report:")
    print(_fmt(headers))
    sep = {k: "-" * widths[k] for k in headers}
    print(_fmt(sep))
    for row in display_rows:
        print(_fmt(row))


@cache_app.command("list")
def cache_list() -> None:
    """List cached per-repo clones."""
    cfg = load_config()
    entries = list_cache(cfg.resolved_cache_dir())
    if not entries:
        typer.echo(f"(empty) {cfg.resolved_cache_dir()}")
        return
    for e in entries:
        size_mb = e.size_bytes / (1024 * 1024)
        sha = (e.last_sha[:12] + "…") if e.last_sha else "(never checked out)"
        typer.echo(f"{e.repo}  HEAD={sha}  {size_mb:,.1f} MiB  {e.path}")


@cache_app.command("clear")
def cache_clear(
    yes: bool = typer.Option(False, "--yes", "-y", help="Don't prompt for confirmation."),
) -> None:
    """Delete the entire sparse-checkout cache."""
    cfg = load_config()
    root = cfg.resolved_cache_dir()
    if not yes:
        typer.confirm(f"Delete cache at {root}?", abort=True)
    clear_cache(root)
    typer.echo(f"cleared {root}")


def _strip_duplicate_program_name(argv: list[str]) -> list[str]:
    """If the user typed `pr-triage pr-triage <sub> …` drop the duplicate and warn."""
    if len(argv) >= 2 and argv[1] == "pr-triage":
        typer.echo(
            "note: ignoring duplicated 'pr-triage' token — did you mean `pr-triage <subcommand>`?",
            err=True,
        )
        return [argv[0], *argv[2:]]
    return argv


def main() -> None:
    sys.argv = _strip_duplicate_program_name(sys.argv)
    app()


if __name__ == "__main__":
    main()
