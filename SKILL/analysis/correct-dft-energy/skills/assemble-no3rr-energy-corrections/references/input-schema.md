# NO3RR input schema

`compute_no3rr_corrections.py` accepts two shapes.

## Standalone `motifs + references + pathways`

See `assets/example_no3rr_input.json`.

Each motif needs `clean` and every state named in its pathway. A state may provide its composition explicitly:

```json
{
  "free_energy_ev": -120.4,
  "composition": {"N": 1, "O": 2, "H": 1},
  "evidence_acceptance_state": "accepted-with-caveat",
  "evidence_caveats": ["one imaginary low-frequency mode"]
}
```

Common labels (`NO3`, `NO3H`, `NO2`, `NO2H`, `NO`, `NHO`, `HNO`, `NOH`, `NH2O`, `NH2OH`, `NH2`, `NH3`) have built-in composition mappings. Explicit composition is safer for custom labels.

Required references are `H2`, `H2O`, `HNO3`, and `NH3`.

## MESA `free_energy_records`

```json
{
  "conditions": {"temperature_K": 298.15, "pH": 14, "potential_v": -0.3, "reference_electrode": "RHE"},
  "reference_policy": {"mode": "hno3_thermodynamic_cycle", "...": "..."},
  "pathways": [{"id": "path_A", "state_order": ["NO3", "NO2", "NO", "NH2", "NH3"]}],
  "state_compositions": {
    "NO3": {"N": 1, "O": 3, "H": 0},
    "NO2": {"N": 1, "O": 2, "H": 0}
  },
  "free_energy_records": [
    {"kind": "gas", "species": "H2", "free_energy_ev": -6.70},
    {"kind": "liquid", "species": "H2O", "free_energy_ev": -14.20, "phase": "liquid"},
    {"kind": "gas", "species": "HNO3", "free_energy_ev": -28.0, "phase": "gas"},
    {"kind": "gas", "species": "NH3", "free_energy_ev": -19.0, "phase": "gas"},
    {"kind": "surface", "motif": "site_A", "state": "clean", "free_energy_ev": -100.0},
    {"kind": "surface", "motif": "site_A", "state": "NO3", "free_energy_ev": -125.0}
  ]
}
```

## Energy record forms

Use exactly one of:

```json
{"free_energy_ev": -100.0}
```

or

```json
{
  "electronic_energy_ev": -100.5,
  "corrections_ev": {
    "zpe": 0.20,
    "thermal_enthalpy": 0.03,
    "minus_t_s": 0.15,
    "solvation": -0.10,
    "standard_state": 0.22
  }
}
```

Every `corrections_ev` value is additive. External HNO3/NH3/H2O corrections cannot be duplicated inside the record.


## Evidence and ranking

Each endpoint may include `evidence_acceptance_state` and
`evidence_caveats`. Failed/excluded endpoint evidence or failed eight-electron
closure keeps the pathway in diagnostic tables but sets `ranking_eligible` to
false.

Reference-policy evidence labels are separate from endpoint acceptance states:

```json
{
  "hno3_correction_evidence_label": "PARTIALLY MATCHED",
  "acid_cycle_evidence_label": "CLOSURE ONLY"
}
```

Allowed reference evidence labels are `MATCHED`, `PARTIALLY MATCHED`,
`CLOSURE ONLY`, `SCREENING ASSUMPTION`, and `UNVERIFIED`.

## Examples

- `assets/example_no3rr_input.json`: synthetic alkaline/RHE demonstration.
- `assets/example_no3rr_calle_vallejo_pH0_input.json`: synthetic pH-0
  bookkeeping reproduction used by the regression tests.

The script does not insert a 1.12 eV HNO3 correction unless it is explicitly
provided with provenance.
