# Modeling Domain Workflow

Use this manual for recipe-backed atomistic model preparation.

Modeling creates structures and model metadata. It does not decide the strategy
queue, run calculations, write manuscript claims, or invent substitutes for
missing recipe requirements.

# Skills

- `import-bulk-structure`
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

# Surface Preparation

When a recipe requires a slab, surface, or adsorbate configuration, keep the
modeling/calculation handoff in this order:

```text
bulk create/import
-> bulk optimization
-> slab build
-> clean slab optimization
-> adsorbate placement
```

Use `import-bulk-structure` for Materials Project retrieval or source-bulk
registration. Preserve source metadata, including Materials Project initial
magnetic moments (`initial_magmoms`) when present, in sidecar metadata and
handoff notes.

Bulk optimization and clean slab optimization belong to the calculation domain
and inherit the active backend policy from root `workflow.md`. Modeling skills
must not choose a calculation backend on their own.

Use `build-slab-models` only after an accepted optimized bulk artifact exists.
Pass that optimized artifact through `--bulk-file`; do not let slab generation
fetch a fresh Materials Project or formula-derived bulk directly.

Use a recipe-authorized adsorbate-placement skill only after an accepted
optimized clean slab artifact exists. AdsorbDiff is one available placement
path, not the only valid future path.

If the recipe or execution plan does not authorize a required predecessor, or if
its accepted artifact and provenance are missing, stop before the dependent slab
build or adsorbate placement. Return to explicit recipe generation, execution
planning, or missing-evidence recording. Do not edit generated recipe status
files.

# Model Types

Use `import-bulk-structure` for recipe-backed source bulk import or registration
before bulk optimization.

Use `build-slab-models` for clean slab models, surface cells, terminations, and
surface model variants requested by a recipe.

Use `build-gas-phase-models` for gas-phase molecules, reference species, and
isolated species required by a recipe.

Use a recipe-authorized adsorbate-placement skill for adsorbate placement on an
optimized clean slab. `place-adsorbates-with-adsorbdiff` is one available
operation-specific skill when its method matches the recipe.

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
- Do not choose the calculation backend in modeling skills; inherit it from the
  root workflow during calculation-domain steps.
