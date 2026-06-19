# TASK2: Reaction Energy Evaluation

## Task Config

```yaml
TASK_ID: TASK2
TASK_NAME: "Reaction Energy Evaluation"
TASK_GOAL: "Evaluate catalyst performance from reaction-coordinate CSV energy data and generate structured comparison outputs."
UPSTREAM_INPUT: "Structured experiment context or a direct CSV path containing reaction steps and catalyst energy columns."
DOWNSTREAM_OUTPUT: "Validated reaction evaluation data, catalyst ranking, limiting-step analysis, and Markdown-ready summary for experiment-computation comparison."
EXPECTED_ARTIFACTS: "Standard MESA skill output JSON, optional Markdown report, examples, tests."
EXTERNAL_TOOLS_OR_APIS: "None"
OWNER: "Unassigned"
```

## Overview

TASK2 evaluates reaction energy diagrams stored as CSV files. It supports NO3RR-specific overpotential interpretation and a HER-specific descriptor mode while keeping the output format consistent with other MESA TASK skills.

The task uses only the Python standard library. It does not run VASP, submit jobs, call APIs, or modify input CSV files.

## Skills

- `MYSKILL/reaction_energy_evaluation.py`: CSV validation, reaction-mode detection, limiting-step or descriptor evaluation, catalyst ranking, and report generation.
- `EXTSKILL/no_external_tools.py`: mockable no-op wrapper documenting that TASK2 currently has no external dependency.

## Interface

Both Python modules expose:

```python
def run(input_data: dict, context: dict | None = None) -> dict:
    ...
```

The main skill supports CLI execution:

```bash
python SKILL/TASK2_reaction_energy_evaluation/MYSKILL/reaction_energy_evaluation.py --input SKILL/TASK2_reaction_energy_evaluation/examples/input.example.json --output SKILL/TASK2_reaction_energy_evaluation/examples/output.generated.json --dry-run
```
