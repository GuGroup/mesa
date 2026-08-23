---
name: plan-recipe-execution
description: Convert finalized P###/C### calculation recipes into a skill-neutral execution dependency graph with deterministic E### IDs and recipe-root-local paths. Use after recipe generation and realization, before modeling or calculation, when execution units, shared artifacts, and dependencies must be planned without selecting skills, commands, backends, feasibility, or status.
---

# Recipe Execution Planning

Create the execution graph:

```bash
python3 SKILL/orchestration/plan-recipe-execution/scripts/plan_recipe_execution.py \
  --recipe-root project/<project_name>/strategy_execution/<run_id>_explicit_recipe
```

The script reads `recipe_index.json` and every indexed `recipe.json` in one LLM
call. The LLM defines only execution units, consumers, dependencies, required
artifacts, and produced artifacts. Deterministic validation covers every C
recipe, rejects cycles and unknown references, topologically orders the units,
assigns `E###` IDs, and writes:

```text
<run_id>_explicit_recipe/execution_plan.json
```

Single-consumer units receive paths under that C recipe:

```text
P###/calculations/C###/execution/units/E###/
```

Multi-consumer units receive paths under:

```text
shared_execution/E###/
```

Both paths are relative to the recipe root. The skill does not create execution
directories, select or inspect available skills, choose commands or backends,
judge feasibility, execute work, write manifests, or modify recipes. A later
executor selects tools but must use the assigned `execution_dir`.

Use `--response-json` to validate a saved LLM response without an API call.
