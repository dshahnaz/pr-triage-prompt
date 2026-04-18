# Changelog

All notable changes to this project are documented here. Format loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to [SemVer](https://semver.org/spec/v2.0.0.html).

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

[0.1.0]: https://github.com/dshahnaz/pr-triage-prompt/releases/tag/v0.1.0
