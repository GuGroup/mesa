---
name: adsorbate-structure-grid
description: Build table-style grid figures of slab and adsorbate structures. Renders each structure with aseview (Rowan style, bonds on, compact atoms) in top/side-a/side-b views, crops to the structure, and lays the cells out with row labels, column labels, and horizontal table rules while omitting figure captions/panel labels. Use when Codex needs optimized-structure panels from CIF/POSCAR/traj/extxyz/xyz files, or just to render+crop clean structure PNGs for a manuscript.
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

It renders with **aseview** (the same headless `save_png` path the
`calculation-result-analyzer` skill uses for visual review), so the look is
consistent with that skill. It does **not** run relaxations, judge convergence,
or pick frames — feed it structures you already trust (or use
`calculation-result-analyzer` first to validate them).

Run everything in the `modeling` env (needs `ase`, `aseview[export]` + a chromium
for playwright, `Pillow`, `matplotlib`, `numpy`); bare `python` is not enough.

## Workflow

1. Collect the structure files (one per grid cell). Any ASE-readable format works
   (`.cif`, `POSCAR/CONTCAR`, `.traj`, `.extxyz`, `.xyz`, …). Multi-frame files
   default to the last frame; set `index` per cell to pick another.
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

Self-contained demo (builds its own fcc(111) slabs, no user data needed):

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
- `side_a` / `side_b` — two slightly tilted near-in-plane views (best for
  adsorbate height, tilt, and layer structure). `side_a` is the default.

**Side-view fixed-atoms policy:** `side_a`/`side_b` render with
`showConstraint: true` by default, so the frozen (`FixAtoms`) bottom layers show
as a faded translucent halo and the relaxed-vs-frozen split is obvious. `top`
keeps it off (the frozen layers sit behind the surface). Set `showConstraint`
explicitly in a cell's/defaults' `style` to override either way.

The render template is **fixed but overridable**: Rowan style, bonds on, atom
size 0.75, orthographic camera, unit cell box drawn, soft shadow, transparent
background (so the crop is exact). `viewMode` accepts `"Orthographic"` (default —
parallel cell edges, no perspective foreshortening, the usual choice for
structure panels) or `"Perspective"`. Other `style` values aseview supports:
`"default"`, `"metallic"`, `"glossy"`, `"cinematic"` (darker, strong shading).
Override the template globally in `defaults.style` or per cell in `style` using
aseview keys (`viewMode`, `showCell` → set `false` to hide the box,
`showConstraint`, `showShadow`, `atomSize`, `viewFit`, `colorBy`, `showBond`,
`style`, `backgroundColor`, …). Keep one template across a figure unless a cell
genuinely needs a different look.

## Layout standards

- Render only concise row/column table headers and horizontal rules. Put
  captions, panel numbers, and explanatory wording in the manuscript or slide,
  not in the generated structure panel.
- Use `empty: true` for a missing combination; it leaves the cell blank.
- Cells take their aspect from the rendered content (common canvas = largest
  content box) so they hug the structures with little whitespace, without
  distortion.
- Tune spacing via the manifest `layout` block (`cell_size_in`, `wspace`,
  `hspace`, `dpi`, ...). Defaults are in `build_grid_figure.py::LAYOUT_DEFAULTS`.
- The structure renders are raster (aseview PNG) embedded at `dpi`; `.pdf` and
  `.svg` wrap those rendered images and add editable row/column table labels
  when SVG/PDF text export is supported.

## Caching

Each cell renders to `<outdir>/_grid_work/` with a signature sidecar of its
(structure mtime, view, repeat, index, style, size). Re-running reuses a cell
unless its inputs changed; pass `--rerender` to force all cells (needed after a
style/manifest edit that the mtime check can't see, e.g. tweaking `viewFit`).

## Boundaries

- Renders are a visual aid, not a measurement — do not read bond lengths or
  heights off the figure.
- Do not use this to claim a structure is relaxed/converged; that is the
  `calculation-result-analyzer` skill's job.
- Do not overwrite the user's structure files; the skill only writes renders and
  the figure outputs.
- If aseview/playwright cannot launch a browser, `--chrome-path` can point at a
  chromium/chrome executable.
