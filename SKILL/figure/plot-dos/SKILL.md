---
name: plot-dos
description: >-
  Plot publication-quality DOS/PDOS diagrams from VASP vasprun.xml.  Supports
  total DOS, element-resolved PDOS, orbital-resolved PDOS, spin-polarised
  mirroring, subplot mode, and raw data CSV export.  Renders in the sumo
  visual style without requiring sumo as a dependency.  Use when Codex needs
  to visualise density of states for catalyst surfaces or any periodic system.
---

For MESA end-to-end use, read `SKILL/figure/workflow.md` before applying this skill.

# DOS / PDOS Plotter

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

> **Tip**: Run this as a follow-up calculation using the converged CONTCAR from your geometry optimization as the POSCAR.

If `LORBIT` is not set, the `vasprun.xml` will not contain projected DOS data, and element/orbital decomposition will fail.

## Workflow

Run the plotting script from this skill directory using the shared `modeling`
mamba environment:

```bash
mamba run -n modeling python scripts/plot_dos.py ...
```

1. Ensure the user has a `vasprun.xml` from a single-point calculation with `LORBIT = 11`.
2. Check for VASP convergence warnings when parsing. If electronic convergence
   failed, produce plots only as diagnostics and clearly mark the result as not
   interpretation-grade.
3. Normalize any user plotting preferences into a JSON spec or CLI flags (see `references/input-schema.md`).
4. Run `mamba run -n modeling python scripts/plot_dos.py` to produce the publication-quality DOS/PDOS figure.
5. If `--export-data` is requested, the raw data will also be saved as CSV.
6. Report the output path and note any missing projections.

## Quick Start

```bash
# Basic total + element PDOS
mamba run -n modeling python scripts/plot_dos.py --vasprun vasprun.xml --output dos.svg

# Specific element/orbital filter
mamba run -n modeling python scripts/plot_dos.py --vasprun vasprun.xml --elements Pt.d Ni.d --output pdos.svg

# Subplot mode (one panel per element)
mamba run -n modeling python scripts/plot_dos.py --vasprun vasprun.xml --subplot --output pdos_sub.svg

# Export raw data
mamba run -n modeling python scripts/plot_dos.py --vasprun vasprun.xml --export-data --output dos.svg

# Style demo (no vasprun needed)
mamba run -n modeling python scripts/plot_dos.py --example --output dos_demo.svg
```

## Runtime Environment

Use the `modeling` mamba environment. It already provides `pymatgen`,
`matplotlib`, and `numpy`.

## Plotting Standards

- Use the sumo visual style: `fill_between` with alpha + solid line overlay for each DOS component.
- Total DOS uses lower alpha (0.15) as background; partial DOS uses alpha 0.25.
- Spin-polarised calculations: spin-down densities are mirrored below zero.
- Fermi level is always at 0 eV, marked with a dashed vertical line.
- Legend automatically hides orbital contributions below 3% of the peak DOS.
- Minor ticks on both axes via `AutoMinorLocator(2)`.
- y-axis tick labels are hidden by default (DOS units are arbitrary).
- SVG/PDF text is editable (`svg.fonttype: none`, `pdf.fonttype: 42`).

## Customization

Read `references/input-schema.md` for JSON input specification and CLI flag details.
