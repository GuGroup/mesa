---
name: mesa-literature-surface-proposal
description: Run the packaged SearchAgent literature workflow for catalyst surface-modeling proposals from a YAML run input. Use when MESA needs literature-backed surface, descriptor, facet, interface, or calculation-gap suggestions before modeling or manuscript work.
---

# MESA Literature Surface Proposal

Use this skill to run the SearchAgent package vendored at
`mesa/ENVIRONMENT/paper_search`. Keep this skill as a thin wrapper; do not copy
the package logic here.

## Inputs

Prefer a YAML run input with this shape:

```yaml
material: RuO2
reaction: HER
extra_terms:
  - rutile
  - heterointerface
research:
  prompt: Compare Ru, RuO2, and Ru/RuO2 interfaces for HER.
  decision_criteria:
    - prioritize DFT-feasible surface and descriptor gaps
```

An example is available at
`mesa/SKILL/TASK_LITERATURE_SURFACE_PROPOSAL/examples/search-input.example.yaml`.

## Runtime

Run from the MESA repository root:

```bash
cd ENVIRONMENT/paper_search
uv run --frozen paper-search run --input ../../SKILL/TASK_LITERATURE_SURFACE_PROPOSAL/examples/search-input.example.yaml --provider openai-oauth
```

For a real run, pass the caller's YAML path and choose an explicit output
directory:

```bash
cd ENVIRONMENT/paper_search
uv run --frozen paper-search run --input /path/to/search-input.yaml --out /path/to/output --provider openai-oauth
```

`~/.env` is supported. The intended default is:

```env
PAPER_SEARCH_PROVIDER=openai-oauth
PAPER_SEARCH_MODEL=gpt-5.4
OPENAI_EMBEDDING_KEY=
LANGSMITH_TRACING=false
```

`OPENAI_EMBEDDING_KEY` is only for PaperQA OpenAI embeddings. If it is unset,
install/use local embeddings or set `paperqa.embedding` to a local `st-*` model.
Sci-Hub fallback is enabled by default in the package config.

## Outputs

Use the generated output directory as the handoff artifact. Important files are:

- `run_manifest.json`
- `report.md` in full mode
- downloaded/parsed paper artifacts under the run folder
- `paperqa/` and `llm_cache.db` for reproducible resume

Do not treat literature suggestions as completed MESA calculations. Hand surface,
descriptor, and calculation-gap suggestions to the owning structure/calculation
skills before manuscript claims are made.
