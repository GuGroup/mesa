# Assemble NO3RR Energy Corrections

A focused Codex Skill for single-N nitrate-to-ammonia free-energy bookkeeping
using an HNO3 reference cycle and CHE.

## What it does

- accepts MESA `free_energy_records` or standalone `motifs + references + pathways` JSON;
- resolves total free energies or an additive correction ledger;
- keeps the HNO3 molecular error separate from `HNO3(g) -> HNO3(l)` and
  `HNO3(l) -> NO3-(aq) + H+(aq)` terms;
- applies RHE/SHE potential and pH bookkeeping without inserting 1.12 eV automatically;
- supports custom single-N pathways, including routes containing or omitting
  `NHO`, `HNO`, or `NOH`;
- verifies state compositions, eight-electron nitrate-to-NH3 closure, and
  potential-independent uphill steps;
- excludes closure/evidence failures from ranking while retaining diagnostics;
- exports deterministic JSON and CSV artifacts.

## Run

```bash
python3 scripts/compute_no3rr_corrections.py \
  --input assets/example_no3rr_input.json \
  --outdir no3rr_outputs \
  --strict
```

For a pH-0 software reproduction of the Calle-Vallejo bookkeeping shift:

```bash
python3 scripts/compute_no3rr_corrections.py \
  --input assets/example_no3rr_calle_vallejo_pH0_input.json \
  --outdir no3rr_pH0_outputs \
  --strict
```

## Validate

```bash
python3 scripts/validate_skill.py
```

All bundled endpoint energies are synthetic test values. The `1.12 eV` entry is
included only as a provenance-tagged literature example, not as a universal
PBE/NOx correction.

## Important boundary

This Skill supports one nitrogen atom ending as declared NH3. It does not model
N2/N2O formation, NH4+ without an acid-base cycle, urea/C-N coupling, barriers,
rates, current density, Faradaic efficiency, or selectivity.
