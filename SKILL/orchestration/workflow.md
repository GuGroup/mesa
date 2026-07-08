# Orchestration Domain Workflow

Use this manual for turning selected-strategy computational procedures into
explicit recipes, planning execution from recipes, validating recipe-local
outputs, and recording missing evidence.

Orchestration does not decide scientific sufficiency and does not execute
calculations.

# Skills

- `generate-explicit-calculation-recipe`
- `validate-recipe-execution`
- `record-missing-evidence`

# Generate Explicit Calculation Recipes

Use `generate-explicit-calculation-recipe` immediately after strategy selection
and before any structure building or calculation.

Input is the selected strategy artifact. The skill reads the selected strategy's
computational block:

- `selected_strategy.experiment.computational`, or
- `selected_strategy.experimental.computational`, or
- equivalent direct computational objects supported by the skill.

Recommended command:

```bash
python3 SKILL/orchestration/generate-explicit-calculation-recipe/scripts/generate_explicit_recipe.py \
  --strategy project/<project_name>/strategy_execution/strategy_selection/selected_strategy.json \
  --out project/<project_name>/strategy_execution/<strategy_id>_explicit_recipe
```

Required output shape:

```text
recipe_index.json
recipe_index.md
source_computational_section.json
P###_<procedure_slug>/
  procedure.json
  procedure_map.md
  calculations/
    C###_<calculation_slug>/
      recipe.json
      recipe.md
```

Each `P###` folder preserves a single source procedure. Each `C###` folder is
one specific calculation or analysis recipe derived from that procedure.

Recipe-generation rules:

- The recipe skill is a translator only.
- It must not decide feasibility, engine choice, policy compliance, repair
  needs, or scientific sufficiency.
- It must not write `blocked`, `unsupported`, `executable`, `feasible`,
  `requires_repair`, or similar decision fields into recipe files.
- It must not execute calculations.
- It must preserve exact source procedure text and JSON-pointer provenance.

# Plan Execution From Recipes

After recipe generation, inspect `recipe_index.md` and the `P###/C###`
`recipe.json` files before executing anything.

For each recipe, identify:

- required prior artifacts;
- required inputs;
- operations;
- method intent;
- output artifacts;
- the narrowest skills or scripts needed to produce those outputs.

Record the plan or coverage note separately from the recipe files. The plan may
state that a recipe requires a prior structure, electronic-structure output,
VASP-like artifact, vibration output, free-energy bookkeeping, or another
dependency. Do not alter the generated recipe to store execution status.

If a required calculation cannot be executed under current project policy or
available skills, do not silently downgrade it. Choose one explicit path:

- stop and ask the user;
- use `record-missing-evidence` to create unresolved, excluded, or blocked
  evidence records;
- update the strategy through the manuscript/update loop after documenting the
  gap;
- execute only the user-approved subset and label the result as bounded.

# Record Missing Evidence

Use `record-missing-evidence` for absent required artifacts, including but not
limited to:

- charge density;
- Bader charge;
- PDOS or DOS;
- wavefunction or projector files;
- kinetic barriers;
- solvent data;
- charged electrochemical-state data;
- any recipe-requested output that cannot be produced.

The record must name the source recipe, required artifact, reason unavailable,
impact on claims, and whether the gap is blocking or nonblocking.

# Validate Recipe Execution

Use `validate-recipe-execution` after recipe-backed modeling, calculation, and
analysis outputs are produced.

Validation checks that every produced calculation artifact is either:

- under the corresponding `C###/execution/` folder; or
- explicitly linked from a recipe-local `execution_manifest.json` to a shared
  batch artifact, with the exact subset for that recipe identified.

Repair orphan outputs before manuscript intake. Do not treat evidence as
manuscript-ready until validation passes or the remaining gaps are explicitly
recorded as excluded, failed, exploratory, or accepted-with-caveat.
