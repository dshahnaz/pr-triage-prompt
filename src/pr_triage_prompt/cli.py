"""Typer CLI for pr-triage-prompt."""

from __future__ import annotations

import json
import sys
from enum import Enum
from pathlib import Path

import typer

from pr_triage_prompt import __version__
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
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass sparse-checkout cache."),
    skip_checkout: bool = typer.Option(
        False, "--skip-checkout", help="Skip sparse checkout (use degraded module resolver)."
    ),
) -> None:
    """Build a Markdown prompt from a PR (+ Jira ticket)."""
    cfg = load_config()
    pr = _load_pr(pr_ref, cfg)
    jira = _load_jira(jira_file, jira_key, cfg, pr.jira_id)

    repo_root: Path | None = None
    if not skip_checkout:
        try:
            repo_root = ensure_checkout(
                cache_root=cfg.resolved_cache_dir(),
                repo=pr.repo,
                sha=pr.sha,
                clone_url=f"https://github.com/{pr.repo}.git",
                paths=[f.filename for f in pr.files],
                no_cache=no_cache,
            )
        except Exception as exc:
            typer.echo(
                f"warning: sparse checkout failed ({type(exc).__name__}: {exc}); "
                "falling back to degraded module resolver",
                err=True,
            )
            repo_root = None

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
        typer.echo(
            f"wrote {out} ({bundle.token_count} tokens / budget {bundle.token_budget}, "
            f"{len(bundle.modules)} module{'s' if len(bundle.modules) != 1 else ''}"
            f"{', ' + str(len(bundle.dropped_modules)) + ' dropped' if bundle.dropped_modules else ''})"
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
    skip_checkout: bool = typer.Option(
        True, "--skip-checkout/--checkout",
        help="Skip sparse checkout in batch mode (default: skip).",
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass sparse-checkout cache."),
    fmt: OutputFormat = typer.Option(OutputFormat.md, "--format", help="Output format."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress per-PR progress lines; always prints the final report."
    ),
) -> None:
    """Build prompts from every pr_*.json in a context folder.

    For each PR, looks up its Jira ticket by `jira_<jira_id>.json` (with a content-based
    fallback on the `key` field). Writes per-PR files and/or one combined prompt.
    """
    cfg = load_config()
    items = discover_context(context_dir)
    if not items:
        typer.echo(f"no pr_*.json files in {context_dir}", err=True)
        raise typer.Exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    budget = token_budget or cfg.default_token_budget

    def _checkout(pr_repo: str, pr_sha: str, file_paths: list[str]) -> Path | None:
        if skip_checkout:
            return None
        try:
            return ensure_checkout(
                cache_root=cfg.resolved_cache_dir(),
                repo=pr_repo,
                sha=pr_sha,
                clone_url=f"https://github.com/{pr_repo}.git",
                paths=file_paths,
                no_cache=no_cache,
            )
        except Exception as exc:
            typer.echo(
                f"warning: checkout failed for {pr_repo}@{pr_sha[:12]} "
                f"({type(exc).__name__}: {exc}); using degraded resolver",
                err=True,
            )
            return None

    # Per-PR pass.
    report_rows: list[dict[str, object]] = []
    batch_items: list[BatchItem] = []
    matched_with_content = 0
    for item in items:
        repo_root = _checkout(item.pr.repo, item.pr.sha, [f.filename for f in item.pr.files])
        bundle = build_prompt(
            item.pr, item.jira,
            repo_root=repo_root, token_budget=budget, strict_budget=strict_budget,
        )
        batch_items.append(BatchItem(pr=item.pr, jira=item.jira, repo_root=repo_root))
        jira_note = item.jira_match
        if item.jira is not None and item.jira.has_content:
            matched_with_content += 1
        if not quiet:
            typer.echo(
                f"  PR #{item.pr.number}  jira={item.pr.jira_id or '—'}  match={jira_note}  "
                f"tokens={bundle.token_count}  modules={len(bundle.modules)}"
                + (f" (dropped {len(bundle.dropped_modules)})" if bundle.dropped_modules else "")
            )

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
            report_rows.append({
                "file": str(pr_out),
                "tokens": bundle.token_count,
                "budget": bundle.token_budget,
                "modules": len(bundle.modules),
                "jira": jira_note,
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
        report_rows.append({
            "file": str(combined_path) + " (combined)",
            "tokens": combined.token_count,
            "budget": combined.token_budget,
            "modules": len(combined.modules),
            "jira": f"{matched_with_content}/{len(items)} matched",
            "over": combined.token_count > combined.token_budget,
            "pr_number": None,
        })

    _print_report(report_rows)

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


def _print_report(rows: list[dict[str, object]]) -> None:
    """Fixed-width report: File | Tokens | Budget | Modules | Jira | Over?."""
    if not rows:
        return
    display_rows: list[dict[str, str]] = []
    for r in rows:
        display_rows.append(
            {
                "file": _truncate_file(str(r["file"])),
                "tokens": str(r["tokens"]),
                "budget": str(r["budget"]),
                "modules": str(r["modules"]),
                "jira": str(r["jira"]),
                "over": "yes" if r["over"] else "",
            }
        )
    headers = {
        "file": "File",
        "tokens": "Tokens",
        "budget": "Budget",
        "modules": "Modules",
        "jira": "Jira",
        "over": "Over?",
    }
    widths = {
        k: max(len(headers[k]), *(len(row[k]) for row in display_rows))
        for k in headers
    }
    # File left-aligned; numbers right-aligned; jira/over left-aligned.
    def _fmt(row: dict[str, str]) -> str:
        return (
            f"  {row['file']:<{widths['file']}}"
            f"  {row['tokens']:>{widths['tokens']}}"
            f"  {row['budget']:>{widths['budget']}}"
            f"  {row['modules']:>{widths['modules']}}"
            f"  {row['jira']:<{widths['jira']}}"
            f"  {row['over']:<{widths['over']}}"
        )

    typer.echo("")
    typer.echo("Report:")
    typer.echo(_fmt(headers))
    sep = {k: "-" * widths[k] for k in headers}
    typer.echo(_fmt(sep))
    for row in display_rows:
        typer.echo(_fmt(row))


@cache_app.command("list")
def cache_list() -> None:
    """List cached (repo, sha) checkouts."""
    cfg = load_config()
    entries = list_cache(cfg.resolved_cache_dir())
    if not entries:
        typer.echo(f"(empty) {cfg.resolved_cache_dir()}")
        return
    for e in entries:
        size_kb = e.size_bytes / 1024
        typer.echo(f"{e.repo} @ {e.sha}  {size_kb:,.0f} KiB  {e.path}")


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
