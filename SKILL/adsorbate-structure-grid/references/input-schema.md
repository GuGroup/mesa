# Manifest schema — `adsorbate-structure-grid`

The manifest is a single JSON object describing one grid figure. Relative
structure/image paths resolve against the manifest file's directory unless
`base_dir` is set.

## Top-level fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `rows` | list of objects | yes | Row slots, top → bottom. Optional `label` is rendered as the row header and can also be used by `cells[*].row`. |
| `cols` | list of objects | yes | Column slots, left → right. Optional `label` is rendered as the column header and can also be used by `cells[*].col`. |
| `cells` | list of cell objects | yes | One per filled (row, col). Missing pairs leave blank cells. |
| `panel_label` | string | no | Ignored. Do not render figure labels such as `Figure 1` inside the grid. |
| `caption` | string | no | Ignored. Put captions outside the generated figure. |
| `base_dir` | string | no | Base directory for relative paths (default: manifest dir). |
| `defaults` | object | no | Per-cell defaults (see below) applied unless a cell overrides them. |
| `layout` | object | no | Figure layout overrides (see Layout). |

## Cell object

| Field | Type | Notes |
|---|---|---|
| `row` | int or string | Row index or `rows[*].label`. Required. |
| `col` | int or string | Col index or `cols[*].label`. Required. |
| `structure` | string | Path to an ASE-readable file. Required unless `image`/`empty`. |
| `image` | string | Use a pre-rendered PNG instead of rendering (it is still cropped). |
| `empty` | bool | `true` → leave the cell blank. |
| `view` | string | `top` \| `side_a` \| `side_b` \| `as_is`. Default `side_a`. |
| `index` | int | Frame to read from a multi-frame file. Default `-1` (last). |
| `repeat` | `[nx, ny, nz]` | Tile the cell before rendering (good for `top` views). |
| `style` | object | aseview style overrides for this cell (merged over `defaults.style`). |
| `width`, `height` | int | aseview render canvas in px (pre-crop). Default `600`. |
| `pad_frac` | float | Crop margin as a fraction of the content box. Default `0.04`. |

`defaults` accepts any of `view`, `index`, `repeat`, `style`, `width`, `height`,
`pad_frac` and applies them to every cell that does not set its own.

## aseview `style` keys (template — fixed but overridable)

Defaults live in `scripts/structure_render.py::DEFAULT_STYLE`:

```json
{
  "colorBy": "Atom",
  "showBond": true,
  "style": "rowan",
  "atomSize": 0.75,
  "viewMode": "Orthographic",
  "showCell": true,
  "showShadow": true,
  "viewFit": 0.62
}
```

Common overrides: `viewMode` (`"Orthographic"` default, or `"Perspective"`),
`style` (`"rowan"` default; also `"default"`, `"metallic"`, `"glossy"`,
`"cinematic"`), `showCell` (set `false` to hide the unit cell box),
`showConstraint`, `showShadow`, `viewFit` (zoom; smaller = more padding),
`atomSize`, `colorBy`, `backgroundColor`/`cellColor`. You can also pin a camera
with `viewDirection`/`viewUp` in `style`, which overrides the `view` choice.

**Side-view fixed-atoms policy:** for `side_a`/`side_b`, `showConstraint`
defaults to `true` (frozen `FixAtoms` layers shown as a faded halo) unless you
set it in `style`; `top` leaves it `false`.

## Layout block (figure styling)

Overrides `scripts/build_grid_figure.py::LAYOUT_DEFAULTS`:

| Key | Default | Meaning |
|---|---|---|
| `cell_size_in` | `1.5` | Long side of each cell (inches); the short side follows the rendered content aspect so cells hug the structures. |
| `cell_width_in` / `cell_height_in` | `null` | Pin both cell dimensions explicitly (overrides `cell_size_in` + auto aspect). |
| `wspace` / `hspace` | `0.02` / `0.06` | Gaps between columns / rows. |
| `background_color` | `white` | Figure background. |
| `dpi` | `220` | Raster DPI for embedded renders / PNG output. |
| `show_labels` | `true` | Render `rows[*].label` and `cols[*].label` as table headers. |
| `show_horizontal_rules` | `true` | Draw horizontal table rules around the header and between rows. |
| `row_label_width_in` | `0.78` | Width reserved for row headers. |
| `col_label_height_in` | `0.34` | Height reserved for column headers. |
| `label_fontsize` | `9` | Header label font size. |
| `rule_color` | `#272727` | Horizontal rule color. |
| `rule_width` / `header_rule_width` | `0.8` / `1.2` | Normal and header/outer rule line widths. |

## Minimal example

```json
{
  "defaults": { "view": "side_a" },
  "cols": [{"label": "*"}, {"label": "H*"}, {"label": "OH*"}],
  "rows": [{"label": "RuO2"}, {"label": "Ru"}],
  "cells": [
    { "row": 0, "col": 0, "structure": "ruo2/slab.cif" },
    { "row": 0, "col": 1, "structure": "ruo2/h.traj" },
    { "row": 0, "col": 2, "structure": "ruo2/oh.traj" },
    { "row": 1, "col": 0, "structure": "ru/slab.cif" },
    { "row": 1, "col": 1, "structure": "ru/h.traj" },
    { "row": 1, "col": 2, "empty": true }
  ]
}
```
