# Input Schema

`record_missing_evidence.py` expects one temporary JSON input and writes one
canonical `missing_evidence.json`.

```json
{
  "schema_version": 1,
  "strategy_id": "S1",
  "procedure_id": "P006",
  "execution_unit_id": "E009",
  "source_recipe": "project/<project_name>/strategy_execution/S1_explicit_recipe/P006_electronic_analysis/calculations/C001_charge/recipe.json",
  "source_diagnosis": "project/<project_name>/strategy_execution/S1_explicit_recipe/P006_electronic_analysis/calculations/C001_charge/execution/units/E009-R2/execution_diagnosis.json",
  "source_repair_decision": "project/<project_name>/strategy_execution/S1_explicit_recipe/P006_electronic_analysis/calculations/C001_charge/execution/units/E009-R2/repair_decision.json",
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
`source_recipe` must resolve to the recipe-local `recipe.json`.
`execution_unit_id` must identify the corresponding unit in
`execution_plan.json`.

`source_diagnosis` and `source_repair_decision` are required. They must exist,
occupy the same terminal E attempt directory, identify the same
`execution_unit_id`, and describe the terminal E-level MDR state. The diagnosis
must be finalized with verdict `warn`, `fail`, or `unknown`; the repair decision
must be `no_repair` or `escalate` and must reference that diagnosis. Use the
terminal E attempt directory for `--output`, with the exact filename
`missing_evidence.json`. Do not retain the input spec as an execution artifact.
The recorder never writes or modifies `execution_manifest.json`.
