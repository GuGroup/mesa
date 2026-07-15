---
name: generate-explicit-calculation-recipe
description: Translate a selected computational-chemistry strategy's experiment.computational or experimental.computational section into a procedure-indexed explicit calculation recipe folder tree. Use before any slab, gas, adsorbate, relaxation, vibration, free-energy, DOS, charge, or benchmark-comparison execution when Codex must preserve the strategy's computational procedures as concrete required inputs, operations, and outputs without judging feasibility or silently replacing the requested calculation with a proxy.
---

For MESA end-to-end use, read `SKILL/orchestration/workflow.md` before applying this skill.

# Explicit Calculation Recipe

## Purpose

Use this skill immediately after a strategy is selected and before calculation
execution. The skill is a translator: it reads the selected strategy's
computational section and writes a folder tree whose top-level folders correspond
one-to-one to the original procedure lines.

This skill must not decide whether a recipe is executable, supported by current
skills, allowed by project policy, or scientifically sufficient. It records what
the strategy asks for.

## Input

Use the selected strategy artifact produced by `select-next-strategy`, usually:

```bash
python3 SKILL/orchestration/generate-explicit-calculation-recipe/scripts/generate_explicit_recipe.py \
  --strategy project/<project_name>/strategy_execution/strategy_selection/selected_strategy.json \
  --out project/<project_name>/strategy_execution/<strategy_id>_explicit_recipe
```

The script accepts a JSON file containing either:

- `selected_strategy.experiment.computational`;
- `selected_strategy.experimental.computational`;
- `experiment.computational`;
- `experimental.computational`;
- a direct `computational` object.

## Output Layout

The output root must contain:

```text
recipe_index.json
recipe_index.md
source_computational_section.json
P001_<procedure_slug>/
  procedure.json
  procedure_map.md
  calculations/
    C001_<calculation_slug>/
      recipe.json
      recipe.md
```

Each `P###` folder preserves a single source procedure. Each `C###` folder is one
specific calculation or analysis recipe derived from that procedure.

## Translation Rules

1. Read the computational section directly. Do not rewrite it from memory or from
   result artifacts.
2. Preserve exact source text and JSON-pointer provenance for every procedure.
3. Include required prior artifacts, inputs, operations, method intent, and
   outputs when they are stated or implied by the source procedure.
4. Use source context from `models`, `methods`, `dft_details`,
   `computational_tests_to_run`, and benchmark-comparison fields only to make the
   recipe explicit. Do not use those fields to override the source procedure.
5. Do not add feasibility labels such as `blocked`, `unsupported`, `executable`,
   or `requires_repair`.
6. Do not explain why a calculation cannot be done. A later preflight skill owns
   feasibility checks.
7. Do not substitute an easier proxy. If the procedure asks for projected DOS,
   write a projected-DOS recipe; do not replace it with geometry descriptors.
8. Do not execute calculations, build structures, submit jobs, run UMA/VASP, or
   create scientific result claims.

## Recipe Semantics

`required_inputs` and `required_prior_artifacts` mean "the calculation recipe
requires these objects." They are not feasibility claims.

`method_intent` means "the strategy requests this type of method or analysis."
It is not an instruction to bypass project policy.

`output_artifacts` means "these files should exist after the calculation is
executed by a later workflow." This skill does not create those scientific
outputs.

See `references/recipe-schema.md` for the JSON field contract.

## Output Validation

After running the generator on a selected strategy artifact, check that:

- every source procedure has exactly one `P###` folder;
- every `P###/procedure.json` contains the original procedure text;
- generated recipes contain no feasibility decision fields;
- no calculations are executed.
