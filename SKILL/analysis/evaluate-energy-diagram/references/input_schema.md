# Input Schema for `evaluate-energy-diagram`

## Accepted input container

`input_data` must be a JSON-serializable dictionary.

## Energy input modes

The evaluator normalizes all supported formats to the same internal table:

```text
step_column: str
steps: list[str]
catalysts: list[str]
values: dict[catalyst, list[float]]
```

### 1. CSV path

```json
{
  "csv_path": "examples/no3rr_energy.example.csv",
  "reaction_type": "NO3RR"
}
```

### 2. CSV text

```json
{
  "csv_text": "step,CatA\n*,0.0\nH*,0.1\n",
  "reaction_type": "HER"
}
```

### 3. Dictionary: steps + energies

```json
{
  "reaction_type": "HER",
  "energy_data": {
    "steps": ["*", "H*"],
    "energies": {
      "Pt": [0.0, -0.02],
      "Ni": [0.0, 0.18]
    }
  }
}
```

### 4. Dictionary: catalyst-centered mapping

```json
{
  "reaction_type": "OER",
  "energy_data": {
    "NiOOH": {"*": 0.0, "*OH": 1.55, "*O": 2.75, "*OOH": 3.45},
    "CoOOH": {"*": 0.0, "*OH": 1.48, "*O": 2.68, "*OOH": 3.37}
  }
}
```

### 5. Dictionary: row records

```json
{
  "reaction_type": "OER",
  "reaction_energies": [
    {"intermediate": "*", "A": 0.0, "B": 0.0},
    {"intermediate": "*OH", "A": 1.6, "B": 1.4},
    {"intermediate": "*O", "A": 2.7, "B": 2.6},
    {"intermediate": "*OOH", "A": 3.5, "B": 3.4}
  ]
}
```

## Optional fields

- `reaction_type`: `auto`, `HER`, `OER`, `NO3RR`, `NO2RR`, `NRR`, `CO2RR`, `ORR`, or formula-style reduction abbreviations ending in `RR`.
- `experiment`: catalyst-to-value dictionary for comparison.
- `competing_reactions` or `competing_descriptors`: lightweight competing-reaction descriptor dictionaries.
- `report_path`: optional Markdown report output path.
- `raw_text`, `materials`, `measurements`, `hypotheses`, `conditions`, `targets`: optional experimental-context fields.
- `include_values_in_output`: set true to include the normalized numerical table in output JSON.

## Assumptions

- Energies are assumed to be corrected free energies in eV unless the user says otherwise.
- The first CSV non-numeric/label-like column is treated as the reaction coordinate.
- Numeric columns are treated as catalysts or catalyst models.
- `NO3*` and `*NO3` are canonicalized to `*NO3`.
