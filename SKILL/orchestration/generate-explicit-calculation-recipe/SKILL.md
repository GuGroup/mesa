---
name: generate-explicit-calculation-recipe
description: Create P### procedure folders, map strategy information, and classify it into C### recipe folders. Use after selecting a computational strategy and before resolving or executing its procedures.
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

The first script writes only `P###/procedure.json` with exact `source_text`.
The second writes only `P###/mapping.json` with validated
`source_json_pointers`. The third writes `P###/calculations/C###/recipe.json`
with deterministic IDs, explicit C-task text, and P-shared/C-specific source
information, then writes `recipe_index.json`. None resolve or execute
procedures.
