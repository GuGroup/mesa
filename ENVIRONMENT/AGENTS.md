# ENVIRONMENT KNOWLEDGE BASE

## OVERVIEW

`ENVIRONMENT/` owns executable runtime packages and their install manifests.
Each child is an independent boundary with its own dependencies, entry points,
tests, and public API. Root `SKILL/` wrappers consume these APIs; they do not own
the underlying chemistry, search, or submission engines.

## STRUCTURE

```text
ENVIRONMENT/
├── build_tools/          # Python 3.11 slabuilder modeling package
│   ├── slabuilder/       # slab, site, adsorbate, validation APIs
│   └── .codex/skills/    # package-local skill surfaces and wrappers
├── paper_search/         # local LangGraph/PaperQA literature pipeline
├── vasp-submit-linker/   # isolated vasp-job CLI and SGE job renderer
└── manuscript_tools/     # conda manifest for manuscript/figure tooling
```

## WHERE TO LOOK

| Change | Primary location | Required follow-up |
|---|---|---|
| Slab or adsorbate behavior | `build_tools/slabuilder/` | package tests and consuming `SKILL/modeling/` wrappers |
| Package-local modeling skill | `build_tools/.codex/skills/` | keep its wrapper contract aligned with the root skill surface |
| Local literature workflow | `paper_search/src/paper_search/` | preserve models, config, HTTP, cache, and graph contracts |
| VASP specification or paths | `vasp-submit-linker/src/vasp_submit/common/` | run spec, path, and renderer contract tests |
| Scheduler rendering or status | `vasp-submit-linker/src/vasp_submit/hpc_server/` | preserve dry-run and trusted-root behavior |
| Manuscript dependencies | `manuscript_tools/environment.yml` | validate skills mapped to `mesa-manuscript` |

## CONVENTIONS

- Treat every top-level child as independently installable; its local
  `pyproject.toml`, `environment.yml`, lockfile, constraints, and templates are
  authoritative for that runtime.
- Run validation from the package directory with the package-local interpreter
  or manifest. There is no root test environment.
- Public APIs imported by `SKILL/` are compatibility contracts. Before changing
  signatures, metadata, tags, serialized fields, or defaults, find every root
  wrapper and update its documentation, examples, and tests together.
- `build_tools/slabuilder` is the modeling engine. Root skills should remain
  thin consumers of `generate_slab`, adsorbate builders, structure checks, and
  explicit metadata helpers.
- `paper_search` is the local research pipeline, not the external scholarly MCP
  snapshot. Its `Paper`/claim models, `PipelineConfig`, `HttpClient`, and atomic
  artifact writers are package-wide seams.
- `vasp-submit-linker` owns job-spec normalization, inheritance precedence,
  safe relative paths, trusted roots, rendering, and CLI behavior. Preserve
  these as security-sensitive contracts.
- Embedded `.codex/skills/` directories are intentional package-local agent
  surfaces. Declare one canonical wrapper source and synchronize mirrors; do
  not let embedded and root copies drift silently.
- Keep reusable code inside the environment that owns its dependency set.
  Duplicate a tiny adapter when necessary rather than creating a hidden import
  from one environment into another.

## ANTI-PATTERNS

- Do not import `slabuilder`, `paper_search`, or `vasp_submit` across sibling
  environments to share helpers.
- Do not add dependencies only to a developer `.venv`; update the owning
  manifest and lock/constraints surface.
- Do not edit generated environments, installed packages, caches, or ignored
  `.venv/` contents as source.
- Do not move engine logic into a `SKILL/` wrapper or duplicate domain models
  there; keep wrappers orchestration-focused.
- Do not conflate local `ENVIRONMENT/paper_search` with
  `EXTERNAL/paper-search-mcp`; similar names do not imply compatible APIs.
- Do not weaken VASP path containment, unknown-field rejection, or spec tests
  for convenience.
- Do not assume `manuscript_tools` is a Python package; it currently owns an
  environment manifest, while manuscript behavior remains in root skills.
