# TASK1: Experimental Information Extraction

## Task Config

```yaml
TASK_ID: TASK1
TASK_NAME: "Experimental Information Extraction"
TASK_GOAL: "Extract structured experimental information, measurements, and researcher hypotheses from raw notes or upstream records."
UPSTREAM_INPUT: "Raw experimental description text plus optional structured metadata, measurements, materials, and hypotheses."
DOWNSTREAM_OUTPUT: "Validated JSON-serializable experimental context for literature search, VASP planning, and later experiment-computation comparison."
EXPECTED_ARTIFACTS: "Standard MESA skill output JSON, normalized extraction data, optional CLI output file, examples, tests."
EXTERNAL_TOOLS_OR_APIS: "None"
OWNER: "Unassigned"
```

## Overview

TASK1 is the first MESA pipeline task. It converts raw researcher-provided experimental notes and optional structured hints into a consistent machine-readable record.

The task is intentionally conservative. It uses Python standard-library logic and does not call external APIs or machine-learning services. Unknown or ambiguous values are preserved as uncertainties instead of being guessed.

## Skills

- `MYSKILL/experimental_information_extraction.py`: deterministic extraction and normalization logic.
- `EXTSKILL/no_external_tools.py`: mockable no-op external wrapper documenting that TASK1 has no external dependency.

## Interface

Both Python modules expose:

```python
def run(input_data: dict, context: dict | None = None) -> dict:
    ...
```

The main skill also supports CLI execution:

```bash
python SKILL/TASK1_experimental_information_extraction/MYSKILL/experimental_information_extraction.py --input SKILL/TASK1_experimental_information_extraction/examples/input.example.json --output SKILL/TASK1_experimental_information_extraction/examples/output.generated.json --dry-run
```
