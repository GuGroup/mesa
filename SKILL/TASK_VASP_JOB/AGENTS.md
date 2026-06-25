# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-24

## OVERVIEW
`TASK_VASP_JOB` is the Codex-facing policy layer for using `vasp-job` safely. It prepares, submits, and tracks expensive VASP jobs only after upstream structure gates have narrowed candidates.

## STRUCTURE
```text
TASK_VASP_JOB/
|-- SKILL.md
|-- defaults.yaml
|-- common_refinement.yml
|-- common_screening.yml
|-- agents/
`-- scripts/
```

## WHERE TO LOOK
| Task | Location | Notes |
| --- | --- | --- |
| Full job policy | `SKILL.md` | Calculation modes, parameter rules, queue/spec constraints. |
| Default refinement settings | `defaults.yaml` | Common + task overlays. |
| Reusable common blocks | `common_refinement.yml`, `common_screening.yml` | Use with `--common` or `extends`. |
| CLI implementation | `../../ENVIRONMENT/vasp-submit-linker/` | `vasp-job` package and tests. |
| Generated job specs | user run directory | Keep specs with selected structures, not hidden in the skill folder. |

## CONVENTIONS
- Default actual calculations to refinement-oriented settings.
- Use screening settings only when the user asks for screening, quick comparison, rough triage, or low-cost sanity checks.
- Minimal edit mode preserves user-supplied VASP parameters unless invalid or explicitly changed.
- Refinement/screening explicit modes must write final merged `vasp.parameters`; the CLI does not merge defaults for you.
- Prefer `structure.path` to POSCAR content; paths resolve relative to the spec file.
- Prefer `kspacing` plus `kgamma`; use explicit `vasp.kpts` only when fixed mesh or one-point Gamma-only behavior is required.

## ANTI-PATTERNS
- Do not run `freq` by default.
- Do not put gas molecule generation here; use `build-gas-phase-models` first.
- Do not silently submit many structures; prepare specs and ask which few should run.
- Do not set POTCAR, queue internals, or `project.root` in the job spec.
- Do not rewrite user INCAR-derived settings in minimal edit mode just because they differ from defaults.

## COMMANDS
```bash
vasp-job schema
vasp-job prepare input.yml
vasp-job prepare input.yml --common common_refinement.yml
vasp-job submit input.yml
vasp-job status <job_uid_or_scheduler_id>
vasp-job show <job_uid_or_scheduler_id>
vasp-job list --limit 20
```
