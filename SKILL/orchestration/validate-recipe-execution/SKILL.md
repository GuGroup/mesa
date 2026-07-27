---
name: validate-recipe-execution
description: Validate recipe-local execution folders, execution_manifest.json files, shared batch artifact links, and orphan outputs for MESA strategy runs. Use after recipe-backed calculations and before evidence readiness, manuscript/result writing, or strategy updates when Codex must enforce that outputs live under S*_explicit_recipe/P*/calculations/C*/execution/ or are explicitly linked shared artifacts.
---

For MESA end-to-end use, read `SKILL/orchestration/workflow.md` before applying this skill.

# Recipe Execution Gate

## Scope

Use this skill after executing recipe-backed calculations and before treating
any output as project evidence. It is a governance gate: it checks paths,
manifests, and provenance. It does not run calculations, edit recipes, repair
outputs, or judge chemistry.

The gate enforces the workflow rule that every calculation recipe has an
`execution/` folder with an `execution_manifest.json`. Shared batch outputs may
exist outside the recipe folder only when recipe-local manifests link to them.

## Quick Start

Run the checker on a strategy recipe root:

```bash
python3 SKILL/orchestration/validate-recipe-execution/scripts/check_recipe_execution.py \
  --recipe-root project/<project_name>/strategy_execution/S1_explicit_recipe \
  --project-root . \
  --outdir project/<project_name>/strategy_execution/S1_recipe_execution_gate
```

The checker automatically treats plan-assigned
`S1_explicit_recipe/shared_execution/` and legacy sibling strategy roots such
as `S1_execution/` and `S1_shared_execution/` as allowed shared roots. Add more
allowed shared roots with:

```bash
python scripts/check_recipe_execution.py ... \
  --shared-root project/<project_name>/strategy_execution/S1_extra_shared_outputs
```

For policy details, read `references/gate-policy.md`.

## What It Checks

- every immediate `P*/calculations/C*/` folder has `recipe.json`;
- every calculation folder has `execution/execution_manifest.json`;
- each manifest has required workflow fields;
- `source_recipe` resolves to the local `recipe.json`;
- `source_procedure_id` matches the recipe's `procedure_id`;
- `acceptance_state` is one of the workflow-allowed values;
- listed input and output artifacts exist;
- local files in `execution/` are listed as outputs or are the manifest itself;
- outputs outside local `execution/` are either under an allowed shared root or
  are reported as external path violations.

## Outputs

The checker writes:

| Artifact | Purpose |
| --- | --- |
| `recipe_execution_gate_report.json` | Full machine-readable gate report. |
| `recipe_execution_gate_report.md` | Human-readable pass/fail summary and issues. |
| `manifest_index.csv` | One row per recipe calculation folder. |
| `path_issues.csv` | Missing paths, external outputs, orphan local files, and related issues. |

Exit code is `0` when there are no hard errors and `2` when hard errors exist.
Warnings are reported but do not fail the gate unless a downstream workflow
chooses to treat warnings as blocking.

## Interpretation

`pass` means the execution pathway is auditable. It does not mean the chemistry
is correct. Continue with `analyze-calculation-results`, free-energy
bookkeeping, missing-evidence recording, and manuscript/result skills only after
the relevant recipe execution gate passes or the exceptions are explicitly
accepted by the user.
