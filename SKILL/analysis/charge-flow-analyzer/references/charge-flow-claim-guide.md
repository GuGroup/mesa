# Charge-Flow / Charge-Density-Difference Claim Guide for Catalysis

## Purpose

Use CHGCAR charge-density-difference analysis to explain where electron density
accumulates or depletes when a catalyst slab binds an adsorbate, is doped, is
alloyed, or presents a different HEA local environment. The output supports
bounded catalysis claims about polarization and redistribution; it does not by
itself prove activity, selectivity, oxidation state, or orbital mechanism.

## Formula Registry

All charge-flow claims are reference-defined. State the formula before
interpreting any plot.

Adsorbate-induced redistribution:

```text
Delta rho_ads(r) = rho(Ads*)(r) - rho(*)(r) - rho(Ads)(r)
```

Use this default for adsorption-induced polarization and interfacial density
redistribution. The `*` and `Ads` references should normally be computed in the
same cell, same FFT grid, same settings, and frozen adsorbed geometry as
`Ads*`. Do not use only `rho(Ads*) - rho(Ads)` as a charge-flow map: that leaves
the clean slab density in the result.

For adsorption, prepare these static CHGCAR inputs:

- `Ads*`: the full adsorbed slab after geometry optimization;
- `*`: remove the adsorbate, keep the slab atoms frozen at the adsorbed
  geometry, and keep the same cell/grid/settings;
- `Ads`: keep only the adsorbate frozen at its adsorbed position in the same
  slab cell/grid/settings.

Modified versus pristine slab:

```text
Delta rho_mod(r) = rho(modified slab)(r) - rho(pristine slab)(r)
```

Use this only for a comparable slab-density difference. If the atoms move or
composition changes without controlled references, electronic redistribution
and density displacement are mixed.

Substitutional dopant redistribution:

```text
Delta rho_sub(r) = rho(A_N-1 B_1)(r) - rho(A_N)(r) - rho(B_1)(r) + rho(A_1)(r)
```

Use this when the intended claim is dopant-induced redistribution without a
simple net electron-count artifact.

Differential adsorption response:

```text
Delta Delta rho_ads =
  [rho(mod+Ads) - rho(mod) - rho(Ads)]
  - [rho(pris+Ads) - rho(pris) - rho(Ads)]
```

Use this for claims that a dopant, alloy, or HEA local environment changes the
adsorption-induced charge-flow pattern.

## Single-Point CHGCAR Generation

Run converged static single-point calculations for every density term before
using this analyzer. Use the same settings across all terms.

```text
IBRION  = -1
NSW     = 0
NELM    = 300
EDIFF   = 1E-6
LCHARG  = .TRUE.
LWAVE   = .FALSE.
LAECHG  = .TRUE.   # optional but recommended if Bader-style analysis may follow
```

Keep `ENCUT`, `PREC`, PAW potentials, functional, `ISPIN`, `MAGMOM`, smearing,
k-points, DFT+U, dispersion, solvation, dipole corrections, and FFT-grid policy
identical. Do not subtract a relaxed reference from an adsorbed structure unless
the claim explicitly includes geometric density displacement. Do not use
non-self-consistent `ICHARG = 11` CHGCARs for charge-flow subtraction.

## Sign and Units

Positive `Delta rho` means electron accumulation relative to the chosen
references. Negative `Delta rho` means electron depletion. For dipoles and
work-function reasoning, remember that electron accumulation carries negative
physical charge, so the electrostatic dipole sign is opposite the electron
density moment sign.

VASP CHGCAR values are not plotted blindly as `e/A^3`. The skill reports both a
raw residual diagnostic and a normalized density convention. For a cell volume
`V`, slab-normal length `Lz`, and raw plane average `p(z)` read from CHGCAR:

```text
plane_average_delta_n(z) = p(z) / V        # e/A^3 convention
lateral_integral_delta_lambda(z) = p(z) / Lz  # e/A
q_e(z) = integral Delta lambda(z') dz'     # e
```

With this convention, the discrete integral of `Delta lambda` equals the raw
CHGCAR electron-count residual `sum(raw) / N_grid`.

## Slab-Normal Profiles

Use the z profiles with the 3D and 2D figures:

- `plane_average_delta_n(z)` answers where average electron accumulation or
  depletion occurs along the slab normal.
- `lateral_integral_delta_lambda(z)` is the charge-displacement curve used for
  surface-normal polarization trends.
- `q_e_from_bottom(z)` and `q_e_from_top(z)` are cumulative displacement
  descriptors. Plateaus can compare interfaces only when the same origin,
  cell, formula, and dividing-plane convention are used.
- `half_abs_integral` reports redistribution magnitude, not net transfer.
- `dipole_summary.json` reports a Delta-rho-derived dipole descriptor. It is not
  a work-function value unless a separate `LOCPOT`/electrostatic-potential
  workflow is used.

## Required Controls

