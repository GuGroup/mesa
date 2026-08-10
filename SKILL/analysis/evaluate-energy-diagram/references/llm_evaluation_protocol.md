# LLM Evaluation Protocol

This skill is deterministic and does not need an LLM to compute rankings. If a future LLM-assisted layer is used for interpretation, the LLM must follow this protocol.

## Required reading order

1. Read `MYSKILL/electrochemical.md` first.
2. Read the normalized output fields from `data.results`, `data.ranking`, `data.reaction_metadata`, and `data.warnings`.
3. Inspect `data.skill_handoff`.
4. Only then write interpretation or invoke a downstream skill.

## Mandatory electrochemical safeguards

- Do not classify pure adsorption/desorption energy as overpotential.
- Do not equate PDS and RDS unless kinetic barriers or kinetic modeling are provided.
- Do not treat competing-reaction descriptors as final selectivity predictions.
- State the assumed energy type: corrected free energy in eV unless the user states another convention.
- State uncertainty when pH, potential scale, reference electrode, solvent model, or coverage assumptions are missing.
- When all compared profiles are downhill, do not rank by the steepest slope,
  most negative intermediate, or largest overall driving force alone.
- Preserve uphill-step screening evidence when present; an uphill profile does
  not suppress the volcano handoff if the comparative ranking remains
  unresolved or tied.
- If `data.skill_handoff.triggered` is true, read
  `SKILL/figure/plot-sabatier-volcano/SKILL.md`, invoke the skill declared there
  exactly once with the emitted `handoff_payload`, and require a
  Sabatier-principle interpretation.
- Do not invoke `$plot-sabatier-volcano` automatically when the trigger is false.
- With only two catalysts, do not claim that the two points establish or fit an
  empirical volcano curve unless an independent relation is supplied.

## Output connection

The Python output includes the same rule in:

```text
data.llm_guidance.must_read_reference_before_interpretation
```

The deterministic routing request is available in:

```text
data.skill_handoff
next_action
```
