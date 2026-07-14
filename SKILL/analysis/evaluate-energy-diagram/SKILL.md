---
name: evaluate-energy-diagram
description: Modular MESA skill for extracting experimental context and evaluating DFT reaction-energy tables from CSV or dictionary input. Supports HER and OER algorithmic analysis plus schema-based naming/evaluation for NO3RR and related reactions.
---

For MESA end-to-end use, read `SKILL/analysis/workflow.md` before applying this skill.

# Evaluate Energy Diagram

Use this skill when the user provides DFT reaction-coordinate energies for electrocatalyst performance evaluation.

## Required LLM interpretation protocol

The deterministic Python modules should be used whenever possible. If an LLM is used for any interpretation beyond deterministic calculations, it must follow this order:

1. Read `MYSKILL/electrochemical.md` first.
2. Apply its warnings before writing catalyst-performance conclusions.
3. Do not classify pure adsorption/desorption, solvent rearrangement, or other non-electrochemical step energies as overpotential.
4. Treat competing-reaction descriptors as selectivity warnings, not final selectivity predictions.
5. State uncertainty when PDS, RDS, limiting potential, or overpotential definitions are not explicitly supported by the input table.

This rule is also exposed in the output under `data.llm_guidance`.

## What this skill does

1. Extracts simple experimental context from `raw_text`, `materials`, `measurements`, `hypotheses`, `conditions`, and `targets`.
2. Loads energy data from CSV or dictionary input.
3. Canonicalizes reaction-coordinate labels such as `NO3*` and `*NO3`.
4. Detects or uses the requested reaction type.
5. Evaluates HER and OER with dedicated algorithmic descriptors.
6. Evaluates NO3RR, NO2RR, NRR, CO2RR, ORR, and generic reactions with deterministic schema/ranking logic.
7. Separates electrochemical PDS-like steps from pure adsorption/desorption steps when possible.
8. Produces ranking data and a Markdown report.

## Main Python entry point

The public API remains stable even though the implementation is modular:

```python
from MYSKILL.reaction_energy_evaluation import run
result = run(input_data, context={"workdir": "."})
```

CLI:

```bash
cd SKILL/analysis/evaluate-energy-diagram
python MYSKILL/reaction_energy_evaluation.py \
  --input ../../../project/<project_name>/inputs/energy_diagram.json \
  --output ../../../project/<project_name>/analysis/energy_diagram_evaluation.json \
  --verbose
```

## Modular structure

```text
MYSKILL/
├── reaction_energy_evaluation.py      # stable public run() + CLI entrypoint
├── core.py                            # orchestration layer
├── input_parsers.py                   # csv_text/csv_path/dictionary normalization
├── nomenclature.py                    # reaction detection and naming rules
├── electrochemistry.py                # transition classification, PDS helper logic, LLM reference rule
├── experimental.py                    # integrated TASK1-style context extraction
├── comparison.py                      # experiment comparison and competing reaction descriptors
├── reporting.py                       # markdown report generation
├── llm_guidance.py                    # machine-readable LLM interpretation protocol
├── chemistry.py                       # label normalization and formula helpers
├── constants.py                       # reaction metadata and shared constants
├── errors.py                          # custom validation errors
├── utils.py                           # shared utility helpers
└── evaluators/
    ├── her.py                         # HER descriptor evaluator
    ├── oer.py                         # OER 4-step evaluator
    ├── schema_reduction.py            # NO3RR/NO2RR/NRR/CO2RR/ORR-like evaluator
    └── generic.py                     # fallback uphill-step evaluator
```

## Notes

- Energies are assumed to be corrected free energies in eV unless the input says otherwise.
- HER ranking uses `abs(ΔG_H*)`.
- OER ranking uses `max(ΔG1..ΔG4) - 1.23 V` by default.
- Complex reactions such as NO3RR use reaction naming and schema rules documented in `references/reaction_nomenclature.md`.
- The deterministic evaluator does not call external APIs or LLMs.
