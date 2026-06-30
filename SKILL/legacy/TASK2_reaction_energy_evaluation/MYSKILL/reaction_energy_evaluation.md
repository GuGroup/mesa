# Reaction Energy Evaluation

## Purpose

Evaluate catalyst performance from reaction-coordinate CSV files by validating columns, calculating stepwise energy changes, determining performance descriptors, ranking catalysts, and producing Markdown-ready summaries.

## Position in MESA Pipeline

This skill fits after structured experimental information extraction and after calculated reaction energies become available. It prepares structured comparison data for downstream experiment-computation comparison and iterative decision-making.

## Inputs

`input_data` is a JSON-serializable dictionary with these fields:

- `csv_path`: Path to a CSV file. Required unless `csv_text` is provided.
- `csv_text`: CSV content as text. Optional alternative to `csv_path`.
- `reaction_type`: Optional. Supported values are `NO3RR`, `HER`, or `auto`.
- `experiment`: Optional dictionary mapping catalyst names to experimental overpotential or descriptor values in V.
- `report_path`: Optional path for a generated Markdown report.

The CSV must contain one step column followed by one or more numeric catalyst columns.

## Outputs

The `data` field contains:

- `reaction_type`: Detected or requested reaction type.
- `step_column`: Name of the first CSV column.
- `steps`: Reaction-coordinate labels.
- `catalysts`: Catalyst column names.
- `ranking`: Catalyst performance ranking.
- `results`: Per-catalyst transitions and descriptors.
- `markdown_report`: Human-readable report text.
- `warnings`: Non-fatal validation or interpretation warnings.

## Algorithm

1. Load CSV from `csv_path` or `csv_text`.
2. Validate that the first column contains reaction steps and remaining columns are numeric catalyst energies.
3. Detect reaction type when `reaction_type` is `auto`.
4. For NO3RR, compute consecutive `dG`, exclude `*NH3 -> NH3` from PDS determination, include `NO3- -> *NO3`, select the largest positive included `dG` as PDS, and estimate `eta_calc = dG_PDS`.
5. For HER, use `dG_H*` from the `H+ -> *H` transition when present and rank catalysts by `abs(dG_H*)` closest to zero.
6. Compare calculated values with optional experimental values.
7. Generate a compact Markdown report.
8. Return the standard MESA skill output structure.

## Dependencies

Python standard library only: `argparse`, `csv`, `io`, `json`, `pathlib`, and `typing`.

## Failure Modes

- Missing CSV input returns `status: failure`.
- Malformed CSV or non-numeric catalyst values return `status: failure`.
- Unknown reaction type returns `status: failure`.
- Missing expected reaction labels returns `status: partial` with warnings when evaluation can still proceed.

## Example

Input:

```json
{
  "csv_path": "no3rr_diagram.csv",
  "reaction_type": "NO3RR",
  "experiment": {"NiCoO2": 0.2}
}
```

Output:

```json
{
  "status": "success",
  "task_id": "TASK2",
  "skill": "reaction_energy_evaluation",
  "data": {
    "reaction_type": "NO3RR",
    "ranking": [
      {"catalyst": "NiCoO2", "score": 0.239315395}
    ]
  }
}
```

## Validation

Run the unit tests:

```bash
python -m unittest discover -s SKILL/TASK2_reaction_energy_evaluation/tests
```

Run the CLI:

```bash
python SKILL/TASK2_reaction_energy_evaluation/MYSKILL/reaction_energy_evaluation.py --input SKILL/TASK2_reaction_energy_evaluation/examples/input.example.json --output /tmp/mesa_task2_output.json --dry-run
```

## Limitations

The skill evaluates tabulated reaction energy diagrams only. It does not parse VASP outputs directly, perform electronic-structure calculations, search literature, or infer missing thermodynamic corrections.
