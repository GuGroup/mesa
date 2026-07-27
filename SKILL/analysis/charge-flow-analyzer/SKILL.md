---
name: charge-flow-analyzer
description: >-
  Analyze VASP CHGCAR charge-density differences for catalyst slabs,
  adsorbates, dopants, alloys, and HEA active-site comparisons. Use when Codex
  needs to compute or interpret charge flow, charge-density-difference maps,
  adsorption-induced polarization, dopant/alloy-induced charge redistribution,
  or CHGCAR-based evidence for catalyst trend explanations.
---

# Charge Flow Analyzer

## Overview

For MESA end-to-end use, read `SKILL/analysis/workflow.md` before applying this
skill.

Use this skill to turn controlled CHGCAR differences into bounded catalyst
claims. It is for charge-density-difference analysis, not for running VASP,
relaxing structures, or proving catalytic activity by itself.

## Prerequisites — VASP Single-Point CHGCAR Calculations

This skill requires **converged single-point (static) VASP calculations** that
write CHGCAR files for every density term in the chosen formula. Start from the
converged adsorbed geometry, then create frozen reference structures in the same
cell/grid protocol.

```text
# Required for every CHGCAR term
IBRION  = -1          # No ionic relaxation
NSW     = 0           # Static single point
NELM    = 300         # Give difficult slab/static SCF enough cycles
EDIFF   = 1E-6        # Tight electronic convergence for density differences
LCHARG  = .TRUE.      # Write CHGCAR
LWAVE   = .FALSE.     # Skip WAVECAR unless a follow-up run needs it

# Recommended when Bader-style charge partitioning may be added later
LAECHG  = .TRUE.      # Write AECCAR0/AECCAR2 for all-electron charge analysis

# Keep identical across Ads*, *, and Ads references
ENCUT, PREC, ISPIN, MAGMOM, KPOINTS, smearing, functional, PAW set,
DFT+U, dispersion, solvation, dipole correction, and FFT grid policy.
```

Do not use non-self-consistent charge-density settings such as `ICHARG = 11`
for the CHGCARs that will be subtracted. If reusing a previous WAVECAR/CHGCAR
as the starting guess, keep the final run self-consistent and converged.

For adsorption, generate three static CHGCARs with the same lattice and grid:
`Ads*`, clean `*` frozen in the adsorbed slab geometry, and isolated `Ads`
frozen in the adsorbed position inside the same slab cell.

## Runtime

Run the analyzer in the existing modeling environment:

```bash
mamba run -n modeling python scripts/analyze_charge_flow.py ...
```

The current script uses `pymatgen`, `numpy`, `matplotlib`, and `scikit-image`
inside the `mesa-modeling` runtime. Keep the default backend limited to
dependencies declared for that runtime unless the user explicitly asks to change
the environment.

Install `scikit-image` through conda-forge, not pip, on low-glibc/GCC servers.
The environment spec pins `<0.26` to avoid the `0.26.0` sdist build path that
can pull a source NumPy build requiring GCC >= 9.3.

## Workflow

1. Classify the comparison before doing arithmetic:
   `adsorption`, `substitutional-dopant`, `modified-vs-pristine`, or
   `differential-adsorption`.
2. Read `references/charge-flow-claim-guide.md` and choose the exact formula.
   Never infer the formula from filenames.
3. Confirm every CHGCAR term was generated with compatible cell, grid, origin,
   spin/charge settings, functional, PAW setup, cutoff, k-points, and geometry
   protocol. Adsorption references should normally be frozen in the combined
   adsorbed cell.
4. Run `scripts/analyze_charge_flow.py difference` with explicit weighted terms.
5. Inspect the JSON warnings and integral residuals before interpreting figures.
6. Inspect `z_profile.csv` and `dipole_summary.json` for surface-normal
   displacement trends; treat them as charge-displacement descriptors, not
   unique atomic charges or work-function values.
7. Use only the allowed claim templates from the guide unless adsorption
   energies, PDOS/d-band trends, Bader/DDEC/Hirshfeld charges, vibration, or
   barrier evidence supports a stronger mechanistic statement.

## Quick Start

