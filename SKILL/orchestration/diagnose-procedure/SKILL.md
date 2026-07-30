---
name: diagnose-procedure
description: >-
  Diagnose whether the grouped C-level execution of one P procedure is ready
  for strategy diagnosis. Use after factual C-level manifests exist when Codex
  must report procedure coverage, usable outputs, and execution gaps as
  pass, warn, fail, or unknown without judging scientific claims or selecting
  repair.
---

For MESA end-to-end work, read `workflow.md` and
`SKILL/orchestration/workflow.md` first.

# Diagnose Procedure

Answer:

> Was this procedure executed completely and coherently enough for strategy
> diagnosis to use its outputs, and if not, what execution gaps remain?

Require:

- `recipe_index.json`;
- `P###/procedure.json`;
- `P###/mapping.json`;
- every C recipe indexed under the procedure;
- every corresponding C-level `execution_manifest.json`;
- referenced terminal E diagnoses and repair records needed to explain an
  execution gap.

Inspect grouped execution only. Check C coverage, terminal manifest presence,
artifact availability, and unresolved E/C execution gaps. Do not reinterpret
scientific values or decide whether outputs support a claim.

Write:

```text
P###/procedure_diagnosis.json
```

For repair attempts, write `P###/procedure_diagnosis-R1.json` and then
`P###/procedure_diagnosis-R2.json`. Never create `-R3`.

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
immutable.

Do not propose repair, accept or exclude evidence, assess scientific
sufficiency, judge strategy claims, or select the next strategy.
