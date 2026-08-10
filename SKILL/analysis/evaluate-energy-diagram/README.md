# Evaluate Energy Diagram

## Purpose

`evaluate-energy-diagram` is a modular MESA skill for evaluating DFT
reaction-energy diagrams and extracting lightweight experimental context in the
same workflow.

It combines experimental-context extraction with reaction-energy evaluation
while keeping a stable public interface:

```python
from MYSKILL.reaction_energy_evaluation import run
result = run(input_data, context={"workdir": "."})
```

## Why the skill is modular

The previous monolithic reaction evaluator mixed input parsing, reaction detection, HER/OER/NO3RR logic, competing-reaction interpretation, experiment comparison, and report generation in one file. This version separates those concerns so that each reaction family and input style can be modified independently.

## Directory structure

```text
SKILL/analysis/evaluate-energy-diagram/
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
│   ├── routing.py
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
- `all_downhill_across_catalysts`
- `unique_best_catalyst_identified`
- `skill_handoff`

## Unresolved-ranking routing

After normalization and reaction-specific evaluation, the skill checks whether
the diagram identifies exactly one thermodynamic best catalyst:

1. Require at least two catalysts, numerical ranking rows, and evaluable
   transitions.
2. Treat the result as unresolved when reaction-specific ranking flags are
   unresolved or multiple catalysts share the top score within the configured
   tolerance.
3. Request a handoff to `SKILL/figure/plot-sabatier-volcano` for unresolved or
   tied comparisons, including mixed downhill/uphill profile sets.
4. Keep common-basis downhill diagnostics and uphill-step/PDS screening in the
   payload; these remain evidence but no longer gate the handoff.

The deterministic Python program emits, but does not itself execute, the
following orchestration result:

```json
{
  "next_action": {
    "recommendation": "invoke_skill",
    "target_skill": "plot-sabatier-volcano",
    "target_skill_path": "SKILL/figure/plot-sabatier-volcano",
    "invocation": "$plot-sabatier-volcano",
    "invocation_strategy": "read_target_skill_md_then_invoke_declared_name",
    "condition": "comparative_thermodynamic_ranking_not_unique",
    "handoff_payload": {}
  }
}
```

The handoff payload contains the normalized energy table in dictionary and CSV
form, screening rankings, catalyst-level uphill/downhill diagnostics, optional
descriptor hints, and explicit Sabatier constraints. It tells the downstream
skill to preserve uphill evidence and not equate a steeper downhill slope with
better activity.

Relevant optional inputs:

```json
{
  "enable_unresolved_volcano_handoff": true,
  "downhill_trigger_scope": "all_steps",
  "downhill_tolerance_ev": 1e-09,
  "energy_reference_potential_v": 0.0,
  "equilibrium_potential_v": -0.12,
  "step_electron_counts": [0, 1, 1, 1],
  "volcano_descriptor": null,
  "volcano_activity_metric": null
}
```

`downhill_trigger_scope` can be `all_steps` or `electrochemical`. The default
`all_steps` applies uphill/downhill diagnostics to the full represented profile;
these diagnostics do not by themselves decide whether the handoff triggers.

## LLM interpretation rule

The deterministic evaluator does not call an LLM. If a future LLM layer is used for interpretation, it must read `MYSKILL/electrochemical.md` before making electrochemical claims. This is important because pure adsorption/desorption steps must not be described as overpotential.

When `skill_handoff.triggered` is true, the host agent must also read that file,
then read `SKILL/figure/plot-sabatier-volcano/SKILL.md`, before passing the payload
to the skill declared there. The downstream analysis
must apply the Sabatier principle and must not infer that stronger binding or a
more negative overall energy is automatically superior.

## Run

From the repository root:

```bash
cd SKILL/analysis/evaluate-energy-diagram
python MYSKILL/reaction_energy_evaluation.py \
  --input ../../../project/<project_name>/inputs/energy_diagram.json \
  --output ../../../project/<project_name>/analysis/energy_diagram_evaluation.json \
  --verbose
```

Create the input JSON from one of the inline schemas in this README or
`references/input_schema.md`; this repository does not bundle run-specific
example inputs.

## Limitations

- The skill evaluates tabulated reaction free-energy diagrams; it does not parse VASP outputs or run DFT.
- Energies are assumed to be compatible corrected free energies in eV.
- The PDS is a thermodynamic descriptor, not automatically the kinetic RDS.
- Competing reaction descriptors are selectivity warnings, not final selectivity predictions.
- With only two catalysts, the volcano skill may position the catalysts on an
  established/model-derived curve, but two points alone should not be used to
  fit a new empirical volcano relation.
