---
name: write-execution-manifest
description: >-
  Write a minimal factual execution_manifest.json for a recipe-backed execution
  unit. Use after an E-level execution completes or fails and before diagnosis
  when Codex must record the actual executor, invocation, inputs, outputs, and
  execution result without evaluating evidence or deciding repair.
---

For MESA end-to-end work, read `workflow.md` and
`SKILL/orchestration/workflow.md` first.

# Write Execution Manifest

Read `execution_plan.json`, the source `recipe.json`, and the actual execution
artifacts. Write the attempt manifest inside the exact E directory:

```text
P###/calculations/C###/execution/units/E###/execution_manifest.json
```

For a shared E unit, use
`<strategy_id>_explicit_recipe/shared_execution/E###/execution_manifest.json`.
For a repair attempt, use the corresponding sibling directory such as
`E###-R1/` or `E###-R2/`, while retaining the planned `execution_unit_id`.

Record only:

- `schema_version`;
- `execution_unit_id`;
- `source_recipe`;
- `skill_or_script_used`;
- `command`;
- `input_artifacts`;
- `output_artifacts`;
- `execution_status`: `completed` or `failed`.

List exact paths that were actually used or produced. Write one manifest per E
attempt directory.

Do not copy `requires`, `produces`, dependencies, consumers, or recipe settings.
Do not diagnose results or record acceptance, caveats, exclusions, scientific
validation, repair decisions, or C-level aggregation. Do not modify the recipe
or execution plan.

After writing the manifest, use `diagnose-execution` for that attempt.