Adsorbate-induced charge redistribution:

```bash
mamba run -n modeling python scripts/analyze_charge_flow.py difference \
  --outdir charge_flow_ads \
  --comparison adsorption \
  --term combined=1:adsorbed/CHGCAR \
  --term clean_slab=-1:clean_slab_frozen/CHGCAR \
  --term adsorbate=-1:adsorbate_frozen_in_cell/CHGCAR \
  --write-delta-chgcar
```

Substitutional dopant redistribution with electron-count correction:

```bash
mamba run -n modeling python scripts/analyze_charge_flow.py difference \
  --outdir charge_flow_dopant \
  --comparison substitutional-dopant \
  --term doped=1:doped/CHGCAR \
  --term pristine=-1:pristine/CHGCAR \
  --term dopant_atom=-1:dopant_atom_in_cell/CHGCAR \
  --term host_atom=1:host_atom_in_cell/CHGCAR
```

Smoke-test the script without user CHGCAR files:

```bash
mamba run -n modeling python scripts/analyze_charge_flow.py example \
  --outdir /tmp/charge_flow_example
```

## Outputs

The analyzer writes:

| Artifact | Purpose |
| --- | --- |
| `charge_flow_summary.json` | Formula, weighted terms, grid/cell checks, raw-CHGCAR and normalized-density integral conventions, extrema, warnings, and output paths. |
| `plane_average_z.csv` | Backward-compatible z-grid, plane-averaged raw delta, and cumulative integral diagnostics. |
| `z_profile.csv` | Normalized slab-normal profile: `z_A`, plane-averaged `Delta n`, lateral integral `Delta lambda`, and cumulative charge displacement from bottom/top. |
| `dipole_summary.json` | Delta-density-derived electron moment and sign-converted electrostatic dipole descriptor; not a work-function result without `LOCPOT`. |
| `plane_average_z.png` | Side-A slab/isodensity view paired with a vertical plane-averaged delta-density profile along the slab normal. |
| `delta_density_slices.png` | Orthogonal delta-density contour slices through the strongest lobe. **Off by default; pass `--slices` to render** (the isosurface + z-profile are the primary views). |
| `delta_density_isosurface.png` | Marching-cubes positive/negative isosurface mesh in fixed `top`, `side_a`, and `side_b` slab views with atom and unit-cell context. |
| `charge_flow_report.md` | Human-readable interpretation scaffold with allowed and disallowed claims. |
| `delta.CHGCAR` | Optional VASP-compatible delta-density file for VESTA/ParaView-style inspection. |

## Rendering Policy

Use this rendering decision:

- Select the existing pure ASE + matplotlib slab-renderer pattern from
  `render-adsorbate-structure-grid` and `analyze-relaxation-results` for
  atom/slab context. It is already built for comparable catalyst slabs: fixed
  top/side views, unit-cell wireframes, fixed-atom marks, and adsorbate-scoped
  bonds when metadata exists.
- Implement charge-density surface figures inside this skill using `xyzrender`
  as the design reference: periodic unit-cell context, positive/negative lobe
  colors, volumetric slice/surface views, and exportable publication figures.
  The current implementation is `scripts/charge_flow_rendering.py`, which writes
  orthogonal contour slices plus a marching-cubes positive/negative isosurface
  mesh in fixed `top`, `side_a`, and `side_b` slab views using `scikit-image`
  inside the `modeling` runtime.

Do not hand off rendering to `xyzrender` as a replacement for this skill. If a
future version adds another renderer, keep the same fixed thresholds, color
scale, and camera policy across compared slabs.

## Boundaries

- Do not claim formal oxidation states or exact electron transfer from
  charge-density difference alone.
- Do not claim activity, selectivity, overpotential, or rate without energetic
  or kinetic evidence.
- Do not decompose donation/back-donation from scalar delta-density alone; pair
  it with orbital-resolved evidence.
- Do not compare isosurface sizes across systems unless the same formula,
  grid/cell protocol, threshold, and color scale were used.
- Do not treat relaxed pristine-vs-modified density differences as purely
  electronic redistribution; geometry displacement is mixed in.
