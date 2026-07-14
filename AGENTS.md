# PROJECT KNOWLEDGE BASE

**Generated:** 2026-07-14 11:19 KST
**Commit:** `3961048`
**Branch:** `modeling-workflow-main-clean`

## OVERVIEW

MESA is a catalyst-focused computational-chemistry skill repository, not one
installable application. `workflow.md` is the authoritative scientific loop;
skills orchestrate isolated Python runtimes and save evidence-bearing artifacts.

## STRUCTURE

```text
mesa/
├── workflow.md        # authoritative end-to-end contract
├── SKILL/             # active domain workflows and agent-facing skills
├── ENVIRONMENT/       # executable packages and environment manifests
├── DEPENDENCY/        # runtime registry, bootstrap, readiness, handoffs
├── EXTERNAL/          # upstream source snapshots; not MESA-owned packages
├── RESOURCE/          # canonical input templates
├── assets/            # tracked product/README media
└── project/           # ignored run outputs; never reusable source
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Understand the scientific loop | `workflow.md` | Root policy wins conflicts |
| Select or change a skill | `SKILL/<domain>/workflow.md`, then leaf `SKILL.md` | Read both completely |
| Map a skill to its runtime | `DEPENDENCY/runtimes.yaml` | Registry is the routing source |
| Install/check/smoke runtimes | `DEPENDENCY/tools/mesa_env.py` | Dry-run unless `--yes` |
| Change slab/adsorbate engines | `ENVIRONMENT/build_tools/slabuilder/` | Python 3.11 package |
| Change local literature agent | `ENVIRONMENT/paper_search/` | LangGraph/PaperQA pipeline |
| Change VASP job helper | `ENVIRONMENT/vasp-submit-linker/` | SGE-facing `vasp-job` CLI |
| Change scholarly MCP vendor | `EXTERNAL/paper-search-mcp/` | Upstream snapshot boundary |
| Inspect task results | `project/<project_name>/` | Default test project is `mos_0629_2` |

## CODE MAP

| Symbol / surface | Type | Location | Refs | Role |
|---|---|---|---:|---|
| `workflow.md` | contract | `workflow.md` | all domains | strategy-to-manuscript loop |
| `main` | CLI | `DEPENDENCY/tools/mesa_env_support/cli.py:396` | runtime control plane | bootstrap/check/install/smoke |
| `load_registry` | function | `DEPENDENCY/tools/mesa_env_support/common.py:52` | 6 commands | parses runtime/skill routing |
| `generate_slab` | function | `ENVIRONMENT/build_tools/slabuilder/slab_gen.py:1262` | 3 callers | unified slab construction API |
| `Paper` | data model | `ENVIRONMENT/paper_search/src/paper_search/models.py:9` | ~18 dependents | literature pipeline contract |
| `AgentServices` | service hub | `ENVIRONMENT/paper_search/src/paper_search/agent/services.py:22` | 14 dependents | network/parser/LLM composition |
| `normalize_spec` | function | `ENVIRONMENT/vasp-submit-linker/src/vasp_submit/common/spec.py:153` | CLI + tests | VASP client contract gate |
| `prepare_job` | function | `ENVIRONMENT/vasp-submit-linker/src/vasp_submit/hpc_server/renderer.py:223` | CLI | trusted job materialization |

Python LSP is not installed by prior user choice. The code map uses the
359-file codegraph plus direct config and entry-point inspection.

## CONVENTIONS

- Instruction precedence is root `workflow.md` → domain `workflow.md` → leaf
  `SKILL.md`; a narrower file may refine but not violate its parent contract.
- Start with the narrowest matching active kebab-case skill. `TASK_*` and
  `SKILL/legacy/` are archival and must not be routed for current work.
- Use bundled scripts for deterministic/repeated operations. Run them through
  the runtime assigned in `DEPENDENCY/runtimes.yaml`, not the root Python.
- Every skill/script call is logged in
  `project/<project_name>/skill_call_log.md` with inputs, outputs, validation,
  and boundary notes.
- Calculation/modeling begins only from an explicit `P###/C###/recipe.json`.
  Execution state belongs in recipe-local `execution_manifest.json`, never in
  generated recipe files.
- Preserve source paths, citations, units, transforms, acceptance state, and
  caveats through analysis, figures, and manuscript handoffs.
- Runtime packages are isolated. Do not import across environments merely to
  deduplicate helpers.

## ANTI-PATTERNS (THIS PROJECT)

- Never submit VASP jobs under the current test policy. `manage-vasp-jobs` is
  limited to preparation, dry-run, status inspection, or future policy work.
- Never present UMA or another bounded proxy as equivalent to VASP or as full
  proof. State model limitations and the exact evidence boundary.
- Never skip explicit recipe generation, silently substitute an easier
  calculation, or advance strategies before result writing and strategy update.
- Never mutate `recipe.json`, `recipe.md`, or recipe indexes to imply progress,
  feasibility, or completion.
- Never edit a canonical `RESOURCE/` template in place; copy derivatives into
  the selected project directory.
- Never expose `.env` values or serialize secrets into plans, logs, reports, or
  generated guidance.
- Never treat `.venv/`, caches, `.omx/`, `.codegraph`, non-allowlisted `.codex/`
  state, or ignored `project/` outputs as source.

## UNIQUE STYLES

- Skills are self-contained instruction bundles: `SKILL.md`, optional
  `scripts/`, `references/`, `agents/openai.yaml`, and rare `MYSKILL/EXTSKILL`
  controller-runner splits.
- Scientific stages communicate through JSON/Markdown artifacts rather than a
  shared import graph. Provenance and acceptance metadata are API contracts.
- Tests are package-local `unittest` islands; there is no root test runner or
  repository-wide formatter/typechecker configuration.

## COMMANDS

```bash
# Inspect routing without changing environments
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py list --recipes --skills
uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py check --all

# Package-local test suites
(cd ENVIRONMENT/build_tools && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v)
(cd ENVIRONMENT/vasp-submit-linker && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src uv run --no-project --with pyyaml python -m unittest discover -s tests -v)
```

## NOTES

- `project/`, `SKILL/**/tests/`, `SKILL/**/assets/`, global `examples/`, and
  global `data/` can be ignored by broad rules; run `git check-ignore -v`
  before assuming a new fixture or asset is tracked.
- `ENVIRONMENT/paper_search` and `EXTERNAL/paper-search-mcp` both expose
  `paper-search` and `paper-search-mcp`; keep their runtimes separate.
- Adding or renaming a skill requires synchronized domain/root catalogs,
  `agents/openai.yaml`, runtime mapping, cross-skill handoffs, and validation.
