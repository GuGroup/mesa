---
name: analyze-dband-center
description: >-
  Compute d-band center (ε_d), width (W_d), and filling (f_d) from VASP
  vasprun.xml for transition-metal catalyst surfaces.  Supports single-system
  analysis and multi-system comparison with d-DOS visualisation.  Use when
  Codex needs to quantify d-band electronic structure, compare d-band centers
  across catalyst systems, or interpret results using Hammer–Nørskov d-band
  theory.  Use adsorbate-free clean slabs by default; adsorbate-covered PDOS is
  a separate, explicitly requested post-adsorption analysis.  Renders d-DOS
  plots in the sumo visual style.
---

For MESA end-to-end use, read `SKILL/analysis/workflow.md` before applying this skill.

# D-Band Center Analyzer

## Structure-State Contract

For the conventional Hammer–Nørskov descriptor, the input MUST be the
**adsorbate-free clean (bare) slab before adsorbate interaction**. The default
comparison is therefore clean candidate slab versus clean reference slab.

- Relax the clean slab first, then run the static DOS calculation on that clean
  relaxed geometry. Do not reuse a CONTCAR from an adsorbate relaxation.
- Keep adsorbate coverage at zero for every system in a conventional d-band
  comparison. The phrase "same adsorbate" refers to the adsorption-energy trend
  being explained; it does not mean that the adsorbate belongs in the DOS input
  structures.
- Before analysis, inspect the structure associated with every `vasprun.xml`.
  The analyzer cannot determine from a path or label whether a slab is clean.
- Use an adsorbate-covered slab only when the user explicitly requests an
  adsorbate-induced or post-adsorption electronic-structure analysis. In that
  case, pair it with the corresponding clean slab, keep adsorbate identity,
  site, and coverage matched across systems, label it `adsorbate-covered`, and
  do not present its ε_d as the conventional clean-surface descriptor.
- The current CLI reports **element-resolved** values aggregated over all atoms
  of the selected element. Do not call them surface-atom-resolved or
  site-resolved values. A true site-resolved claim requires a separate
  site-projected calculation or analysis.

## Prerequisites — VASP Single-Point Calculation

This skill requires a **converged single-point (static) VASP calculation** with projected DOS output.  Ensure the following INCAR settings before running VASP:

```
# Required
LORBIT  = 11          # Write projected DOS (element + orbital resolved)
ISMEAR  = -5          # Tetrahedron method with Blöchl corrections (for DOS)
NEDOS   = 3001        # Number of DOS grid points (higher = smoother)
IBRION  = -1          # No ionic relaxation (static)
NSW     = 0           # Zero ionic steps (single point)
NELM    = 300         # Allow enough electronic SCF cycles for DOS/static runs
EDIFF   = 1E-5        # Tight electronic convergence for DOS descriptors

# Recommended
LWAVE   = .FALSE.     # Skip WAVECAR (saves disk)
LCHARG  = .FALSE.     # Skip CHGCAR (saves disk)
SIGMA   = 0.05        # Small smearing for accurate DOS (if using ISMEAR=0)
EMIN    = -15         # Energy range for DOS (optional, VASP auto-detects)
EMAX    = 15
```

> **Tip**: Run this as a follow-up calculation using the converged CONTCAR from
> the **clean-slab geometry optimization** as the POSCAR. A CONTCAR containing
> an adsorbate is not a valid default input for the conventional descriptor.

If `LORBIT` is not set, the `vasprun.xml` will not contain projected DOS data, and element/orbital decomposition will fail.

## Workflow

Run the analysis script from this skill directory using the shared `modeling`
mamba environment:

```bash
mamba run -n modeling python scripts/analyze_dband.py ...
```

1. Inspect the structure associated with each `vasprun.xml` and verify that it
   is an adsorbate-free clean slab. If it is adsorbate-covered, do not use it as
   the default descriptor input.
2. Ensure the clean-slab `vasprun.xml` comes from a single-point calculation
   with `LORBIT = 11`.
3. Check for VASP convergence warnings when parsing. Do not interpret
   unconverged electronic runs as reliable d-band evidence; request/recommend a
   rerun with at least `NELM = 300` and tighter convergence.
4. Run `mamba run -n modeling python scripts/analyze_dband.py single` for a single system or `compare` for multi-system comparison.
5. Report the element-resolved d-band center (ε_d), width (W_d), and filling
   (f_d) values without claiming site resolution.
6. Interpret the results using the Hammer–Nørskov d-band theory framework described in `references/dband-theory.md`.

## Quick Start

```bash
# Single system
mamba run -n modeling python scripts/analyze_dband.py single --vasprun clean_slab/vasprun.xml --elements Pt --output dband.svg --json dband.json

# Compare multiple systems (overlay; 2-3 systems)
mamba run -n modeling python scripts/analyze_dband.py compare \
    --vaspruns clean_sys_a/vasprun.xml clean_sys_b/vasprun.xml \
    --labels "Pt(111)" "PtNi(111)" \
    --element Pt \
    --output dband_compare.svg

# Compare d-band centres across several systems (vertical columns; publication style)
mamba run -n modeling python scripts/analyze_dband.py columns \
    --vaspruns clean_a/vasprun.xml clean_b/vasprun.xml clean_c/vasprun.xml \
    --labels "Ni(111)" "Ni+Co-dopant" "Co(111)" \
    --elements Ni Co Co \
    --output dband_columns.svg

# Style demo (no vasprun needed)
mamba run -n modeling python scripts/analyze_dband.py example --output dband_example.svg
```

Choosing a layout: use `single` for one system, `compare` (overlay) for 2-3
systems where the curve shapes overlap, and `columns` (one vertical panel per
system with a dashed ε_d line) for comparing d-band centres across several
systems. See `references/plot-styles.md` for the full guide.

## Runtime Environment

Use the `modeling` mamba environment. It already provides `pymatgen`,
`matplotlib`, and `numpy`.

## Plotting Standards

- Use the sumo visual style: `fill_between` with alpha + solid line overlay for each d-DOS component.
- Filled region below Fermi level uses subtle background shading (alpha 0.10).
- d-DOS curve uses alpha 0.22 fill with 1.5 lw solid overlay.
- d-band center marked with a subtle vertical line + triangle marker.
- Fermi level is always at 0 eV, marked with a dashed vertical line.
- Multi-system comparison overlays d-DOS curves with distinct colors (`compare`),
  or draws one vertical panel per system with a dashed ε_d line (`columns`).
- Minor ticks on both axes via `AutoMinorLocator(2)`.
- SVG/PDF text is editable (`svg.fonttype: none`, `pdf.fonttype: 42`).

Comparability conventions (apply consistently across a figure set):

- Use clean slabs with zero adsorbate coverage for the conventional descriptor.
- d-DOS is normalized **per atom** (`states eV⁻¹ atom⁻¹`) so a single dopant and a
  full slab are comparable; this does not change ε_d/width/filling.
- Default energy window is trimmed to the d-band (`--emin -8 --emax 2`).
- Lock the DOS scale with `--ymax` (single/compare) or `--xmax` (columns).
- A small plot-only Gaussian broadening (`--smear 0.05` eV) is applied for
  legibility; moments are always computed from the raw DOS.
- Displayed d-band values (ε_d, width, filling) are shown to **2 decimal places**
  in plots and the console table (the raw JSON keeps full precision).

## Customization

Read `references/plot-styles.md` to choose a layout (single / compare / columns)
and for the shared per-atom, window, scale and smearing conventions.
Read `references/input-schema.md` for CLI flag details and JSON output format.
Read `references/dband-theory.md` when interpreting d-band analysis results for catalysis discussions.
