# LLM Evaluation Protocol

This skill is deterministic and does not need an LLM to compute rankings. If a future LLM-assisted layer is used for interpretation, the LLM must follow this protocol.

## Required reading order

1. Read `MYSKILL/electrochemical.md` first.
2. Read the normalized output fields from `data.results`, `data.ranking`, `data.reaction_metadata`, and `data.warnings`.
3. Only then write interpretation.

## Mandatory electrochemical safeguards

- Do not classify pure adsorption/desorption energy as overpotential.
- Do not equate PDS and RDS unless kinetic barriers or kinetic modeling are provided.
- Do not treat competing-reaction descriptors as final selectivity predictions.
- State the assumed energy type: corrected free energy in eV unless the user states another convention.
- State uncertainty when pH, potential scale, reference electrode, solvent model, or coverage assumptions are missing.

## Output connection

The Python output includes the same rule in:

```text
data.llm_guidance.must_read_reference_before_interpretation
```
