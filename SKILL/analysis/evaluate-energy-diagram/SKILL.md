---
name: evaluate-energy-diagram
description: Evaluate DFT reaction-energy tables from CSV or dictionary input. When a multi-catalyst diagram does not identify one unique thermodynamic best catalyst, including mixed downhill/uphill or tied cases, hand off to SKILL/figure/plot-sabatier-volcano for Sabatier analysis.
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

## Conditional handoff to `SKILL/figure/plot-sabatier-volcano`

After running the deterministic evaluator, inspect `data.skill_handoff`.

1. When `data.skill_handoff.triggered` is `true`, read
   `MYSKILL/electrochemical.md` first.
2. Then read `SKILL/figure/plot-sabatier-volcano/SKILL.md` and invoke the
   skill declared there exactly once with `data.skill_handoff.handoff_payload`.
   The directory-name fallback invocation is `$plot-sabatier-volcano`.
3. Preserve any uphill-step/PDS screening evidence, but do not declare a unique
   best catalyst before the downstream Sabatier analysis resolves or bounds it.
4. Do not invoke `$plot-sabatier-volcano` automatically when
   `data.skill_handoff.triggered` is `false`.
5. Trigger only when at least two catalysts are evaluable and the thermodynamic
   ranking is unresolved or its top score is tied within the configured energy
   tolerance. Uphill steps do not suppress this trigger.
6. Do not trigger when the evaluator identifies one unique thermodynamic best
   catalyst, or when fewer than two catalyst rankings are evaluable.
7. If the target skill is unavailable, preserve and return the handoff payload;
   do not pretend that a volcano plot was generated.

The Python module cannot activate a Codex skill by itself. It emits a
machine-readable `next_action` with `recommendation: invoke_skill`; the Codex
host follows the instruction above.

## What this skill does

1. Extracts simple experimental context from `raw_text`, `materials`, `measurements`, `hypotheses`, `conditions`, and `targets`.
2. Loads energy data from CSV or dictionary input.
3. Canonicalizes reaction-coordinate labels such as `NO3*` and `*NO3`.
4. Detects or uses the requested reaction type.
5. Evaluates HER and OER with dedicated algorithmic descriptors.
6. Evaluates NO3RR, NO2RR, NRR, CO2RR, ORR, and generic reactions with deterministic schema/ranking logic.
7. Separates electrochemical PDS-like steps from pure adsorption/desorption steps when possible.
8. Produces ranking data and a Markdown report.
9. Routes multi-catalyst comparisons without one unique thermodynamic best to
   `SKILL/figure/plot-sabatier-volcano`, including mixed downhill/uphill cases.

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
├── routing.py                         # unresolved/tied-ranking handoff to plot-sabatier-volcano
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
- The deterministic evaluator does not directly execute another Codex skill;
  it emits the exact conditional handoff for the host agent.
