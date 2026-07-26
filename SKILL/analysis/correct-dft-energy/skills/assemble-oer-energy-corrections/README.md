# Assemble OER Energy Corrections

A focused Codex Skill for four-step adsorbate-evolution-mechanism (AEM) OER
free-energy bookkeeping.

## What it does

- accepts MESA `free_energy_records` or standalone `motifs + references` JSON;
- resolves either total free energies or an additive correction ledger;
- constructs `G(O2)` from a documented `H2O/H2` thermodynamic cycle, or audits a declared direct-O2 reference;
- applies CHE potential and pH terms on RHE or SHE scales;
- calculates four AEM step energies, `U_L`, `U_eq`, thermodynamic overpotential, PDS, and profiles;
- checks thermodynamic closure and blocks invalid/evidence-failed entries from ranking;
- exports deterministic JSON and CSV artifacts.

## Run

```bash
python3 scripts/compute_oer_corrections.py \
  --input assets/example_oer_input.json \
  --outdir oer_outputs \
  --strict
```

## Validate

```bash
python3 scripts/validate_skill.py
```

The example energies are synthetic software-test data. They are not a physical
prediction for a real catalyst.

## Important boundary

This Skill covers the four-state AEM (`*`, `*OH`, `*O`, `*OOH`). It does not
model lattice-oxygen mechanisms, barriers, rates, current density, Tafel slopes,
active-site populations, or a universal adsorbate-solvation correction.
