---
name: generate-explicit-calculation-recipe
description: Create P### procedure folders, optionally integrate a validated strategy-outcome next_run, map strategy information, and classify it into C### recipe folders. Use after selecting a computational strategy and before resolving or executing its procedures.
---

# Procedure Mapping

Create procedure folders:

```bash
python3 SKILL/orchestration/generate-explicit-calculation-recipe/scripts/generate_explicit_recipe.py \
  --strategy project/<project_name>/strategy_execution/strategy_selection/selected_strategy.json \
  --out project/<project_name>/strategy_execution/<strategy_id>_explicit_recipe
```

Map strategy information:

```bash
python3 SKILL/orchestration/generate-explicit-calculation-recipe/scripts/map_strategy_to_procedures.py \
  --strategy project/<project_name>/strategy_execution/strategy_selection/selected_strategy.json \
  --recipe-root project/<project_name>/strategy_execution/<strategy_id>_explicit_recipe
```

Classify P information into C recipes:

```bash
python3 SKILL/orchestration/generate-explicit-calculation-recipe/scripts/classify_procedure_information.py \
  --strategy project/<project_name>/strategy_execution/strategy_selection/selected_strategy.json \
  --recipe-root project/<project_name>/strategy_execution/<strategy_id>_explicit_recipe
```

For a classified next run, add this same option to both mapping and
classification commands:

```bash
--next-run project/<project_name>/strategy_execution/<prior_strategy_id>_explicit_recipe/strategy_outcome_classification.json
```

Omit the option for an ordinary strategy run. When supplied, it must be a
schema-version `1.0` `classify-strategy-outcome` artifact with a non-null
`next_run`.
The target strategy ID must match the strategy artifact for
`extend_strategy` and `prerequisite`; `replace_strategy` keeps its target null.

The first script writes only `P###/procedure.json` with exact `source_text`.
The second writes only `P###/mapping.json` with validated
`source_json_pointers`. The third writes `P###/calculations/C###/recipe.json`
with deterministic IDs, explicit C-task text, and P-shared/C-specific source
information, then writes `recipe_index.json`. None resolve or execute
procedures.

`next_run` does not replace the strategy contract or change its procedures.
The mapping stage exposes its mode, target, exact input sources, and short
report under `/next_run`; only information mapped to a procedure enters its C
recipes. Supply the corresponding target or replacement strategy artifact
through `--strategy`.
