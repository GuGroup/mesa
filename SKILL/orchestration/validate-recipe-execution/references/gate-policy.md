# Recipe Execution Gate Policy

The gate checks project organization, not scientific validity.

## Canonical Calculation Path

Every calculation derived from an explicit recipe must have:

```text
<strategy_id>_explicit_recipe/
  P###/
    calculations/
      C###/
        recipe.json
        execution/
          execution_manifest.json
          units/
            E###/
```

Generated `recipe.json` files remain translator outputs. Do not write execution
status into them.

## Shared Outputs

Batch commands may naturally produce shared outputs outside one calculation's
`execution/` folder. They are valid evidence only when:

- the output path exists;
- at least one recipe-local `execution_manifest.json` lists it in
  `output_artifacts`;
- the path is under the plan-assigned
  `S1_explicit_recipe/shared_execution/E###/` directory.

Legacy `S1_execution/` and `S1_shared_execution/` roots remain accepted for
previous runs when recipe-local manifests preserve provenance.

If a shared output is not linked from a recipe-local manifest, it is an orphan
and should not be used as evidence.

## Hard Errors

Hard errors include missing manifests, unreadable JSON, source-recipe mismatch,
missing listed artifacts, invalid acceptance state, and external output paths
outside allowed roots.

## Warnings

Warnings include local files in `execution/` that are not listed in
`output_artifacts`, empty commands, empty caveats for caveated/failed/excluded
states, and shared outputs that are valid but should be reviewed for whether
they are linked from all relevant recipes.
