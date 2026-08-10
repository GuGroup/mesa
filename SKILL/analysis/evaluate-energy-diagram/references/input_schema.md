# Input Schema for TASK_REACTION_ENERGY_EVALUATION

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
- `enable_unresolved_volcano_handoff`: default `true`; when false, suppress the unresolved/tied-ranking handoff.
- `enable_downhill_volcano_handoff`: deprecated compatibility alias used only when `enable_unresolved_volcano_handoff` is absent.
- `downhill_trigger_scope`: `all_steps` (default) or `electrochemical`.
- `downhill_tolerance_ev`: numerical tolerance used for non-uphill diagnostics and top-score tie detection; default `1e-9` eV.
- `energy_reference_potential_v`, `input_potential_v`, or `diagram_potential_v`: potential at which the supplied diagram is defined.
- `equilibrium_potential_v` or `reversible_potential_v`: common equilibrium potential used for common-basis profile diagnostics when available for every catalyst.
- `step_electron_counts`: one transferred-electron count per transition, supplied as a list or transition-label mapping.
- `state_electron_counts`: cumulative electron counts for the listed states.
- `volcano_descriptor`: optional descriptor hint passed to `SKILL/figure/plot-sabatier-volcano`; the evaluator does not silently invent one.
- `volcano_activity_metric`: optional activity metric hint passed to `SKILL/figure/plot-sabatier-volcano`.

## Conditional downstream skill output

When at least two catalyst profiles and ranking rows are evaluable but the
diagram does not identify one unique thermodynamic best catalyst, output
includes:

```json
{
  "data": {
    "unique_best_catalyst_identified": false,
    "skill_handoff": {
      "triggered": true,
      "target_skill": "plot-sabatier-volcano",
      "target_skill_path": "SKILL/figure/plot-sabatier-volcano",
      "invocation": "$plot-sabatier-volcano",
      "condition": "comparative_thermodynamic_ranking_not_unique",
      "handoff_payload": {}
    }
  },
  "next_action": {
    "recommendation": "invoke_skill",
    "target_skill": "plot-sabatier-volcano",
    "target_skill_path": "SKILL/figure/plot-sabatier-volcano"
  }
}
```

The trigger covers unresolved rankings and top-score ties, including cases in
which some catalyst profiles contain uphill steps. The handoff remains
untriggered when one unique thermodynamic best catalyst is resolved, fewer than
two numerical ranking rows are available, a profile is not evaluable, or the
handoff is disabled. The Python code emits the routing request but does not
execute the other Codex skill itself.

## Assumptions

- Energies are assumed to be corrected free energies in eV unless the user says otherwise.
- The first CSV non-numeric/label-like column is treated as the reaction coordinate.
- Numeric columns are treated as catalysts or catalyst models.
- `NO3*` and `*NO3` are canonicalized to `*NO3`.
