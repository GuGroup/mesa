---
name: manage-calculation
description: >-
  Manage one recipe-backed C calculation by writing its factual
  execution_manifest.json from terminal E attempts. Use after E-level diagnosis
  and repair terminate for the C recipe and before P-level management, when
  Codex must link execution sources, exact artifacts, optional assembly
  provenance, and output status without adding C-level diagnosis or repair.
---

# Manage Calculation

For MESA end-to-end work, read `workflow.md` and
`SKILL/orchestration/workflow.md` first.

## Required Inputs

Require:

- `P###/calculations/C###/recipe.json`;
- `execution_plan.json`;
- every E unit whose `consumers` include this C;
- the terminal attempt manifest for each required E unit;
- E repair records needed to identify those terminal attempts;
- exact artifacts used or exposed by the C calculation;
- any C-level assembly invocation and outputs.

Follow the E repair chain without reinterpreting its diagnosis. Do not guess a
terminal attempt when the records are ambiguous.

## Factual Manifest

Write:

```text
P###/calculations/C###/execution/execution_manifest.json
```

Record only:

- `schema_version`;
- `calculation_id`;
- `source_recipe`;
- `source_execution_plan`;
- `execution_sources`, each with `execution_unit_id`, `attempt_id`, and
  `manifest`;
- `assembly`, with `skill_or_script_used` and `command`, or null values when no
  C-level assembly occurred;
- `input_artifacts`;
- `output_artifacts`;
- `execution_status`: `completed` or `failed`.

Keep `execution_sources` as a list even when the C recipe uses one E unit. List
exact paths. Use `completed` only when the recorded C outputs were produced;
otherwise use `failed`.

## Boundary

Do not copy E settings, commands, findings, or repair reasoning into the C
manifest. Do not diagnose, repair, accept, exclude, or judge scientific
sufficiency. Do not modify the recipe, execution plan, or E records.
