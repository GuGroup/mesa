---
name: correct-dft-energy
description: Route, execute, and audit catalyst DFT free-energy corrections for either four-step AEM OER or single-N nitrate-to-NH3 NO3RR. Use when Codex must correct endpoint energies, assemble CHE free-energy profiles, check thermodynamic-cycle closure, calculate limiting potentials or bounded rankings, or choose between the bundled OER and NO3RR correction workflows. Accepts standalone JSON or compatible MESA free-energy records and delegates to the reaction-specific skill without running electronic-structure jobs.
---

# Correct DFT Energy

Use this skill as the independent entry point for the bundled catalyst
free-energy correction workflows. Do not run relaxations, vibrations, VASP, or
other electronic-structure calculations from this skill.

## Select the workflow

- Use `oer` for the four-state AEM sequence `clean`, `OH`, `O`, and `OOH`.
- Use `no3rr` for a single-N nitrate-to-NH3 pathway with declared references
  and pathway states.
- Use `auto` only when the input contains unambiguous reaction markers.
- Stop and request `--mode` when automatic detection is ambiguous.

Before interpreting or publishing results, read the selected child skill
completely:

- OER: `skills/assemble-oer-energy-corrections/SKILL.md`
- NO3RR: `skills/assemble-no3rr-energy-corrections/SKILL.md`

Read only the policy, provenance, and input-schema references required by the
selected child skill.

## Execute

Run from any working directory:

```bash
python /path/to/correct-dft-energy/scripts/run_correct_dft_energy.py \
  --mode auto \
  --input /path/to/endpoints.json \
  --outdir /path/to/correction-results \
  --strict
```

Pass reaction-specific options unchanged after the common options. The runner
prints the selected workflow and child command before execution and returns the
child process exit code.

## Composition contract

To remain compatible with other skills:

1. Treat input artifacts as read-only.
2. Write only to the explicit `--outdir`.
3. Preserve endpoint evidence states, caveats, provenance, temperature,
   standard state, pH, potential, and electrode scale.
4. Do not invent missing energies or corrections.
5. Keep electronic, vibrational, thermal, solvation, phase-transfer,
   standard-state, molecular-reference, and CHE terms distinguishable.
6. Do not reinterpret thermodynamic rankings as kinetics or selectivity.
7. Return generated JSON/CSV artifacts for downstream diagram, evaluation,
   manuscript, or evidence-validation skills.

Use the specialized child skill directly when the reaction is already known;
use this router when a stable common entry point or automatic dispatch is
useful.
