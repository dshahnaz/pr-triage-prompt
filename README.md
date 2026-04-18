# pr-triage-prompt

Turn a GitHub PR (plus its Jira ticket) into a Markdown prompt file you can paste into a separate LLM agent bound to a test-suite knowledge base, and ask *"which tests exercise these changes?"*.

The tool's output is a `.md` file. No LLM calls, no PAIS SDK dependency.

## Install

Not on PyPI yet — install straight from GitHub. The `pr-triage` command is the console script.

```bash
# pip — latest main
pip install "git+https://github.com/dshahnaz/pr-triage-prompt.git"

# pip — pinned tag (reproducible)
pip install "git+https://github.com/dshahnaz/pr-triage-prompt.git@v0.1.0"

# pip — with dev extras (pytest, ruff)
pip install "git+https://github.com/dshahnaz/pr-triage-prompt.git#egg=pr-triage-prompt[dev]"

# pip — with optional tree-sitter analyzers (better symbol extraction than regex)
pip install "git+https://github.com/dshahnaz/pr-triage-prompt.git#egg=pr-triage-prompt[treesitter]"

# uv tool (recommended for CLI users)
uv tool install "git+https://github.com/dshahnaz/pr-triage-prompt.git"

# pipx
pipx install "git+https://github.com/dshahnaz/pr-triage-prompt.git"
```

Verify:

```bash
pr-triage --version
pr-triage --help
```

### Upgrade

```bash
# pip
pip install --upgrade "git+https://github.com/dshahnaz/pr-triage-prompt.git"

# uv
uv tool upgrade pr-triage-prompt

# pipx
pipx upgrade pr-triage-prompt
```

## Quickstart

Given a pre-fetched PR JSON (same shape GitHub's REST API emits) and an optional Jira ticket JSON:

```bash
pr-triage build examples/pr_23861.json \
    --jira-file examples/jira_VCOPS-75787.json \
    --out out/prompt_23861.md
```

Or live (requires `GITHUB_TOKEN` in env):

```bash
pr-triage build vcf/mops#23861 --out out/prompt_23861.md
```

Output is a Markdown file with: PR header, Jira block, scrubbed PR description, a per-module changes table, per-file symbol lists, and a fixed "Task for the agent" footer. Paste it into your test-suite-bound agent.

### Batch a whole context folder

Have a directory of `pr_*.json` + `jira_*.json` fixtures? Process them all in one shot:

```bash
pr-triage batch ./context --out-dir ./out
```

For each `pr_*.json` this looks up the matching Jira — first by filename convention (`jira_<jira_id>.json`), then by scanning every `jira_*.json` for a top-level `"key"` that matches. You get one `prompt_<N>.md` per PR **and** one combined `prompt.md` with a single agent-task footer.

Useful flags: `--emit per-pr|combined|both` (default `both`), `--combined-name all.md`, `--token-budget 4000` (per-PR), `--combined-budget 16000`, `--checkout` (sparse-clone each PR to get accurate module names; off by default in batch mode).

## Input contract

The PR JSON shape matches what `gh api repos/OWNER/REPO/pulls/N` and `.../files` return, merged:

```json
{
  "number": 23861,
  "sha": "2ec5116f78bba8e74e25711cb7e3066d14e50fd0",
  "repo": "vcf/mops",
  "title": "[VCOPS-76551] - Stop collection in password management tests",
  "body": "…PR description…",
  "jira_id": "VCOPS-76551",
  "files": [
    {
      "filename": "path/to/File.java",
      "status": "added",
      "additions": 123,
      "deletions": 0,
      "patch": "@@ -0,0 +1,123 @@\n+…"
    }
  ]
}
```

Jira JSON uses fields `key`, `summary`, `description`, `issuetype`, `status`, `components`, `labels` — all optional.

## Output

A Markdown file. The schema is versioned: the first line is always `<!-- pr-triage-prompt schema v1 -->`. The *"Task for the agent"* footer is identical across runs so downstream agent behavior is comparable.

Alternate format: `--format json` emits the structured bundle the Markdown was built from.

## Configuration

`~/.pr-triage/config.toml` (all optional):

```toml
github_token_env = "GITHUB_TOKEN"
jira_base_url = "https://jira.example.com"
jira_token_env = "JIRA_TOKEN"
cache_dir = "~/.cache/pr-triage"
default_token_budget = 4000
```

Resolution order: env var → CLI flag → config file → default. Tokens are read from env only; never echoed.

## Cache

Sparse checkouts are cached under `~/.cache/pr-triage/<repo>/<sha>/` (keyed by `(repo, sha)`):

```bash
pr-triage cache list
pr-triage cache clear
```

Use `--no-cache` on `build` to force a fresh checkout for one run.

## Language support (v0.1)

| Language      | Extensions                       | Analyzer                              |
|---------------|----------------------------------|---------------------------------------|
| Java          | `.java`                          | regex (tree-sitter opt-in via extras) |
| Python        | `.py`                            | regex (tree-sitter opt-in)            |
| TypeScript/JS | `.ts`, `.tsx`, `.js`, `.jsx`     | regex (tree-sitter opt-in)            |

Install `pr-triage-prompt[treesitter]` to activate tree-sitter parsing (more accurate on heavily-nested code; falls back to regex if any grammar fails to load). See [plugin authoring](#plugin-authoring) to add a new language.

## Plugin authoring

A language analyzer implements this Protocol (see `pr_triage_prompt/analyzers/base.py`):

```python
from pathlib import Path
from pr_triage_prompt.analyzers.base import LanguageAnalyzer, FileChangeSummary, register_analyzer

@register_analyzer
class GoAnalyzer:
    extensions: tuple[str, ...] = (".go",)

    def analyze(self, file_path: Path, patch: str, status: str) -> FileChangeSummary:
        ...
```

- Parse the unified diff with `pr_triage_prompt.analyzers.patch.parse_patch` to get changed line ranges.
- Return a `FileChangeSummary` with `classes_changed` and `functions_changed` populated.
- Register via `@register_analyzer` (import side-effect from `pr_triage_prompt.analyzers`).

## Development

```bash
git clone https://github.com/dshahnaz/pr-triage-prompt.git
cd pr-triage-prompt
uv sync --extra dev --extra treesitter
uv run pytest
uv run ruff check .
```

Golden test: `tests/test_golden.py` re-runs the CLI against `examples/pr_23861.json` and byte-exact-compares to `examples/prompt_23861.md`. If you intentionally change the prompt schema, regenerate the golden and bump the schema version in the header.

## License

MIT — see [LICENSE](LICENSE).
