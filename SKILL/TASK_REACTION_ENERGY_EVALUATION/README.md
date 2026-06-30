# TASK_REACTION_ENERGY_EVALUATION

## Purpose

`TASK_REACTION_ENERGY_EVALUATION` is a modular MESA skill for evaluating DFT reaction-energy diagrams and extracting lightweight experimental context in the same workflow.

It integrates the former TASK1 experimental-information extraction role with the former TASK2 reaction-energy evaluation role, while keeping a stable public interface:

```python
from MYSKILL.reaction_energy_evaluation import run
result = run(input_data, context={"workdir": "."})
```

## Why the skill is modular

The previous monolithic reaction evaluator mixed input parsing, reaction detection, HER/OER/NO3RR logic, competing-reaction interpretation, experiment comparison, and report generation in one file. This version separates those concerns so that each reaction family and input style can be modified independently.

## Directory structure

```text
TASK_REACTION_ENERGY_EVALUATION/
├── SKILL.md
├── README.md
├── MYSKILL/
│   ├── __init__.py
│   ├── reaction_energy_evaluation.py
│   ├── core.py
│   ├── input_parsers.py
│   ├── nomenclature.py
│   ├── electrochemistry.py
│   ├── experimental.py
│   ├── experimental_information_extraction.py
│   ├── comparison.py
│   ├── reporting.py
│   ├── llm_guidance.py
│   ├── chemistry.py
│   ├── constants.py
│   ├── errors.py
│   ├── utils.py
│   ├── electrochemical.md
│   └── evaluators/
│       ├── __init__.py
│       ├── her.py
│       ├── oer.py
│       ├── schema_reduction.py
│       └── generic.py
├── EXTSKILL/
│   └── no_external_tools.py
├── references/
│   ├── input_schema.md
│   ├── reaction_nomenclature.md
│   └── llm_evaluation_protocol.md
├── examples/
│   ├── input_csv_no3rr.example.json
│   ├── input_dict_her.example.json
│   ├── input_dict_oer.example.json
│   └── no3rr_energy.example.csv
└── tests/
    ├── test_reaction_energy_evaluation.py
    └── test_module_boundaries.py
```

## Inputs

The evaluator supports CSV and dictionary input.

### CSV path

```json
{
  "csv_path": "examples/no3rr_energy.example.csv",
  "reaction_type": "NO3RR"
}
```

### CSV text

```json
{
  "csv_text": "step,CatA\n*,0\nH*,0.03\n",
  "reaction_type": "HER"
}
```

### Dictionary: steps + energies

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

### Dictionary: catalyst-centered step map

```json
{
  "reaction_type": "OER",
  "energy_data": {
    "NiOOH": {"*": 0.0, "*OH": 1.55, "*O": 2.75, "*OOH": 3.45},
    "CoOOH": {"*": 0.0, "*OH": 1.48, "*O": 2.68, "*OOH": 3.37}
  }
}
```

### Dictionary: row records

```json
{
  "reaction_type": "OER",
  "reaction_energies": [
    {"intermediate": "*", "NiOOH": 0.0, "CoOOH": 0.0},
    {"intermediate": "*OH", "NiOOH": 1.55, "CoOOH": 1.48},
    {"intermediate": "*O", "NiOOH": 2.75, "CoOOH": 2.68},
    {"intermediate": "*OOH", "NiOOH": 3.45, "CoOOH": 3.37}
  ]
}
```

## Outputs

The `data` field includes:

- `reaction_type`
- `reaction_metadata`
- `step_column`
- `steps`
- `catalysts`
- `ranking`
- `results`
- `experiment_comparison`
- `competing_reaction_summary`
- `llm_guidance`
- `markdown_report`
- `warnings`

## LLM interpretation rule

The deterministic evaluator does not call an LLM. If a future LLM layer is used for interpretation, it must read `MYSKILL/electrochemical.md` before making electrochemical claims. This is important because pure adsorption/desorption steps must not be described as overpotential.

## Run

From the skill directory:

```bash
python MYSKILL/reaction_energy_evaluation.py \
  --input examples/input_dict_oer.example.json \
  --output examples/output.generated.json \
  --verbose
```

From the parent directory:

```bash
python TASK_REACTION_ENERGY_EVALUATION/MYSKILL/reaction_energy_evaluation.py \
  --input TASK_REACTION_ENERGY_EVALUATION/examples/input_dict_oer.example.json \
  --output /tmp/mesa_reaction_output.json \
  --verbose
```

## Test

```bash
python -m unittest discover -s tests -v
```

or from the parent directory:

```bash
python -m unittest discover -s TASK_REACTION_ENERGY_EVALUATION/tests -v
```

## Limitations

- The skill evaluates tabulated reaction free-energy diagrams; it does not parse VASP outputs or run DFT.
- Energies are assumed to be compatible corrected free energies in eV.
- The PDS is a thermodynamic descriptor, not automatically the kinetic RDS.
- Competing reaction descriptors are selectivity warnings, not final selectivity predictions.
