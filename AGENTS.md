# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-24
**Commit:** 1af9b2d
**Branch:** main

## OVERVIEW
`mesa` is a computational chemistry agent/workflow repo. It is split between executable environment tooling under `ENVIRONMENT/` and task-oriented agent skills under `SKILL/`.

## STRUCTURE
```text
mesa/
|-- ENVIRONMENT/
|   |-- build_tools/          # slabuilder package + modeling env
|   `-- vasp-submit-linker/   # vasp-job package and SGE templates
`-- SKILL/                    # MESA task bundles and Codex-facing workflows
```

## WHERE TO LOOK
| Task | Location | Notes |
| --- | --- | --- |
| Build slabs / adsorbates | `ENVIRONMENT/build_tools/` | `slabuilder` package and `modeling` env. |
| Submit/track VASP | `ENVIRONMENT/vasp-submit-linker/` | `vasp-job` CLI package. |
| MESA task contracts | `SKILL/` | Child instructions list task boundaries and entry points. |
| UMA/MLIP handoff | `SKILL/TASK_UMA/` | POSCAR-only workflow, dry-run default, qsub/local split. |
| VASP job policy | `SKILL/TASK_VASP_JOB/` | Cost-sensitive calculation defaults and submission rules. |

## CODE MAP
| Entry | Type | Location | Role |
| --- | --- | --- | --- |
| `slabuilder` | package | `ENVIRONMENT/build_tools/slabuilder/` | Structure generation and validation engine. |
| `vasp-job` | CLI | `ENVIRONMENT/vasp-submit-linker/src/vasp_submit/hpc_server/cli.py` | Prepare/submit/status/list/show VASP jobs. |
| `build_slab_model.py` | script | `SKILL/TASK_BUILD_SLAB_MODELS/scripts/` | Clean slab generation driver. |
| `place_surface_adsorbates.py` | script | `SKILL/TASK_PLACE_SURFACE_ADSORBATES/scripts/` | Adsorption-site placement driver. |
| `analyze_calculation_result.py` | script | `SKILL/TASK_CALCULATION_RESULT_ANALYZER/scripts/` | Convergence and visual-review analysis. |
| `mlip_workflow_controller.py` | controller | `SKILL/TASK_UMA/MYSKILL/` | UMA/MLIP handoff workflow. |

## CONVENTIONS
- Treat `ENVIRONMENT/` as package/runtime infrastructure and `SKILL/` as agent-facing task contracts.
- MESA task outputs use status/data/artifacts/messages/errors/provenance/next_action envelopes where documented.
- Tests are mostly `unittest`, often loading modules by absolute file path to avoid install-state coupling.
- Expensive or external execution is mocked in tests; real VASP/UMA/qsub behavior is a runtime workflow, not unit-test default.

## ANTI-PATTERNS
- Do not collapse slab generation, adsorbate placement, calculation submission, and result analysis into one undocumented step.
- Do not submit broad VASP or UMA job matrices without narrowing candidates first.
- Do not infer scientific validity from geometry generation alone; each downstream gate owns a different claim.

## COMMANDS
```bash
mamba env create -f ENVIRONMENT/build_tools/environment.yml
mamba env update -f ENVIRONMENT/build_tools/environment.yml --prune
mamba run -n modeling python -m playwright install chromium

cd ENVIRONMENT/vasp-submit-linker
PYTHONPATH=src uv run --no-project --with pyyaml python -m unittest discover -s tests -v
```
