---
name: adsorbate-structure-grid
description: Build table-style grid figures of slab and adsorbate structures. Renders each structure with a pure-ASE + matplotlib engine (ball-and-stick spheres, bonds drawn only within the adsorbate and between adsorbate-slab, ase-gui-style X on FixAtoms-constrained atoms) in top/side-a/side-b views, crops to the structure, and lays the cells out with row labels, column labels, and horizontal table rules while omitting figure captions/panel labels. Use when Codex needs optimized-structure panels from CIF/POSCAR/traj/extxyz/xyz files, or just to render+crop clean structure PNGs for a manuscript.
---

# Adsorbate Structure Grid

## Scope

Use this skill to turn a set of relaxed slab/adsorbate structures into a single
manuscript-ready figure: a table of structure renders with surfaces down the
rows and adsorbate states across the columns. Render row and column labels from
`rows[*].label` and `cols[*].label`, plus horizontal table rules. Do not render
figure-level labels such as `Figure 1`, panel labels, captions, explanatory
sentences, or placeholders inside the generated figure. It also works as a
plain render+crop tool for one-off publication structure images.

It renders with the same pure-ASE + matplotlib engine (`render_core.py`) the
`calculation-result-analyzer` skill uses for visual review, so the look is
consistent with that skill. No aseview, no browser/playwright — just ase,
matplotlib, numpy, and Pillow. It does **not** run relaxations, judge
convergence, or pick frames — feed it structures you already trust (or use
`calculation-result-analyzer` first to validate them).

Run everything in the `modeling` env (needs `ase`, `matplotlib`, `Pillow`,
`numpy`); bare `python` is not enough.

## Workflow

1. Collect the structure files (one per grid cell). Any ASE-readable format works
   (`.cif`, `POSCAR/CONTCAR`, `.traj`, `.extxyz`, `.xyz`, …). Multi-frame files
   default to the last frame; set `index` per cell to pick another. To show
   fixed atoms (see below), use a format that preserves ASE constraints —
   `.traj`, `.extxyz`, or VASP `POSCAR`/`CONTCAR` with Selective Dynamics all
   round-trip `FixAtoms`; plain `.cif` does not.
2. Write a manifest JSON describing the grid shape — `rows`, `cols`, and
   `cells` mapping each `(row, col)` to a structure + view. Put only concise
   table headers in `rows[*].label` and `cols[*].label`; these are rendered.
   Keep `panel_label` and `caption` out of the figure. See
   `references/input-schema.md`. Relative paths resolve against the manifest's
   directory (or `base_dir`).
3. Render the figure:
   ```bash
   mamba run -n modeling python scripts/build_grid_figure.py \
       --input figure.json --output figure.pdf
   ```
4. **Look at the output.** Check each cell shows the intended structure and
   view and nothing is clipped. Adjust per-cell `view`, `repeat`, `index`, or
   `style`, then re-run (cached renders make iterating on layout fast; pass
   `--rerender` after changing a structure or its style).
5. Export `.pdf`/`.svg` for the manuscript; use `.png` for previews.
   Comma-separate `--output` to write several at once.

## Quick Start

Self-contained demo (builds its own fcc(111) slabs with a fixed bottom layer,
no user data needed):

```bash
mamba run -n modeling python scripts/build_grid_figure.py \
    --example --outdir demo_grid_out --output demo_grid_out/demo_grid.png
```

Render + crop standalone structure images (no grid), for ad-hoc figure work:

```bash
mamba run -n modeling python scripts/structure_render.py \
    --input slab.cif ohads.traj --views top side_a side_b --outdir renders
```

## Views and template

Three camera directions are derived from the cell basis so they stay consistent
across systems:

- `top` — true top-down, looking straight along the surface normal (best for
  site/coverage; add a `repeat` like `[2, 2, 1]` so the lattice reads).
- `side_a` / `side_b` — straight-on profiles looking exactly along the `a` /
  `b` cell vector, surface normal as screen-up (best for adsorbate height and
  layer structure). `side_a` is the default.

