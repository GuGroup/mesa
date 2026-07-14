# Input Schema

`record_missing_evidence.py` expects one JSON file.

```json
{
  "schema_version": 1,
  "strategy_id": "S1",
  "procedure_id": "P006",
  "source_recipe": "project/<project_name>/strategy_execution/S1_explicit_recipe/P006_electronic_analysis/calculations/C001_charge/recipe.json",
  "status": "excluded",
  "reason": "Charge transfer and PDOS require artifacts that were not generated.",
  "not_substituted_with_proxy": true,
  "required_future_artifacts": [
    "charge density or Bader-compatible grid",
    "wavefunction/projector data",
    "electronic DOS/PDOS outputs"
  ],
  "requirements": [
    {
      "calculation_id": "C001",
      "label": "compute charge-transfer descriptors",
      "status": "excluded",
      "missing_artifacts": ["charge_density_or_partitionable_electronic_density"],
      "targets": ["Ni", "adjacent S", "adjacent Mo"]
    },
    {
      "calculation_id": "C002",
      "label": "compute projected DOS descriptors",
      "status": "excluded",
      "missing_artifacts": ["wavefunction_or_projector_data", "electronic_dos_data"],
      "targets": ["Ni", "adjacent S", "adjacent Mo"]
    }
  ]
}
```

Allowed top-level `status` values are `excluded`, `blocked`, and `unresolved`.
The script exits non-zero if `not_substituted_with_proxy` is not `true`.
`source_recipe` must resolve to the recipe-local `recipe.json`, and
`procedure_id` must match that recipe's `procedure_id` so the generated
`execution_manifest.json` can pass `validate-recipe-execution`.
