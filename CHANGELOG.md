# Changelog

All notable changes to this project are documented here. Format loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to [SemVer](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-04-18

### Changed (breaking default)
- `token_budget` is now an **informational target** by default — no content is dropped even when a PR exceeds it. The old greedy-trim behavior is still available via `--strict-budget` (or `strict_budget=True` in the SDK). If you relied on the `_N additional modules omitted_` line appearing automatically, pass `--strict-budget`.

### Added
- End-of-run report on `pr-triage batch`: a fixed-width table (`File | Tokens | Budget | Modules | Jira | Over?`) printed after the emit loop, so large runs show per-prompt sizes at a glance. The `Over?` column flags rows where `tokens > budget`.
- `--quiet` / `-q` on `pr-triage batch` to suppress per-PR progress lines; the report still prints.
- `--format json` on `pr-triage batch` now also writes a `<combined-name-stem>.report.json` sidecar with the same rows as the table, for scripting.
- `--strict-budget` flag on both `build` and `batch` subcommands (and matching `strict_budget` param on `build_prompt` / `build_combined_prompt`).
- Friendlier `pr-triage pr-triage …` handling: the duplicated program-name token is dropped with a note on stderr, and the rest of the command runs normally.

## [0.2.0] — 2026-04-18

### Added
- `pr-triage batch <context-dir> --out-dir <dir>`: turn a folder of `pr_*.json` (+ optional `jira_*.json`) into per-PR Markdown files **and** one combined prompt with a single agent-task footer.
- Jira matching in batch mode: primary lookup via `jira_<jira_id>.json` filename, with a content-based fallback that scans each `jira_*.json`'s top-level `key` field — so a bulk Jira export in a single file still resolves correctly.
- `--emit {per-pr,combined,both}` (default `both`), `--combined-name`, `--combined-budget`, `--checkout/--skip-checkout` (default skip in batch mode) for the new command.
- SDK: `build_combined_prompt(items, token_budget, per_pr_token_budget)` and the `BatchItem` dataclass for programmatic batch assembly.

## [0.1.0] — 2026-04-18

Initial release.

### Added
- `pr-triage build <pr-ref>` CLI: builds a Markdown prompt from a PR JSON file or a live `owner/repo#number` (requires `GITHUB_TOKEN`).
- `--jira-file PATH` / `--jira KEY` for optional Jira ticket context; live Jira fetch via env-configured base URL + token.
- `pr-triage cache list|clear` for managing the sparse-checkout cache under `~/.cache/pr-triage/`.
- `pr-triage --version` / `--format md|json` / `--token-budget N` / `--no-cache` flags.
- Language analyzers for Java, Python, and TypeScript/JavaScript — regex-based by default, with optional tree-sitter backends (`pip install pr-triage-prompt[treesitter]`).
- Module resolver: walks up from each changed file to the nearest build descriptor (Maven, Gradle, npm, pyproject, setup, go.mod, Cargo, .csproj/.fsproj, Gemfile/.gemspec).
- Prompt schema versioned via `<!-- pr-triage-prompt schema v1 -->` header; fixed "Task for the agent" footer.
- Token-budget greedy packer using HuggingFace `tokenizers` (`BAAI/bge-small-en-v1.5`).
- SDK: `build_prompt(pr, jira, *, repo_cache_dir, token_budget) -> PromptBundle`.
- Golden test against `examples/pr_23861.json` → `examples/prompt_23861.md` (byte-exact).

[0.3.0]: https://github.com/dshahnaz/pr-triage-prompt/releases/tag/v0.3.0
[0.2.0]: https://github.com/dshahnaz/pr-triage-prompt/releases/tag/v0.2.0
[0.1.0]: https://github.com/dshahnaz/pr-triage-prompt/releases/tag/v0.1.0