**Fixed atoms:** any atom under a `FixAtoms` constraint renders with a small
black X drawn on top of the sphere (ase-gui's own convention for a
constrained atom) in `side_a`/`side_b`, so the relaxed-vs-frozen split is
obvious. `top` leaves it off by default — from directly above, the frozen
bottom layer sits behind the relaxed top layer anyway, and the X mostly just
clutters a view whose job is site/coverage. Unlike a halo ring, the X stays
inside the atom's own footprint instead of expanding it. Set
`show_fixed_halo` explicitly in `style` (`true`/`false`) to override either
way, for any view.

**Atoms always render on top of bonds.** Bonds are trimmed surface-to-surface
(not center-to-center), and every atom draws after every bond regardless of
true depth, so a bond stick can never cut across the face of the atom it
connects to — depth order is still respected separately among atoms and
separately among bonds, so a foreground atom still correctly occludes a
background one. One consequence: a bond between two large, closely-spaced
atoms (e.g. a hollow-site adsorbate bond seen top-down) can end up as a very
short, easy-to-miss sliver — that's the true surface-to-surface gap at the
current `atom_scale`, not a rendering error; the side views usually show the
same bond at a less foreshortened length.

**Bonds are opt-in, not a fallback.** A bond is only ever drawn when the
adsorbate can be identified, and then only within the adsorbate and between
adsorbate-slab — slab-slab bonds are never drawn. With no adsorbate info at
all (a clean slab with nothing adsorbed, or a structure with no such
metadata), **no bonds are drawn at all** rather than guessing at the whole
slab lattice. Identification reads `atoms.info["adsorbate_atom_indices_json"]`
/ `"adsorbate_metadata_json"` (what slabuilder's `place_surface_adsorbates`
pipeline writes) or, failing that, `atoms.info["adsorbate_tag"]` + ASE tags.
**All of this is lost once a structure round-trips through VASP**
(POSCAR/CONTCAR/OUTCAR/vasprun.xml carry no such metadata — VASP has no
concept of "adsorbate"), so a bare VASP-derived file renders with no bonds at
all. Prefer the `.traj`/`.extxyz` that sits next to a VASP input when both
exist.

The render template is **fixed but overridable**: shaded spheres sized off a
Jmol/three.js-style reference radius table (`atom_scale`, default `0.72` — a
ball-and-stick look with bonds clearly visible, not close-packed/space-filling),
bonds (`bond_scale`, default `1.05`, a multiplier on ASE's natural cutoffs),
unit cell wireframe (`show_cell`), an X mark on fixed atoms (`show_fixed_halo`),
transparent background (so the crop is exact). Override the template globally
in `defaults.style` or per cell in `style` (see `references/input-schema.md`
for the full key list — `atom_scale`, `bond_scale`, `show_cell`,
`show_fixed_halo`, `margin_frac`, `dpi`). Pin a camera directly with
`viewDirection`/`viewUp` in `style`, which overrides the `view` choice. Keep
one template across a figure unless a cell genuinely needs a different look.

## Layout standards

- Render only concise row/column table headers and horizontal rules. Put
  captions, panel numbers, and explanatory wording in the manuscript or slide,
  not in the generated structure panel.
- Use `empty: true` for a missing combination; it leaves the cell blank.
- Cells take their aspect from the rendered content (common canvas = largest
  content box) so they hug the structures with little whitespace, without
  distortion. Each cell is also framed tight up front (analytical content
  bounds, not just a post-hoc crop), so a single small molecule next to a
  large tiled slab still renders at full resolution before padding.
- Tune spacing via the manifest `layout` block (`cell_size_in`, `wspace`,
  `hspace`, `dpi`, ...). Defaults are in `build_grid_figure.py::LAYOUT_DEFAULTS`.
- The structure renders are raster (matplotlib PNG) embedded at `dpi`; `.pdf`
  and `.svg` wrap those rendered images and add editable row/column table
  labels when SVG/PDF text export is supported.

## Caching

Each cell renders to `<outdir>/_grid_work/` with a signature sidecar of its
(structure mtime, view, repeat, index, style, size). Re-running reuses a cell
unless its inputs changed; pass `--rerender` to force all cells (needed after a
style/manifest edit that the mtime check can't see, e.g. tweaking `margin_frac`).

## Boundaries

- Renders are a visual aid, not a measurement — do not read bond lengths or
  heights off the figure.
- Do not use this to claim a structure is relaxed/converged; that is the
  `calculation-result-analyzer` skill's job.
- Do not overwrite the user's structure files; the skill only writes renders and
  the figure outputs.
