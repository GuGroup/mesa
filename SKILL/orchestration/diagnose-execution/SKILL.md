---
name: diagnose-execution
description: >-
  Diagnose one recipe-backed E execution attempt from execution_plan.json and
  its execution_manifest.json, using the referenced recipe, artifacts, and logs.
  Use after an execution manifest exists when Codex must produce an immutable,
  evidence-linked execution_diagnosis.json without selecting repair, accepting
  scientific evidence, or revising strategy.
---

For MESA end-to-end work, read `workflow.md` and
`SKILL/orchestration/workflow.md` first.

# Diagnose Execution

Require:

- `execution_plan.json`;
- the target `execution_id`;
- that attempt's `execution_manifest.json`.

Load the target E record from the plan. Follow `source_recipe` from the manifest
and inspect the linked inputs, outputs, and logs. If the recipe is missing or
inconsistent, do not infer its intent.

Choose the diagnosis method. Prefer a matching domain skill; otherwise use an
appropriate project-local analysis or direct structured inspection. Record the
actual method and evidence. Do not modify the execution being diagnosed.

Write `execution_diagnosis.json` beside the source manifest in the same E
attempt directory. It may be edited while being prepared, but becomes
immutable once finalized or consumed by repair. If that same attempt must be
diagnosed again, write `execution_diagnosis-D2.json` with a `supersedes`
reference instead of overwriting the finalized diagnosis.

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
`unknown`. Do not include repair methods or decisions, terminal/final status,
evidence acceptance, or strategy judgment.
