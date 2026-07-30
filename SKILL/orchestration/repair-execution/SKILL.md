---
name: repair-execution
description: >-
  Decide and perform up to two best-effort repairs of a diagnosed recipe-backed
  E execution while preserving its execution_plan.json and source recipe. Use
  after execution_diagnosis.json exists when Codex should exhaust available
  installed skills, tools, runtimes, and project-local methods before recording
  no_repair, repair_once, or escalate.
---

For MESA end-to-end work, read `workflow.md` and
`SKILL/orchestration/workflow.md` first.

# Repair Execution

Require:

- `execution_plan.json` and the target `execution_id`;
- the current `execution_manifest.json`;
- the current `execution_diagnosis.json`;
- the source `recipe.json` referenced by the manifest;
- any previous attempt, diagnosis, or repair records.

Preserve the original E task, `requires`, `produces`, dependencies, consumers,
and assigned output meaning. Do not modify the execution plan or recipe.

Choose exactly one decision:

- `no_repair`;
- `repair_once`;
- `escalate`.

Before escalating, exhaust reasonable options available through installed
skills, tools, runtimes, existing executors, and project-local scripts. Keep
method selection open to Codex. Return `escalate` when repair requires
installing software, changing the recipe, or changing the execution-plan
contract.

Keep the planned E directory and repair attempts as sibling leaf directories.
For planned unit `E003`, use:

```text
execution/units/E003/
  execution_manifest.json
  execution_diagnosis.json
execution/units/E003-R1/
  execution_manifest.json
  execution_diagnosis.json
  repair_outcome.json
execution/units/E003-R2/
  execution_manifest.json
  execution_diagnosis.json
  repair_outcome.json
```

For shared execution, use the same names directly under `shared_execution/`.
`E003-R1` and `E003-R2` are attempts of `E003`, not new plan units; their
manifests must retain `execution_unit_id: E003`. Never create `E003-R3`.

Write an immutable `repair_decision.json` in the currently diagnosed attempt
directory with the execution-unit ID, source manifest, source diagnosis,
decision, reason, and next attempt when applicable. For `no_repair` or
`escalate`, stop and treat the source diagnosis as final for that E attempt.

For `repair_once`:

1. Choose an operational realization that differs from the failed invocation
   while preserving the plan and recipe.
2. Execute it in the next unused sibling attempt directory, first `-R1`, then
   `-R2`; never overwrite an earlier attempt.
3. Use `write-execution-manifest` for the new attempt in that directory.
4. Use `diagnose-execution` to create a fresh diagnosis in that directory.
5. Write `repair_outcome.json` there as `resolved` when the diagnosed problem
   is removed, otherwise `unresolved`.

Each `repair_outcome.json` must record only:

- `schema_version`;
- `execution_unit_id`;
- `attempt_id`, such as `E003-R1`;
- `source_diagnosis`, pointing to that attempt's diagnosis;
- `status`: `resolved` or `unresolved`.

If `-R1` is unresolved, one further repair may create `-R2`. If `-R2` is
unresolved, write an `escalate` decision in `-R2` and stop. Do not decide
scientific evidence acceptance or strategy revision.
