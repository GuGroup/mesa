---
name: manage-execution-unit
description: >-
  Manage one recipe-backed E execution unit through ordered factual manifest
  writing, immutable diagnosis, and up to two best-effort execution-only
  repairs. Use after an E attempt completes or fails and before C-level
  aggregation, when Codex must terminally resolve the unit without changing its
  recipe, execution plan, scientific meaning, or strategy.
---

# Manage Execution Unit

For MESA end-to-end work, read `workflow.md` and
`SKILL/orchestration/workflow.md` first.

Apply the stages below in order. Keep manifest, diagnosis, repair decision, and
repair outcome as separate artifacts with separate responsibilities.

## Required Inputs

Require:

- `execution_plan.json` and the target `execution_id`;
- the source `recipe.json`;
- the current attempt's actual inputs, outputs, logs, executor, and invocation;
- any previous attempt manifest, diagnosis, repair decision, or repair outcome.

Load the target E record from the plan. If the recipe is missing or
inconsistent, do not infer its intent.

Preserve the original E task, `requires`, `produces`, dependencies, consumers,
assigned output meaning, recipe, and execution plan throughout all stages.

## Attempt Directories

Write a single-consumer original attempt under:

```text
P###/calculations/C###/execution/units/E###/
```

Write a shared original attempt under
`<strategy_id>_explicit_recipe/shared_execution/E###/`. Use sibling leaf
directories for repairs. For example:

```text
execution/units/E003/
  execution_manifest.json
  execution_diagnosis.json
  repair_decision.json
execution/units/E003-R1/
  execution_manifest.json
  execution_diagnosis.json
  repair_outcome.json
  repair_decision.json  # only when another decision is needed
execution/units/E003-R2/
  execution_manifest.json
  execution_diagnosis.json
  repair_outcome.json
  repair_decision.json  # when escalation is required
```

For shared execution, use the same attempt names directly under
`shared_execution/`. `E003-R1` and `E003-R2` remain attempts of planned unit
`E003`; every manifest must retain `execution_unit_id: E003`. Never create
`E003-R3`.

## Stage 1: Write The Attempt Manifest

After the current attempt completes or fails, write
`execution_manifest.json` inside that exact attempt directory.

Record only:

- `schema_version`;
- `execution_unit_id`;
- `source_recipe`;
- `skill_or_script_used`;
- `command`;
- `input_artifacts`;
- `output_artifacts`;
- `execution_status`: `completed` or `failed`.

List exact paths actually used or produced. Write one manifest per attempt.

Do not copy `requires`, `produces`, dependencies, consumers, or recipe settings.
Do not add diagnosis, acceptance, caveats, exclusions, scientific validation,
repair decisions, or C-level aggregation.

## Stage 2: Diagnose The Attempt

Read the attempt manifest, follow its `source_recipe`, and inspect its linked
inputs, outputs, and logs. Choose the diagnostic method. Prefer a matching
domain skill; otherwise use an appropriate project-local analysis or direct
structured inspection. Record the actual method and evidence. Do not modify
the execution being diagnosed.

Write `execution_diagnosis.json` beside the manifest. It may be edited while
being prepared, but becomes immutable once finalized or consumed by repair. If
the same attempt must be diagnosed again, write
`execution_diagnosis-D2.json` with a `supersedes` reference instead of
overwriting the finalized diagnosis.

Record:

- `schema_version`;
- `execution_unit_id`;
- `source_execution_plan`;
- `source_manifest`;
- `diagnostic_method`;
- `diagnosis_status`: `complete` or `insufficient_evidence`;
- `verdict`: `pass`, `warn`, `fail`, or `unknown`;
- `findings`, each with `problem` and supporting `evidence`;
- `diagnostic_artifacts`.

When reliable diagnosis is impossible, use `insufficient_evidence` and
`unknown`. Do not include repair methods or decisions, terminal status,
evidence acceptance, or strategy judgment.

## Stage 3: Decide Repair

Require the finalized current manifest and diagnosis. Choose exactly one:

- `no_repair`;
- `repair_once`;
- `escalate`.

Keep method selection open to Codex. Before escalating, exhaust reasonable
options available through installed skills, tools, runtimes, existing
executors, and project-local scripts. Escalate when repair requires installing
software, changing the recipe, or changing the execution-plan contract.

Write an immutable `repair_decision.json` in the currently diagnosed attempt
directory. Record:

- `execution_unit_id`;
- `source_manifest`;
- `source_diagnosis`;
- `decision`;
- `reason`;
- `next_attempt`, when applicable.

For `no_repair` or `escalate`, stop and treat the source diagnosis as the final
diagnosis for that attempt.

## Stage 4: Perform One Repair

For `repair_once`:

1. Choose an operational realization that differs from the failed invocation
   while preserving the plan and recipe.
2. Execute it in the next unused sibling directory, first `-R1`, then `-R2`;
   never overwrite an earlier attempt.
3. Apply Stage 1 to write that attempt's manifest.
4. Apply Stage 2 to write that attempt's diagnosis.
5. Write `repair_outcome.json` in that repair-attempt directory as `resolved`
   when the diagnosed problem is removed, otherwise `unresolved`.

Each `repair_outcome.json` must record only:

- `schema_version`;
- `execution_unit_id`;
- `attempt_id`, such as `E003-R1`;
- `source_diagnosis`, pointing to that attempt's diagnosis;
- `status`: `resolved` or `unresolved`.

If `-R1` is unresolved, apply Stage 3 to decide whether to use the one remaining
repair. If `-R2` is unresolved, write an `escalate` decision in `-R2` and stop.

## Boundary

Do not modify the recipe or execution plan. Do not decide C-level aggregation,
scientific evidence acceptance, exclusions, strategy sufficiency, strategy
revision, or the next strategy.
