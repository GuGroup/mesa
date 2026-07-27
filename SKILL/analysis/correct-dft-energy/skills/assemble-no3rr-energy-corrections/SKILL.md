---
name: assemble-no3rr-energy-corrections
description: Assemble and audit NO3RR DFT free-energy corrections for single-N nitrate-to-ammonia pathways using an HNO3(g) molecular reference, explicit HNO3 gas-to-liquid and liquid-to-NO3-(aq)+H+ thermodynamic-cycle terms, species-specific gas-phase corrections, CHE potential/pH bookkeeping, pathway closure, limiting potential, and bounded rankings. Use for Calle-Vallejo-style nitrate adsorption corrections, the literature 1.12 eV HNO3 error, NO3/NO2/NO/NHxOy pathways, or comparison of NHO/NOH-free routes. Do not apply one correction to every NOx species, substitute vacuum NO3- for aqueous nitrate, or infer kinetics/selectivity from endpoint thermodynamics.
---

For MESA end-to-end use, read `SKILL/analysis/workflow.md` first when that file exists.

# NO3RR Energy-Correction Bookkeeper

## Scope

Use this skill after relaxation, vibration/thermal correction, and evidence gating have produced endpoint free energies. It supports single-N pathways from aqueous nitrate to NH3, including alternative state orders such as routes that contain or omit `NHO`, `HNO`, or `NOH`.

The supplied helper separates four layers:

1. endpoint electronic/thermal/solvation free energy;
2. species-specific HNO3 and optional NH3 molecular corrections;
3. `HNO3(g) -> HNO3(l) -> NO3-(aq) + H+(aq)` transfer cycle;
4. potential and pH through CHE chemical-potential bookkeeping.

It does not calculate barriers, rates, Faradaic efficiency, or product selectivity.

## Mandatory correction policy

1. Never apply the HNO3 correction to all NOx species.
2. Never treat a vacuum-box `NO3-` calculation as aqueous nitrate without a documented solvation/countercharge/standard-state protocol.
3. A literature value such as `1.12 eV` must carry method and source provenance; the script does not insert it automatically.
4. Keep the HNO3 molecular error separate from phase-transfer terms such as `-0.075 eV` and `-0.317 eV`.
5. Do not provide both a complete `free_energy_ev` and additive component fields for the same record.
6. Keep NH3(g), NH3(aq), and NH4+(aq) distinct. This bounded helper uses a declared NH3 product reference.
7. Verify the full pathway closes to eight net electrons for nitrate-to-NH3.
8. Rank by PCET limiting potential/thermodynamic overpotential only after closure passes, while reporting adsorption or desorption steps that potential cannot rescue.

Read `references/no3rr-correction-policy.md` before interpreting results. Read
`references/literature-and-provenance.md` before assigning any HNO3, phase-transfer,
NH3, or other molecular correction.

## Quick start

```bash
python scripts/compute_no3rr_corrections.py \
  --input path/to/no3rr_endpoints.json \
  --outdir path/to/no3rr_outputs \
  --strict
```

The script accepts either MESA `free_energy_records` or a standalone `motifs + references + pathways` object. Read `references/input-schema.md`.

## Reference equations

For adsorbed nitrate on the neutral gas-reference scale:

```text
* + HNO3(g) -> *NO3 + 1/2 H2(g)
```

For any single-N adsorbate with composition `N1 H_h O_o`, define:

```text
b = 3 - o                         # H2O produced
n_pair = h + 2b                   # H+ + e- pairs used from nitrate
n_e,net = n_pair - 1              # net electrons consumed
H2 coefficient = n_e,net / 2
```

The neutral HNO3/H2 cumulative free energy is converted to the aqueous nitrate scale using the supplied transfer free energy and CHE chemical potentials. This makes the initial nitrate adsorption an electron-releasing step and the full nitrate-to-NH3 pathway an eight-electron reduction.

## Required outputs

The helper writes:

- `no3rr_bookkeeping.json`
- `no3rr_pathway_summary.csv/.json`
- `no3rr_step_summary.csv`
- `no3rr_profile_table.csv`
- `no3rr_pathway_ranking.csv/.json`
- `nitrate_adsorption_diagnostics.csv`
- `no3rr_warnings.csv`

## Claim policy

Allowed:

- “The HNO3 correction changes the absolute nitrate adsorption energy but cancels from internal steps sharing the same reference.”
- “Within the stated HNO3/CHE convention, pathway A has the more positive PCET limiting potential.”
- “The pathway without NHO remains thermodynamically admissible in the supplied endpoint network.”
- “Nitrate adsorption is still uphill at the PCET limiting potential and may require a separate interfacial treatment.”

Not allowed without separate evidence:

- “The 1.12 eV value is universal for PBE, every PAW data set, or every NOx species.”
- “The lowest thermodynamic pathway is kinetically dominant or selectively produces NH3.”
- “NH3 and NH4+ can be exchanged without an acid-base/standard-state cycle.”
