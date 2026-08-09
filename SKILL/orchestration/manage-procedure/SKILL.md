---
name: manage-procedure
description: >-
  Manage one P procedure through ordered grouped-execution diagnosis and up to
  two execution-only repairs. Use after factual C-level manifests exist and
  before strategy diagnosis, when Codex must determine procedure coverage,
  expose usable outputs and execution gaps, and terminally resolve repairable
  gaps without changing scientific content.
---

# Manage Procedure

For MESA end-to-end work, read `workflow.md` and
`SKILL/orchestration/workflow.md` first.

Apply diagnosis and repair in order. Keep diagnosis, repair decision, and
repair outcome as separate artifacts with separate responsibilities.

Answer:

> Was this procedure executed completely and coherently enough for strategy
> diagnosis to use its outputs, and if not, what execution gaps remain?

## Required Inputs

Require:

- `recipe_index.json`;
- `P###/procedure.json` and `P###/mapping.json`;
- every C recipe indexed under the procedure;
- every corresponding C-level `execution_manifest.json`;
- referenced terminal E diagnoses and repair records needed to explain an
  execution gap;
- previous P-level diagnoses, repair decisions, and repair outcomes.

Inspect grouped execution only. Preserve the procedure, mapping, C recipes,
execution plan, and strategy. Respect lower-level repair limits.

## Procedure Artifacts

Use:

```text
P003/
  procedure.json
  mapping.json
  procedure_diagnosis.json
  repair_decision.json
  procedure_diagnosis-R1.json
  repair_outcome-R1.json
  repair_decision-R1.json
  procedure_diagnosis-R2.json
  repair_outcome-R2.json
  repair_decision-R2.json
  calculations/
```

The logical attempt IDs are `P003`, `P003-R1`, and `P003-R2`. Never create
`R3`.

## Stage 1: Diagnose The Procedure

Check C coverage, terminal manifest presence, artifact availability, and
unresolved E/C execution gaps. Do not reinterpret scientific values or decide
whether outputs support a claim.

Write `P###/procedure_diagnosis.json` for the original diagnosis. After repair,
write `P###/procedure_diagnosis-R1.json` and then
`P###/procedure_diagnosis-R2.json`.

Record:

- `schema_version`;
- `procedure_id`;
- `sources`, with `procedure`, `mapping`, and `calculation_manifests`;
- `verdict`: `pass`, `warn`, `fail`, or `unknown`;
- `coverage`, with `expected`, `completed`, `failed`, and `missing` C IDs;
- `outputs_for_strategy_diagnosis`;
- `execution_gaps`, each with `problem`, `affected_calculations`, and
  supporting `evidence`.

Use verdicts as follows:

- `pass`: procedure outputs are ready for strategy diagnosis;
- `warn`: outputs are usable with bounded execution gaps;
- `fail`: no usable procedure-level handoff exists;
- `unknown`: the records are insufficient to determine handoff readiness.

Keep paths exact and findings evidence-linked. Keep every finalized diagnosis
immutable. Do not propose repair in a diagnosis.

## Stage 2: Decide Repair

Repair only the current diagnosis's `execution_gaps`. Choose exactly one:

- `no_repair`;
- `repair_once`;
- `escalate`.

Keep repair method selection open to Codex. Use reasonable available skills,
tools, runtimes, executors, and project-local methods. Repair may coordinate
lower-level execution, restore missing artifacts or links, rerun permitted
work, and regenerate affected C manifests.

Escalate when repair requires changing scientific content, the procedure,
mapping, a recipe, the execution plan, or the strategy.

Write the original decision as `P###/repair_decision.json`. For a repaired
diagnosis, append its attempt suffix, such as `repair_decision-R1.json`. Record:

- `procedure_id`;
- `source_diagnosis`;
- `decision`;
- `reason`;
- `targeted_execution_gaps`;
- `next_attempt`, when applicable.

For `no_repair` or `escalate`, stop and treat the current diagnosis as the
P-level handoff.

## Stage 3: Perform One Repair

For `repair_once`:

1. Select the next unused suffix, first `-R1`, then `-R2`; never overwrite an
   earlier artifact.
2. Perform one best-effort execution repair without changing scientific
   content.
3. Use `manage-execution-unit` and `manage-calculation` for affected lower-level
   records.
4. Apply Stage 1 to write `procedure_diagnosis-R1.json` or
   `procedure_diagnosis-R2.json`.
5. Write the corresponding `repair_outcome-R1.json` or
   `repair_outcome-R2.json` as `resolved` when the targeted execution gaps are
   removed, otherwise `unresolved`.

Each repair outcome must record only:

- `schema_version`;
- `procedure_id`;
- `attempt_id`, such as `P003-R1`;
- `source_diagnosis`, pointing to that attempt's diagnosis;
- `status`: `resolved` or `unresolved`.

If `R1` is unresolved, apply Stage 2 and use at most one further repair. If
`R2` is unresolved, write an `escalate` decision in
`repair_decision-R2.json` and stop.

## Boundary

Do not evaluate scientific correctness, accept or exclude evidence, assess
scientific sufficiency, judge strategy claims, revise the strategy, or select
the next strategy.
