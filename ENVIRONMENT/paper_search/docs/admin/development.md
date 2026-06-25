# Development

This project uses `uv` for dependency and environment management.

## Install

```bash
uv sync
uv sync --extra docs   # for docs work
```

## Test

```bash
uv run python -m unittest discover -s tests
```

Tests run fully offline (deterministic graph, fixture-based search/resolver
parsing, and a fake-model LLM path). CI runs the same suite via
`.github/workflows/tests.yml`.

## Build docs locally

```bash
uv run --extra docs mkdocs build --strict
uv run --extra docs mkdocs serve
```

## Dependency updates

After editing `pyproject.toml`, refresh the lock file and commit both:

```bash
uv lock
```

CI installs with `uv sync --frozen`, so the lock must stay in sync.

## Code organization

Keep new functionality aligned with the node / module boundaries:

- search providers under `paper_search.search`,
- full-text resolvers under `paper_search.resolvers`,
- parser adapters under `paper_search.parsers`,
- evidence extraction in `paper_search.extraction`,
- opportunity ranking and calculation suggestions in `paper_search.opportunities`,
- graph orchestration and LLM/PaperQA nodes under `paper_search.agent`.

See [Agent graph](../architecture/agent-graph.md) for how these compose.
