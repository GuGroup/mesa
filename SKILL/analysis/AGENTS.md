# ANALYSIS DOMAIN

## OVERVIEW

- Convert validated, recipe-backed calculation outputs into bounded scientific
  evidence; do not launch, repair, or silently replace calculations here.
- Treat `workflow.md` as the domain gate, then read the narrowest leaf
  `SKILL.md` and only the references it routes to.
- The active directory contains five skills even though `workflow.md` currently
  catalogs only three: `analyze-dband-center`,
  `assemble-alkaline-her-descriptors`, `charge-flow-analyzer`,
  `construct-energy-diagram`, and `evaluate-energy-diagram`.

## WHERE TO LOOK

| Need | Location | Boundary |
|---|---|---|
| Domain readiness and claim policy | `workflow.md` | Existing evidence only |
| DOS-derived d-band descriptors | `analyze-dband-center/` | Converged projected DOS |
| Alkaline HER free-energy bookkeeping | `assemble-alkaline-her-descriptors/` | Thermodynamic descriptors, not kinetics |
| CHGCAR redistribution evidence | `charge-flow-analyzer/` | Controlled compatible density differences |
| OUTCAR-based free-energy profile | `construct-energy-diagram/` | Narrow CHON ADS/GAS model |
| Energy-table evaluation | `evaluate-energy-diagram/` | Deterministic HER/OER/schema ranking |
| Raw trajectory/endpoint verdict | `../calculation/analyze-calculation-results/` | Run before higher-level analysis |
| Recipe evidence validation | `../orchestration/validate-recipe-execution/` | Final manuscript-readiness gate |
| Missing required artifacts | `../orchestration/record-missing-evidence/` | Keep gaps explicit |

## CONVENTIONS

- Confirm source recipe, structures, energies, vibration/bookkeeping artifacts,
  and recipe-local `execution_manifest.json` before interpreting results.
- Gate relaxations and trajectories with `analyze-calculation-results`; preserve
  `accepted`, `accepted-with-caveat`, `exploratory`, `failed`, or `excluded`.
- Carry source paths, units, transforms, warnings, unsupported physics, and
  acceptance state into tables, figures, reports, and manuscript handoffs.
- State exactly when potential, pH, solvation, barriers, kinetics, charge/DOS,
  entropy/vibration, or experimental comparability is outside the evidence.
- `mesa-general` runs deterministic bookkeeping/evaluation skills;
  `mesa-modeling` runs ASE/pymatgen/numpy/matplotlib analysis. Resolve the exact
  binding in `DEPENDENCY/runtimes.yaml`; commands are normally skill-relative.
- `scripts/` entries are standalone CLIs with sibling imports.
  `evaluate-energy-diagram/MYSKILL/` is an in-process package with stable
  `reaction_energy_evaluation.run`; its `EXTSKILL` is intentionally a no-op.
- Use deterministic outputs for calculations and rankings. If an LLM interprets
  electrochemistry, follow `evaluate-energy-diagram/MYSKILL/electrochemical.md`.

## ANTI-PATTERNS

- Do not run new VASP/UMA work, repair structures, or infer missing evidence in
  analysis; hand the task back to calculation/orchestration.
- Do not replace free energy with electronic energy, kinetics with
  thermodynamics, charge/DOS evidence with geometry, or charged states with
  neutral gas references.
- Do not call descriptor rankings overpotential, rate, selectivity, or complete
  mechanism proof; alkaline `Delta G_H` alone is not full alkaline HER evidence.
- Do not accept unconverged DOS/CHGCAR inputs or compare charge-density figures
  made with incompatible formulas, grids, cells, thresholds, or color scales.
- Do not import `construct-energy-diagram/MYSKILL/tools/start.py` for side
  effects. Invoke its explicit CLI with reaction, mapping, and output paths.
- Do not treat examples or smoke commands as regression tests; use each
  skill's tracked `tests/` directory when one is present.
