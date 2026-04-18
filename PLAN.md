# Handoff: new repo `pr-triage-prompt` (working title)

## Context

The user has a PAIS agent bound to a knowledge base of test suites. They want a separate CLI + SDK tool that, given a PR (plus its Jira ticket), produces a **Markdown prompt file** that can be pasted into that agent to get back "which test cases from the KB are relevant for these changes".

Keeping it outside `pais-sdk-cli` because the concerns are orthogonal: GitHub fetch + sparse checkout + multi-language AST/build-descriptor parsing has nothing to do with the PAIS API. The PAIS-side integration is later and trivial (one `agents.chat` call) if we ever want to automate the round-trip.

Current repo: `pais-sdk-cli` (PAIS SDK + `pais` CLI). Example input artifact shape lives in `/Users/davitshahnazaryan/Projects/pais-sdk-cli/context/`:
- `pr_23861.json` — PR metadata (`number`, `sha`, `repo`, `title`, `body`, `jira_id`, `files[]` with `filename`/`status`/`additions`/`deletions`/`patch`). ~20 KB.
- `jira_VCOPS-75787.json` — Jira ticket JSON (empty placeholder in the example; real ones will have summary / description / acceptance criteria).

Representative PR: changes in `ops/tests/dev/VCFPasswordManagement/src/main/java/com/vmware/vropsqa/test/...` — a Java module; build descriptor at the nearest `pom.xml` or `build.gradle`.

---

## Copy-paste prompt for the new session

Paste everything below into a fresh Claude Code session opened in a **new empty folder** (e.g. `~/Projects/pr-triage-prompt/`). It is self-contained.

---

