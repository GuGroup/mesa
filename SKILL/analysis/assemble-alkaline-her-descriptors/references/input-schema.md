# Input Schema

`compute_alkaline_her_descriptors.py` accepts two input shapes.

## MESA free_energy_records

Use this when a prior workflow already wrote endpoint records:

```json
{
  "schema_version": 1,
  "free_energy_records": [
    {
      "kind": "surface",
      "motif": "ni_decorated_s_edge",
      "state": "H",
      "free_energy_ev": -118.1,
      "evidence_acceptance_state": "accepted-with-caveat",
      "evidence_caveats": ["visual review caveat"]
    },
    {
      "kind": "gas",
      "species": "H2",
      "free_energy_ev": -6.69
    }
  ]
}
```

Gas records are selected by `species`. Surface records are selected by
`motif` and `state`.

## Generic motif/state schema

Use this when assembling a standalone descriptor calculation:

```json
{
  "schema_version": 1,
  "motifs": [
    {
      "motif": "ni_decorated_s_edge",
      "motif_class": "Ni-doped",
      "states": {
        "clean": {"free_energy_ev": -114.36},
        "H2O": {"free_energy_ev": -128.19},
        "OH": {"free_energy_ev": -124.63},
        "H": {"free_energy_ev": -118.14},
        "H_OH": {"free_energy_ev": -128.42},
        "H2": {"free_energy_ev": -121.10}
      }
    }
  ],
  "references": {
    "H2": {"free_energy_ev": -6.69, "phase": "gas"},
    "H2O": {"free_energy_ev": -14.19, "phase": "liquid"}
  }
}
```

If `H2O.free_energy_ev` is gas-phase, pass
`--h2o-reference-correction-ev -0.088` or another documented correction.
