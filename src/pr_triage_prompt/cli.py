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
from pr_triage_prompt.io.jira import fetch_jira_live, load_jira_file
from pr_triage_prompt.io.pr import fetch_pr_live, load_pr_file, parse_pr_ref
from pr_triage_prompt.models import JiraTicket, PullRequest
from pr_triage_prompt.prompt import build_prompt

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
        None, "--token-budget", help="Override token budget."
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
    bundle = build_prompt(pr, jira, repo_root=repo_root, token_budget=budget)

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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
