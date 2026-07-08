# Modeling Domain Workflow

Use this manual for recipe-backed atomistic model preparation.

Modeling creates structures and model metadata. It does not decide the strategy
queue, run calculations, write manuscript claims, or invent substitutes for
missing recipe requirements.

# Skills

- `build-slab-models`
- `build-gas-phase-models`
- `place-adsorbates-with-adsorbdiff`
- `propose-surface-models-from-literature`

# Entry Requirements

Do not start modeling immediately after strategy selection. Explicit recipes
must already exist.

Before modeling, read:

- `recipe_index.md`;
- the relevant `P###/procedure.json`;
- the relevant `C###/recipe.json`;
- any execution plan or coverage note.

Model required structures based on explicit recipe artifacts, not from memory or
from a loose reading of the strategy.

# Model Types

Use `build-slab-models` for clean slab models, surface cells, terminations, and
surface model variants requested by a recipe.

Use `build-gas-phase-models` for gas-phase molecules, reference species, and
isolated species required by a recipe.

Use `place-adsorbates-with-adsorbdiff` for adsorbate placement on recipe-backed
slabs when adsorption configurations are required.

Use `propose-surface-models-from-literature` only when the recipe or strategy
requires literature-guided surface model proposal and the needed literature
evidence is present.

# Output Placement

Save model artifacts under the recipe calculation that authorized them:

```text
project/<project_name>/strategy_execution/<strategy_id>_explicit_recipe/
  P###_<procedure_slug>/
    calculations/
      C###_<calculation_slug>/
        execution/
          structures/
          model_manifest.json
          execution_manifest.json
```

If one model-generation run naturally creates structures for multiple recipes,
the shared output may live in a strategy-level shared directory only when each
recipe-local `execution_manifest.json` links to the exact subset used.

# Model Metadata

Record enough metadata for calculation and manuscript stages to understand the
model without rereading raw files:

- source recipe path and procedure ID;
- source structure, surface, adsorbate, or gas species;
- cell, slab, vacuum, termination, and site metadata when applicable;
- charge, spin, constraints, and periodic-boundary notes when applicable;
- generated structure paths;
- validation or sanity-check status;
- caveats and unsupported recipe requirements.

# Boundaries

- Do not model for a later strategy before the current selected strategy has
  passed through result writing and strategy update.
- Do not create proxy models unless the recipe, user, or logged execution plan
  explicitly permits a bounded proxy.
- Do not mark a recipe satisfied by a model that lacks required metadata or
  recipe-local provenance.