- Use the same lattice, FFT grid shape, origin, and axis ordering for every
  term in the formula.
- Use consistent functional, PAW/pseudopotential set, ENCUT, FFT grid policy,
  k-points, smearing, spin, charge, DFT+U, dispersion, solvation, and dipole
  correction settings.
- For adsorption references, keep the clean slab and adsorbate frozen in the
  combined adsorbed geometry unless the claim explicitly includes relaxation.
- For charged systems, label the result as non-neutral and avoid
  "redistribution only" language.
- Use the same isosurface threshold, color convention, and view cameras when
  comparing systems.
- Report the integral residual. For neutral adsorption redistribution, it
  should be small relative to the positive and negative lobe integrals.
- Inspect the z profile before interpreting 3D lobes; it catches vacuum, dipole,
  and threshold artifacts that isosurfaces can hide.

## Claim Ladder

Visual-only evidence supports:

- electron accumulation/depletion locations;
- interfacial polarization patterns;
- qualitative density buildup in an adsorbate-metal bond region.

Visual plus z-profile metrics supports:

- larger or smaller surface-normal charge displacement across a comparable
  site/dopant/alloy/HEA series;
- whether redistribution is concentrated adsorbate-side, interface-side, or
  slab-side;
- whether the residual is physically sensible for the selected formula.

Visual plus Bader/DDEC/Hirshfeld or comparable charge partitioning supports:

- method-dependent adsorbate or active-site charge trends;
- correlations with adsorption free energy or d-band descriptors when the
  series is controlled.

Visual plus geometry, vibration, PDOS/d-band, adsorption energies, or barriers
supports stronger activation or catalytic-trend language. Keep the claim tied
to the corroborating evidence actually present.

## Claims Not Allowed From Delta Density Alone

- Do not assign formal oxidation states.
- Do not report exact atom-to-atom electron transfer unless a named partitioning
  method is also used.
- Do not claim activity, selectivity, overpotential, or rate without energetic
  or kinetic evidence.
- Do not claim donation/back-donation decomposition from scalar delta density
  alone; require independent orbital-resolved, geometric, vibrational, or
  energetic support.
- Do not claim a work-function change from CHGCAR alone; use `LOCPOT` or an
  equivalent electrostatic-potential workflow.
- Do not compare lobe size across systems with different cells, grids,
  thresholds, formulas, spin states, or adsorbate geometries.

## Literature Basis for Claim Wording

Use these anchors when drafting method/caption language or checking whether a
claim stays within common surface-science charge-density-difference practice.

- Gossenberger et al., Beilstein J. Nanotechnol. 2014, define adsorbate-surface
  density difference as interacting adsorbate-surface density minus the
  non-interacting slab and adsorbate densities at the same positions, then use
  lateral charge-displacement profiles for dipole/work-function reasoning:
  https://www.beilstein-journals.org/bjnano/articles/5/15
- Ropo et al., Phys. Rev. B 2014, use laterally integrated charge-density
  difference curves for CO/Cu(111) and local-region integration near the CO
  axis: https://link.aps.org/doi/10.1103/PhysRevB.90.241401
- Yang et al., npj Comput. Mater. 2021, combine plane-averaged charge-density
  difference, top/side isosurfaces, Bader charge transfer, PDOS, and hydrogen
  adsorption free-energy trends:
  https://www.nature.com/articles/s41524-021-00684-5
- VASP CHGCAR documentation explains FFT-grid normalization and total versus
  magnetization-density blocks:
  https://www.vasp.at/wiki/index.php/CHGCAR

## Caption Template

```text
Charge-density difference computed as {formula}. Positive Delta rho indicates
electron accumulation and negative Delta rho indicates electron depletion
relative to the stated references. References used the same cell/grid and
{frozen-geometry protocol}. Isosurfaces use +/-{threshold} {units}; z profiles
report plane_average_delta_n in e/A^3, Delta lambda in e/A, and q_e in e.
The integral residual is {residual} e.
```

## Claim Template

```text
Using {formula}, {system} shows electron accumulation near {region_a} and
depletion near {region_b}. The z-profile shows {larger/smaller/localized}
surface-normal charge displacement relative to {comparison}. Under the shared
cell/grid/reference protocol, this supports {adsorption-induced polarization /
dopant-induced redistribution / modified-site charge response} at {site}.
```

## Minimal Decision Flow

1. Classify the comparison type.
2. Select and state the formula before reading plots.
3. Reject or downgrade the analysis if cell/grid/settings checks fail.
4. Compute the delta density and residual.
5. Inspect `z_profile.csv` and `dipole_summary.json`.
6. Interpret 3D isosurfaces and 2D slices with the same threshold and color
   convention across compared systems.
7. Use qualitative language for visual-only evidence.
8. Use trend language only when local integrals or a comparable site series are
   controlled.
9. Use activation or catalytic language only when independent descriptors agree.
