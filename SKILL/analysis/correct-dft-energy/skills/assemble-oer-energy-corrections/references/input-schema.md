# OER input schema

`compute_oer_corrections.py` accepts two shapes.

## MESA `free_energy_records`

```json
{
  "conditions": {
    "temperature_K": 298.15,
    "pH": 14,
    "potential_v": 0,
    "reference_electrode": "RHE"
  },
  "reference_policy": {
    "o2_mode": "h2o_h2_cycle",
    "o2_cycle_free_energy_eV": 4.92,
    "o2_cycle_temperature_K": 298.15,
    "o2_cycle_provenance": {"source": "..."}
  },
  "free_energy_records": [
    {"kind": "gas", "species": "H2", "free_energy_ev": -6.70},
    {"kind": "liquid", "species": "H2O", "free_energy_ev": -14.20, "phase": "liquid"},
    {"kind": "surface", "motif": "site_A", "state": "clean", "free_energy_ev": -100.0},
    {"kind": "surface", "motif": "site_A", "state": "OH", "free_energy_ev": -107.0},
    {"kind": "surface", "motif": "site_A", "state": "O", "free_energy_ev": -105.0},
    {"kind": "surface", "motif": "site_A", "state": "OOH", "free_energy_ev": -111.0}
  ]
}
```

## Standalone `motifs + references`

See `assets/example_oer_input.json`.

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

Every value in `corrections_ev` is additive. Do not provide both forms for one record.


## Evidence and ranking

Each surface state may include:

```json
{
  "evidence_acceptance_state": "accepted-with-caveat",
  "evidence_caveats": ["low-frequency mode requires review"]
}
```

Allowed workflow states are `accepted`, `accepted-with-caveat`, `failed`,
`excluded`, and `unknown`. A motif with failed/excluded evidence or failed OER
closure remains in diagnostic outputs but is not `ranking_eligible`.

## Cycle provenance

`h2o_h2_cycle` mode requires an explicit `o2_cycle_free_energy_eV`, cycle
temperature, and provenance. The script does not silently insert 4.92 eV. If a
direct O2 record is also supplied, it is used only as a diagnostic unless
`o2_mode` is `direct_o2`.
