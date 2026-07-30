---
name: repair-procedure
description: >-
  Decide and perform up to two execution-only repairs of the grouped C-level
  execution for one P procedure. Use after a current procedure diagnosis
  exists when Codex should resolve documented execution gaps through available
  lower-level work while preserving all scientific procedure, recipe, plan,
  and strategy content.
---

For MESA end-to-end work, read `workflow.md` and
`SKILL/orchestration/workflow.md` first.

# Repair Procedure

Require:

- `recipe_index.json`;
- `P###/procedure.json` and `P###/mapping.json`;
- the current unsuffixed, `-R1`, or `-R2` procedure diagnosis;
- every C-level manifest and referenced E record used by that diagnosis;
- previous P-level repair decisions and outcomes.

Repair only the diagnosis's `execution_gaps`. Preserve the procedure, mapping,
C recipes, execution plan, and strategy. Respect lower-level repair limits.

Choose exactly one decision:

- `no_repair`;
- `repair_once`;
- `escalate`.

Keep repair method selection open to Codex. Use reasonable available skills,
tools, runtimes, executors, and project-local methods. Repair may coordinate
lower-level execution, restore missing artifacts or links, rerun permitted
work, and regenerate affected C manifests.

Return `escalate` when repair requires changing scientific content, the
procedure, mapping, a recipe, the execution plan, or the strategy.

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

Write the original decision as `P###/repair_decision.json`. For a repaired
diagnosis, append its attempt suffix, such as `repair_decision-R1.json`. Record
the procedure ID, source diagnosis, decision, reason, targeted execution gaps,
and next attempt when applicable. For `no_repair` or `escalate`, stop and treat
the current diagnosis as the P-level handoff.

For `repair_once`:

1. Select the next unused suffix, first `-R1`, then `-R2`; never overwrite an
   earlier artifact.
2. Perform one best-effort execution repair without changing scientific
   content.
3. Use `write-execution-manifest` and `write-calculation-manifest` for any
   affected lower-level records.
4. Use `diagnose-procedure` to write `procedure_diagnosis-R1.json` or
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

If `R1` is unresolved, write `repair_decision-R1.json`; one further repair may
produce the `-R2` artifacts. If `R2` is unresolved, write an `escalate`
decision in `repair_decision-R2.json` and stop.

Do not evaluate scientific correctness, accept or exclude evidence, revise the
strategy, or select the next strategy.
