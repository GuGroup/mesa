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

- `recipe_index.json`;
- `execution_plan.json`;
- the relevant `P###/procedure.json`;
- the relevant `C###/recipe.json`;

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

Use `import-bulk-structure` for source-bulk resolution before optimization. It
owns Materials Project retrieval, local/source-bulk registration, and direct
bulk unit-cell creation when no source artifact exists but the recipe provides
enough crystallographic information to construct one. Preserve source metadata,
including Materials Project initial magnetic moments (`initial_magmoms`) when
present, in sidecar metadata and handoff notes.

Resolve the source bulk in this order:

1. import an authorized Materials Project source when the recipe identifies or
   authorizes MP candidate selection;
2. register an authorized local or code-generated bulk artifact when one exists;
3. create the bulk unit cell directly when no import/register source exists and
   the recipe specifies enough composition, lattice, prototype, Wyckoff/site, or
   structure-generation instructions;
4. stop when the recipe lacks enough information to import, register, or create
   the bulk; record and diagnose the failed E attempt before any terminal
   missing-evidence record.

Bulk optimization and clean slab optimization belong to the calculation domain
and inherit the active backend policy from
`project/<project_name>/project_profile.md`. Modeling skills must not choose a
calculation backend on their own.

Use `build-slab-models` only after an accepted optimized bulk artifact exists.
Pass that optimized artifact through `--bulk-file`; do not let slab generation
fetch a fresh Materials Project or formula-derived bulk directly.

Use a recipe-authorized adsorbate-placement skill only after an accepted
optimized clean slab artifact exists. AdsorbDiff is one available placement
path, not the only valid future path.

If the recipe or execution plan does not authorize a required predecessor, or if
its accepted artifact and provenance are missing, stop before the dependent slab
build or adsorbate placement. Return to explicit recipe generation or execution
planning when appropriate; otherwise record and diagnose the failed E attempt
before any terminal missing-evidence record. Do not edit generated recipe
status files.

# Model Types

Use `import-bulk-structure` for recipe-backed source bulk import, registration,
or direct bulk unit-cell creation before bulk optimization.

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

Save model artifacts under the execution unit's assigned `execution_dir`.
Single-consumer units use:

```text
project/<project_name>/strategy_execution/<strategy_id>_explicit_recipe/
  P###/
    calculations/
      C###/
        execution/
          units/
            E###/
```

Multi-consumer units use the plan-assigned
`<strategy_id>_explicit_recipe/shared_execution/E###/` directory. Each
consumer's recipe-local `execution_manifest.json` must link the exact subset
used. Each E attempt directory must also contain its own
`execution_manifest.json`.

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
  active project profile during calculation-domain steps.
