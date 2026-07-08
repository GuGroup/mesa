---
name: assemble-alkaline-her-descriptors
description: Assemble bounded alkaline HER free-energy descriptors and motif rankings from relaxed/vibrated endpoint free energies. Use when Codex needs to compare MoS2 or catalyst motifs with clean, H2O*, OH*, H*, H*+OH*, and H2* states under a pH/RHE CHE-style bookkeeping convention, create descriptor_summary/activity_ranking artifacts, or check that downstream alkaline HER claims stay thermodynamic rather than kinetic.
---

For MESA end-to-end use, read `SKILL/analysis/workflow.md` before applying this skill.

# Alkaline HER Free-Energy Bookkeeper

## Scope

Use this skill after structure relaxation, vibration/thermal correction, and
evidence gating have produced endpoint free energies. The skill computes a
bounded descriptor table for alkaline HER motifs:

- `Delta G_H2O = G(H2O*) - G(*) - G(H2O)`
- `Delta G_H+OH = G(H*+OH*) - G(*) - G(H2O)`
- `Delta G_H = G(H*) - G(*) - 0.5 G(H2)`
- `Delta G_OH = G(OH*) - G(*) - (G(H2O) - 0.5 G(H2))`
- `Delta G_H2_ads = G(H2*) - G(*) - G(H2)`

Do not use this skill to claim barriers, current density, overpotential, Tafel
slope, explicit double-layer physics, or explicit solvated OH- energetics. It is
a bounded thermodynamic descriptor workflow.

## Quick Start

The helper script accepts either a generic motif/state JSON or an existing
MESA-style file containing `free_energy_records`.

```bash
python scripts/compute_alkaline_her_descriptors.py \
  --input path/to/free_energy_bookkeeping.json \
  --outdir path/to/free_energy_outputs \
  --ph 14 \
  --potential-rhe 0
```

If the H2O reference is gas-phase and the liquid correction is not already
included in `free_energy_ev`, pass it explicitly:

```bash
python scripts/compute_alkaline_her_descriptors.py \
  --input endpoints.json \
  --outdir free_energy \
  --h2o-reference-correction-ev -0.088
```

For the generic input schema, read `references/input-schema.md`.

## Required Inputs

Each motif must have these surface states:

- `clean`
- `H2O`
- `OH`
- `H`
- `H_OH`
- `H2`

The input must also provide gas/reference entries for `H2` and `H2O`. The
`free_energy_ev` field should already include any selected electronic,
zero-point, entropy, and phase-reference corrections unless a correction is
passed on the command line.

## Outputs

The script writes:

| Artifact | Purpose |
| --- | --- |
| `alkaline_her_bookkeeping.json` | Complete machine-readable output with reference policy, descriptors, rankings, and state table. |
| `descriptor_summary.csv` / `.json` | Motif-level descriptors used in claims and tables. |
| `activity_ranking.csv` / `.json` | Ranking by bounded activity score. |
| `bounded_profile_table.csv` | Relative profile values for plotting or manuscript tables. |

The bounded activity score is:

```text
abs(Delta G_H)
+ max(Delta G_H2O, 0)
+ max(H2 desorption free energy, 0)
+ max(Delta G_OH - 0.5, 0)
```

Lower score means a better bounded descriptor balance inside this convention.
Do not treat the score as an overpotential.

## Claim Policy

Use strong but bounded language:

- Allowed: "motif A gives the best bounded alkaline HER descriptor balance
  among the tested motifs."
- Allowed: "the ranking is directionally consistent with an experimental
  activity trend."
- Not allowed: "motif A predicts the measured overpotential" unless a separate
  kinetic/current model exists.
- Not allowed: substituting geometry-only information for missing charge,
  solvation, barrier, or DOS evidence.