````
You are scaffolding a brand-new public GitHub repo in my account (`dshahnaz`) called `pr-triage-prompt` (suggest a better name if you have one; I'll approve). Goal: a small CLI + SDK that converts a GitHub PR + its Jira ticket into a **Markdown prompt file** I can paste into a separate PAIS agent (which is bound to a test-suite knowledge base) to ask "which test cases are relevant for these changes".

This is intentionally decoupled from the PAIS side. The tool's output is an `.md` file. No PAIS SDK dependency, no agent call, no network to PAIS.

## Inputs (per invocation)

1. A GitHub PR — one of:
   - A pre-fetched JSON file matching the shape below (preferred for offline / reproducible runs).
   - Or live: `owner/repo` + PR number + a `GITHUB_TOKEN` env var (fetched via REST).
2. A Jira ticket JSON (optional but usually present) — same idea: pre-fetched file or live fetch if a Jira base URL + token are configured.

### Example input shape (real data from my other project — treat as the contract)

`/Users/davitshahnazaryan/Projects/pais-sdk-cli/context/pr_23861.json` (copy this path to your new repo as `examples/pr_23861.json` for fixtures):

```json
{
  "number": 23861,
  "sha": "2ec5116f78bba8e74e25711cb7e3066d14e50fd0",
  "repo": "vcf/mops",
  "title": "[VCOPS-76551] - Stop collection in password management tests",
  "body": "## Change Description ...  Jira ID: VCOPS-76551  ...",
  "jira_id": "VCOPS-76551",
  "files": [
    {
      "filename": "ops/tests/dev/VCFPasswordManagement/src/main/java/com/vmware/vropsqa/test/AdapterMonitoringStopTest.java",
      "status": "added",
      "additions": 123,
      "deletions": 0,
      "patch": "@@ -0,0 +1,123 @@\n+/* ... full unified diff ... */"
    },
    ...
  ]
}
```

Jira JSON: assume fields `key`, `summary`, `description`, `issuetype`, `status`, `components`, `labels` (be defensive — the example file in my context folder is currently empty).

## Required behavior

1. **Resolve inputs** — accept `--pr-file <path>` / `--jira-file <path>` first; fall back to live GitHub / Jira API using env-var tokens. Never print tokens.
2. **Sparse checkout** the repo at the PR's `sha` into a cache dir (`~/.cache/pr-triage/<repo>/<sha>/`). Sparse pattern = only the paths touched by `files[]` **plus** each of their nearest build-descriptor ancestors (see step 4). Use `git clone --filter=blob:none --sparse`, then `git sparse-checkout set <paths>`, then `git checkout <sha>`. Cache the checkout — don't re-clone on subsequent runs for the same sha.
3. **Per-file change analysis** — for each entry in `files[]`:
   - Language detection from extension (`.java`, `.py`, `.ts`/`.tsx`, `.js`/`.jsx`, `.go`, `.kt`, `.scala`, `.cs`, `.rb`, …).
   - Identify **classes** and **functions/methods** added / removed / modified. For added files, list all top-level symbols. For modified files, parse the patch hunks: any symbol whose body overlaps a `+`/`-` line counts. Prefer tree-sitter when available; fall back to language-specific regex if not. Pluggable analyzer interface so a new language is ~one file.
   - Record: `{path, language, module, classes_changed[], functions_changed[], status, additions, deletions}`.
4. **Module identification** — walk up from each changed file to the nearest build descriptor. Known descriptors:
   - Java/Kotlin/Scala: `pom.xml`, `build.gradle`, `build.gradle.kts`, `build.xml`
   - JS/TS: `package.json`
   - Python: `pyproject.toml`, `setup.py`, `setup.cfg`
   - Go: `go.mod`
   - Rust: `Cargo.toml`
   - .NET: `*.csproj`, `*.fsproj`
   - Ruby: `Gemfile`, `*.gemspec`
   Record the **module path** (directory containing the descriptor) and the **module name** (parse it out: `<artifactId>` for Maven, `name` for npm / pyproject, `module` line for go.mod, etc.). Group changed files by module in the output.
5. **Prompt assembly** — produce a single `.md` file (default `./out/prompt_<pr_number>.md`) with these sections, in order:

   ```markdown
   # PR #<number> — <title>

   **Repo:** <repo>   **SHA:** <sha>   **Jira:** <jira_id>

   ## Jira ticket

   **Summary:** <jira.summary>

   <jira.description>  (rendered as markdown, truncated to N paragraphs if huge)

   _Type: <jira.issuetype>  |  Status: <jira.status>  |  Components: <...>  |  Labels: <...>_

   ## PR description

   <pr.body>  (stripped of the boilerplate "Pipeline parameters" / "Auto-merge" blocks — keep only the human-written Change Description)

   ## Changes — summary

   | Module | Language | Files | Classes changed | Functions changed | +/- |
   |---|---|---|---|---|---|
   | <module-name> (<relpath>) | Java | 2 | AdapterMonitoringStopTest, AdapterUtils | testStopAdapterCollection, fetchAdapters, stopAdapterCollection | +335/-0 |
   | ... | ... | ... | ... | ... | ... |

   ### <module-name> (<relpath>)

   - `<file>` (<status>, +A/-D)
     - Classes: `<Class1>`, `<Class2>`
     - Functions/methods: `<fn1>`, `<fn2>`, `<Class1.method>`, ...
     - Excerpt: <3-5 line representative snippet from the patch>

   ## Task for the agent

   Using only the retrieved test-suite context from the knowledge base, list which **test cases** (by `suite → test_case`) are most likely to exercise the code changed above. For each, include a one-sentence justification tied to a specific changed class or function. If nothing in the KB is relevant, say "none" — do not invent test names.
   ```

   The last section is a **fixed task prompt** — keep it identical across runs so agent behavior is comparable.

6. **Token budget** — default cap ~4000 tokens for the full `.md`. Header (PR meta, Jira summary, PR description ≤500 tokens), changes table (always), then per-module sections greedy-fill until budget is hit; remaining modules collapse to "X additional modules: …" one-liners. Use the HuggingFace `tokenizers` library (`BAAI/bge-small-en-v1.5` or any stable tokenizer).

7. **Output formats** — `--format md` (default). `--format json` dumps the same data as structured JSON (useful for piping into other tools).

## SDK / CLI shape

- **SDK**: one package `pr_triage_prompt` with a single public entry `build_prompt(pr: PullRequest, jira: JiraTicket | None, *, repo_cache_dir: Path, token_budget: int = 4000) -> PromptBundle`. `PromptBundle` has `.markdown`, `.json_payload`, `.modules[]`, `.files[]`.
- **CLI**: Typer-based. Main command `pr-triage build <pr-ref> [--jira-file …] [--out …] [--format md|json] [--no-cache]`. `<pr-ref>` is either a file path, or `owner/repo#number` (live fetch). Add `pr-triage cache clear|list` for housekeeping.
- **Config**: `~/.pr-triage/config.toml` with `github_token_env = "GITHUB_TOKEN"`, `jira_base_url`, `jira_token_env`, `cache_dir`, `default_token_budget`. Env > CLI flag > config > defaults.

## Plugin interface for languages

```python
class LanguageAnalyzer(Protocol):
    extensions: tuple[str, ...]
    def analyze(self, file_path: Path, patch: str, status: str) -> FileChangeSummary: ...

@register_analyzer
class JavaAnalyzer: ...
```

Ship Java + Python + TypeScript/JavaScript as v0.1 built-ins (they cover the user's near-term repos). Others land incrementally.

## Tests

- Golden tests against `examples/pr_23861.json` → expected `prompt_23861.md` (checked into the repo). Running `pr-triage build examples/pr_23861.json --out /tmp/out.md` must match the golden byte-for-byte (modulo a small normalization for SHAs).
- Unit tests per analyzer on tiny synthetic patches (added file, modified method, whitespace-only, rename-only, binary).
- Module-resolver tests over a fake file tree with mixed descriptors.

## Non-goals (explicit)

- Do **not** call any LLM / agent. The tool's output is a Markdown file. Full stop.
- Do **not** parse the test-suite KB. That's the agent's job on the other end.
- Do **not** add PAIS SDK as a dependency. Zero coupling.

## Deliverables for this session

1. Repo scaffold: `pyproject.toml` (hatch or uv), `src/pr_triage_prompt/…`, `tests/…`, `examples/pr_23861.json` (copy from the example shape above), `examples/prompt_23861.md` (golden).
2. Working `pr-triage build examples/pr_23861.json --out /tmp/out.md` end-to-end for Java.
3. `README.md` with quickstart + plugin authoring guide.
4. `gh repo create dshahnaz/pr-triage-prompt --public --source=. --push` (confirm the name with me first).
5. CI on 3.10/3.11/3.12.

Ask me before:
- Finalizing the repo name.
- Adding a dependency heavier than `typer`, `httpx`, `gitpython`/subprocess-git, `tree-sitter` + a few language grammars, `tokenizers`, `pydantic`.
- Any design choice that changes the output `.md` schema (I want it stable so downstream tooling can rely on it).
````

---

## Safety review

| Risk | Mitigation |
|---|---|
| Leaking `GITHUB_TOKEN` into logs or the output `.md` | Env-var-only; never echoed; redact in any debug output. |
| Huge monorepo sparse-checkout thrash | Cache keyed by `(repo, sha)`; `--no-cache` opt-in; `pr-triage cache clear` escape hatch. |
| Tree-sitter grammar fragility | Fall back to regex per-language analyzer; golden tests pin expected output. |
| Prompt drift across versions breaking downstream consumers | Fix the "Task for the agent" footer; version the `.md` schema in a header comment. |
| Misidentified module (nested builds, e.g. multi-module Maven) | Walk to the **nearest** descriptor, not the outermost; unit-test with a nested `pom.xml` fixture. |
| Jira JSON shape varies by tenant | Defensive field access; null-safe rendering. |

## Flat TODO

- [ ] Confirm new repo name with user.
- [ ] Scaffold repo + `uv`/`hatch` layout + CI matrix.
- [ ] Copy `examples/pr_23861.json` fixture from `pais-sdk-cli/context/`.
- [ ] Implement `PullRequest` / `JiraTicket` / `FileChangeSummary` / `PromptBundle` pydantic models.
- [ ] Implement GitHub fetch (file + live) and Jira fetch (file + live).
- [ ] Implement sparse-checkout cache + `pr-triage cache` subcommand.
- [ ] Implement module resolver (walk-up for 8 build descriptors).
- [ ] Implement `LanguageAnalyzer` registry + Java / Python / TS/JS built-ins (tree-sitter preferred, regex fallback).
- [ ] Implement prompt assembler + token-budget greedy packer.
- [ ] Write golden test `prompt_23861.md`; wire byte-exact assertion.
- [ ] `pr-triage build` CLI, `--format md|json`, `--out`.
- [ ] README + plugin authoring guide.
- [ ] `gh repo create` + push + CI green on 3.10/3.11/3.12.
