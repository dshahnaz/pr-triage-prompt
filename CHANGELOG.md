# Changelog

All notable changes to this project are documented here. Format loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to [SemVer](https://semver.org/spec/v2.0.0.html).

## [0.6.0] — 2026-04-18

### Changed (performance)
- **One clone per repo, not per SHA.** The cache is now keyed by `<repo-slug>` (e.g. `vcf__mops/`) instead of `<repo-slug>/<sha>/`. Subsequent PRs on the same repo reuse the existing partial clone and just switch SHAs in place — fetching the new commit lazily, flipping the sparse set, then `git checkout <sha>`. A 10-PR batch against the same repo goes from 10 full clones (minutes, GBs) down to **one metadata clone + 10 lazy SHA fetches** (seconds, MBs).
- **Sparse patterns are exact files only.** Previously the tool added every parent directory (`ops/`, `ops/tests/`, …) to the sparse-checkout set. With `--no-cone` sparse-checkout, a bare directory pattern is gitignore-style recursive — so `ops/` pulled *every blob under ops*. That's why the first checkout was ~600 MB. Fix: list only the exact file paths (and the build descriptors the module resolver wants). Working-tree size drops by orders of magnitude.
- **Legacy cache layout (v0.5 and earlier) is auto-cleaned on first run.** If v0.6.0 finds old `<repo-slug>/<sha>/` directories, it removes them before setting up the new per-repo clone. No manual `pr-triage cache clear` needed.
- **`pr-triage cache list` output** now shows one row per repo with the currently-checked-out SHA and total size, instead of one row per (repo, sha) pair.

### Added
- Checkout phases include a new `reuse` event (`reusing <repo> clone`) and `fetch` event (`fetching <sha> (lazy blob fetch)`) so you can see cache effectiveness at a glance.
- `migrate` phase event (`removed N legacy per-SHA dirs`) on the first v0.6.0 run against a v0.5 cache.

### Known limitation
- **Not safe to run two `pr-triage batch` jobs against the same repo concurrently.** The working tree is shared; parallel runs on different repos are fine. A file-based lock would be straightforward — raise an issue if you need it.

## [0.5.0] — 2026-04-18

### Changed
- **Output streams cleanly split.** The report table is the only thing on stdout; all progress, notes, warnings, and errors go to stderr. Piping `--format json` and redirecting stderr now both work without munging.
- **Per-PR progress is phased.** Replaces the old single-line `PR #… jira=… tokens=…` with an indexed header + aligned sub-lines (`checkout`, `jira`, `wrote`).
- **Report paths are relative to `--out-dir` by default** (`prompt_23861.md` instead of a long absolute path). Use `--report-paths abs` to restore the old format. The combined row's `(combined)` filename suffix is gone; a new `Kind` column marks it.
- **`GIT_TERMINAL_PROMPT=0`** is now set for every git invocation so a missing credential fails fast with a real error instead of hanging on an interactive prompt.

### Added
- **Git authentication for HTTPS clones.** When `clone_url_template` points at `github.com` and `GITHUB_TOKEN` is set, the tool now injects an `Authorization: Bearer` header into the git invocation via `git -c http.https://github.com/.extraheader=…`. No token ends up in disk state or URL munging. For non-GitHub hosts, set `git_token_env` in `~/.pr-triage/config.toml` to name the env var. SSH URLs are untouched (continue to use your agent).
- **`--verbose` / `-v`** on `build` + `batch`: prints each git subcommand (tokens redacted to `Bearer ***`) and other detail.
- **`--no-color`** on `build` + `batch` (plus standard `NO_COLOR` env var): disables color regardless of TTY state.
- **`--report-paths abs|rel`** on `batch`: default `rel`.
- New `src/pr_triage_prompt/log.py` module with `info / note / warn / error / progress / phase / verbose` helpers, TTY detection, and `--quiet` / `--verbose` / `--no-color` state.
- The startup banner (`pr-triage 0.5.0  ·  N PRs in <ctx>  →  <out>`) makes it obvious what's about to run.

### Migration
- `--skip-checkout` was already removed in 0.4.0; no new flag removals.
- Scripts that scrape the old per-PR progress line (`  PR #… jira=…`) should instead parse the JSON report sidecar (`--format json` → `<combined-stem>.report.json`) or the report table on stdout.

## [0.4.0] — 2026-04-18

### Changed (breaking)
- **Prompt schema bumped to v2.** The marker is now `<!-- pr-triage-prompt schema v2 -->`. Header gains `**Components:**` (from Jira) and `**Packages:**` (extracted from source) lines; the `## Retrieval keys` section is added before the agent-task footer; the footer itself is rewritten to cite the test-suite KB format (suite / test-case / `## Components` / **Key Operations** / **API Endpoints**) and pin an explicit one-line output format.
- **`--skip-checkout` removed.** The tool now always attempts a sparse checkout when `clone_url_template` resolves. The `(repo, sha)` cache means subsequent runs are instant. `--no-cache` remains as the "force re-clone" escape hatch.
- **No built-in clone URL.** `clone_url_template` must be set in `~/.pr-triage/config.toml` or passed via `--clone-url`. Without it, the tool prints a one-time stderr note and falls back to degraded analysis (no hard error).

### Added
- **Full-file analysis** when source is available. Analyzers now pick up methods that were only **modified in their body** — previously missed because the patch hunk didn't include the declaration.
- **Java package extraction** from source (`package com.foo.bar;`), used as a module-name hint in degraded mode and surfaced as `**Packages:**` in the prompt header plus a per-file `- Package: ...` line.
- **Python package extraction** from `__init__.py` walk → dotted path (e.g. `pkg.mod`).
- **`clone_url_template` config / `--clone-url` flag** with `{repo}` placeholder — supports internal GitHub Enterprise / GitLab.
- **Report columns: `Files` + `Checkout`** in `pr-triage batch`, so you can see how many files each PR touched and whether the sparse checkout ran (`yes`/`no`/`fail`).
- `analyze_file(file_path, patch, status, repo_root)` on the `LanguageAnalyzer` Protocol; custom analyzers can override it to read from the checkout.
- `FileChangeSummary.package` field and the `Retrieval keys` block in the SDK's `PromptBundle.json_payload`.

### Migration
- If you relied on `--skip-checkout`, drop the flag; the tool behaves the same as `--skip-checkout` when `clone_url_template` isn't configured.
- If you have tooling reading the schema-v1 footer verbatim, update it for schema v2. The macro shape (header → Jira → PR description → summary table → per-module sections → agent-task footer) is unchanged; only the marker and the footer's wording changed.
- Golden prompt regenerated (`examples/prompt_23861.md`) with the new layout.

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

[0.6.0]: https://github.com/dshahnaz/pr-triage-prompt/releases/tag/v0.6.0
[0.5.0]: https://github.com/dshahnaz/pr-triage-prompt/releases/tag/v0.5.0
[0.4.0]: https://github.com/dshahnaz/pr-triage-prompt/releases/tag/v0.4.0
[0.3.0]: https://github.com/dshahnaz/pr-triage-prompt/releases/tag/v0.3.0
[0.2.0]: https://github.com/dshahnaz/pr-triage-prompt/releases/tag/v0.2.0
[0.1.0]: https://github.com/dshahnaz/pr-triage-prompt/releases/tag/v0.1.0
