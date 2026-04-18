# Contributing

## Dev setup

```bash
git clone https://github.com/dshahnaz/pr-triage-prompt.git
cd pr-triage-prompt
uv sync --extra dev --extra treesitter
uv run pytest
uv run ruff check .
```

## Adding a language analyzer

See [README.md#plugin-authoring](README.md#plugin-authoring). Add tests in `tests/test_<lang>_analyzer.py` exercising: added file, modified method, whitespace-only patch, rename-only patch.

## Release flow

Versions live in two places and must be bumped together in the same commit:

1. `pyproject.toml` → `[project] version = "X.Y.Z"`
2. `src/pr_triage_prompt/__init__.py` → `__version__ = "X.Y.Z"`

Then:

```bash
# Update CHANGELOG.md with the new section
git commit -am "release: vX.Y.Z"
git tag vX.Y.Z
git push && git push --tags
```

Tag-pinned installs (`pip install "git+...@vX.Y.Z"`) start working as soon as the tag is pushed. No PyPI publish step — we install directly from the public Git repo.

## Prompt schema changes

The output `.md` is a stable contract. If you change section order, labels, or the agent-task footer:

1. Bump the schema marker in the output header (`<!-- pr-triage-prompt schema v2 -->`).
2. Regenerate `examples/prompt_23861.md` and commit the updated golden.
3. Note the change under "Changed" in `CHANGELOG.md`.
