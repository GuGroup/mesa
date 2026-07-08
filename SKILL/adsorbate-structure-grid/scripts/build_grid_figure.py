#!/usr/bin/env python3
"""Compose a labelled grid figure of slab/adsorbate structures.

Reads a JSON manifest describing a table whose rows are surfaces (by Miller
index or material) and columns are adsorbate states. Each cell points at a
structure file; the script renders it with the pure-ASE + matplotlib engine in
``structure_render``/``render_core`` (no aseview, no browser), crops to
content, pads every cell to a uniform box, and lays the cells out in a
compact table-like grid with row/column labels and horizontal rules. Figure
labels and captions are intentionally not drawn.

Run inside the ``modeling`` env:

    mamba run -n modeling python build_grid_figure.py \
        --input figure.json --output figure.pdf

See ``references/input-schema.md`` for the manifest schema, and ``--example``
for a self-contained demo that builds its own structures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

import structure_render as sr


# ----------------------------------------------------------------------------
# Layout defaults (overridable via manifest "layout" / "style" blocks)
# ----------------------------------------------------------------------------
LAYOUT_DEFAULTS: dict[str, Any] = {
    # Cell size: the long side is `cell_size_in`; the short side is derived from
    # the rendered content aspect so cells hug the structures (little whitespace).
    # Set `cell_width_in`/`cell_height_in` to pin both explicitly instead.
    "cell_size_in": 1.5,
    "cell_width_in": None,
    "cell_height_in": None,
    "background_color": "white",
    "dpi": 220,
    "wspace": 0.02,
    "hspace": 0.06,
    "show_labels": True,
    "show_horizontal_rules": True,
    "row_label_width_in": 0.78,
    "col_label_height_in": 0.34,
    "label_fontsize": 9,
    "rule_color": "#272727",
    "rule_width": 0.8,
    "header_rule_width": 1.2,
}


def _resolve_index(value: Any, items: list[dict[str, Any]], kind: str) -> int:
    """Resolve a row/col reference that may be an int index or a label string."""
    if isinstance(value, int):
        if not 0 <= value < len(items):
            raise ValueError(f"{kind} index {value} out of range 0..{len(items) - 1}")
        return value
    labels = [it.get("label", "") for it in items]
    if value in labels:
        return labels.index(value)
    raise ValueError(f"{kind} {value!r} not found among labels {labels}")


def _render_signature(params: dict[str, Any], src_mtime: float | None) -> str:
    payload = json.dumps({"params": params, "mtime": src_mtime}, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode()).hexdigest()[:16]


def _cell_render(
    cell: dict[str, Any],
    defaults: dict[str, Any],
    base_dir: Path,
    cache_dir: Path,
    ri: int,
    ci: int,
    *,
    rerender: bool,
) -> Path | None:
    """Resolve one cell to a cropped PNG path (or None for an empty cell)."""
    if cell.get("empty"):
        return None
    # Pre-rendered image: just crop it.
    if cell.get("image"):
        img = (base_dir / cell["image"]).resolve()
        out = cache_dir / f"r{ri}_c{ci}_image.png"
        sr.crop_to_content(img, pad_frac=cell.get("pad_frac", defaults.get("pad_frac", 0.04)), out_path=out)
        return out

    structure = cell.get("structure")
    if not structure:
        return None
    src = (base_dir / structure).resolve()
    if not src.exists():
        raise FileNotFoundError(f"cell (row={ri}, col={ci}) structure not found: {src}")

    view = cell.get("view", defaults.get("view", "side_a"))
    index = int(cell.get("index", defaults.get("index", -1)))
    repeat = cell.get("repeat", defaults.get("repeat"))
    style = {**defaults.get("style", {}), **cell.get("style", {})}
    width = int(cell.get("width", defaults.get("width", 600)))
    height = int(cell.get("height", defaults.get("height", 600)))
    pad_frac = float(cell.get("pad_frac", defaults.get("pad_frac", 0.04)))

    params = {
        "structure": str(src), "view": view, "index": index, "repeat": repeat,
        "style": style, "width": width, "height": height, "pad_frac": pad_frac,
    }
    sig = _render_signature(params, src.stat().st_mtime)
    out = cache_dir / f"r{ri}_c{ci}_{view}.png"
    sig_file = cache_dir / f"r{ri}_c{ci}_{view}.sig"

    cached_ok = (
        not rerender
        and out.exists()
        and sig_file.exists()
        and sig_file.read_text().strip() == sig
    )
    if not cached_ok:
        atoms = sr.load_structure(src, index=index, repeat=tuple(repeat) if repeat else None)
        sr.render_view(atoms, view, out, style=style, width=width, height=height)
        sr.crop_to_content(out, pad_frac=pad_frac)
        sig_file.write_text(sig)
    return out


def _uniform_canvas(images: list[Path | None]) -> tuple[int, int]:
    """Common canvas = the largest content bounding box across all cells.

    Cells are padded to this, and the grid cell aspect is taken from it, so the
    table hugs the structures instead of letterboxing them into a fixed shape.
    """
    from PIL import Image

    max_w = max_h = 1
    for p in images:
        if p is None:
            continue
        with Image.open(p) as image:
            w, h = image.size
        max_w, max_h = max(max_w, w), max(max_h, h)
    return max_w, max_h


def compose_grid(
    manifest: dict[str, Any],
    rendered: list[list[Path | None]],
    layout: dict[str, Any],
    outputs: list[Path],
) -> list[Path]:
    """Lay the rendered cells out as a paper-style table figure and save it."""
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams.update({"svg.fonttype": "none", "pdf.fonttype": 42})
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from PIL import Image

    rows = manifest["rows"]
    cols = manifest["cols"]
    M, N = len(rows), len(cols)

    # Pad every cell to a common canvas = the largest content box, then take the
    # cell aspect from that canvas so cells hug the structures (minimal margins).
    flat = [img for row in rendered for img in row]
    canvas_w, canvas_h = _uniform_canvas(flat)
    content_aspect = canvas_w / canvas_h
    arrays: list[list[Any]] = []
    for row in rendered:
        out_row = []
        for img in row:
            if img is None:
                out_row.append(None)
                continue
            padded = sr.pad_to_canvas(img, canvas_w, canvas_h, out_path=img.with_suffix(".pad.png"))
            with Image.open(padded) as image:
                out_row.append(np.asarray(image.convert("RGBA")))
        arrays.append(out_row)

    # Cell size from content aspect (long side = cell_size_in), unless pinned.
    if layout.get("cell_width_in") and layout.get("cell_height_in"):
        cw, ch = layout["cell_width_in"], layout["cell_height_in"]
    else:
        base = layout["cell_size_in"]
        cw, ch = (base, base / content_aspect) if content_aspect >= 1 else (base * content_aspect, base)

    show_labels = bool(layout.get("show_labels", True))
    show_row_labels = show_labels and any(row.get("label") for row in rows)
    show_col_labels = show_labels and any(col.get("label") for col in cols)
    row_label_w = float(layout.get("row_label_width_in", 0.78)) if show_row_labels else 0.0
    col_label_h = float(layout.get("col_label_height_in", 0.34)) if show_col_labels else 0.0
    wgap = float(layout.get("wspace", 0.02)) * cw
    hgap = float(layout.get("hspace", 0.06)) * ch

    fig_w = row_label_w + N * cw + max(N - 1, 0) * wgap
    fig_h = col_label_h + M * ch + max(M - 1, 0) * hgap
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=layout["dpi"])
    fig.patch.set_facecolor(layout["background_color"])

    for i in range(M):
        for j in range(N):
            x = row_label_w + j * (cw + wgap)
            y = (M - 1 - i) * (ch + hgap)
            ax = fig.add_axes([x / fig_w, y / fig_h, cw / fig_w, ch / fig_h])
            ax.axis("off")
            arr = arrays[i][j]
            if arr is not None:
                ax.imshow(arr, aspect="auto", interpolation="lanczos")

    label_fs = float(layout.get("label_fontsize", 9))
    if show_col_labels:
        header_y = (M * ch + max(M - 1, 0) * hgap + 0.5 * col_label_h) / fig_h
        for j, col in enumerate(cols):
            fig.text(
                (row_label_w + j * (cw + wgap) + 0.5 * cw) / fig_w,
                header_y,
                str(col.get("label", "")),
                ha="center",
                va="center",
                fontsize=label_fs,
                fontweight="bold",
            )

    if show_row_labels:
        label_x = 0.5 * row_label_w / fig_w
        for i, row in enumerate(rows):
            fig.text(
                label_x,
                ((M - 1 - i) * (ch + hgap) + 0.5 * ch) / fig_h,
                str(row.get("label", "")),
                ha="center",
                va="center",
                fontsize=label_fs,
                fontweight="bold",
            )

    if layout.get("show_horizontal_rules", True):
        color = layout.get("rule_color", "#272727")
        rule_width = float(layout.get("rule_width", 0.8))
        header_rule_width = float(layout.get("header_rule_width", 1.2))
        data_top = M * ch + max(M - 1, 0) * hgap
        rule_ys = [0.0, data_top, fig_h]
        for k in range(1, M):
            rule_ys.append(k * ch + (k - 0.5) * hgap)
        for y in sorted(set(round(v / fig_h, 10) for v in rule_ys)):
            is_outer_or_header = y in {0.0, round(data_top / fig_h, 10), 1.0}
            fig.add_artist(
                Line2D(
                    [0, 1],
                    [y, y],
                    transform=fig.transFigure,
                    color=color,
                    lw=header_rule_width if is_outer_or_header else rule_width,
                    clip_on=False,
                )
            )

    saved = []
    for out in outputs:
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=layout["dpi"], facecolor=layout["background_color"])
        saved.append(out)
    plt.close(fig)
    return saved


def _build_example(workdir: Path) -> Path:
    """Write a small self-contained demo manifest + structures; return its path."""
    from ase.build import fcc111, add_adsorbate
    from ase.constraints import FixAtoms
    from ase.io import write

    struct_dir = workdir / "demo_structures"
    struct_dir.mkdir(parents=True, exist_ok=True)

    def slab(metal: str, ads: str | None, height: float = 1.7, site: str = "fcc"):
        s = fcc111(metal, size=(3, 3, 3), vacuum=8.0)
        z = s.positions[:, 2]
        bottom = z.min() + 0.5
        s.set_constraint(FixAtoms(indices=[i for i, v in enumerate(z) if v <= bottom]))
        if ads:
            n_before = len(s)
            add_adsorbate(s, ads, height=height, position=site)
            # Record which atoms are the adsorbate (plain ase.build tagging
            # does not mark this) so the renderer can suppress slab-slab bonds.
            s.info["adsorbate_atom_indices_json"] = json.dumps(list(range(n_before, len(s))))
        return s

    specs = {
        "pt_clean": slab("Pt", None),
        "pt_h": slab("Pt", "H", 0.6),
        "pt_o": slab("Pt", "O", 1.2),
        "cu_clean": slab("Cu", None),
        "cu_h": slab("Cu", "H", 0.6),
        "cu_o": slab("Cu", "O", 1.2),
    }
    # .traj (not .cif) so the FixAtoms constraints survive the round-trip and
    # the bottom-layer halo actually shows up in the render.
    for name, atoms in specs.items():
        write(str(struct_dir / f"{name}.traj"), atoms)

    manifest = {
        "defaults": {"view": "side_a"},
        "cols": [{"label": "*"}, {"label": "H*"}, {"label": "O*"}],
        "rows": [{"label": "Pt(111)"}, {"label": "Cu(111)"}],
        "cells": [
            {"row": 0, "col": 0, "structure": "demo_structures/pt_clean.traj"},
            {"row": 0, "col": 1, "structure": "demo_structures/pt_h.traj"},
            {"row": 0, "col": 2, "structure": "demo_structures/pt_o.traj"},
            {"row": 1, "col": 0, "structure": "demo_structures/cu_clean.traj"},
            {"row": 1, "col": 1, "structure": "demo_structures/cu_h.traj"},
            {"row": 1, "col": 2, "structure": "demo_structures/cu_o.traj"},
        ],
    }
    manifest_path = workdir / "demo_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Compose a paper-style grid of slab/adsorbate structures.")
    ap.add_argument("--input", help="Manifest JSON (see references/input-schema.md).")
    ap.add_argument("--output", default=None, help="Output figure path(s), comma-separated (.pdf/.svg/.png).")
    ap.add_argument("--outdir", default=None, help="Working dir for cached renders. Default: <output dir>/_grid_work.")
    ap.add_argument("--example", action="store_true", help="Build and render a self-contained demo grid.")
    ap.add_argument("--rerender", action="store_true", help="Ignore cached cell renders and redo them.")
    args = ap.parse_args()

    if not args.input and not args.example:
        ap.error("provide --input MANIFEST or --example")

    if args.example:
        work = Path(args.outdir or "demo_grid_out")
        work.mkdir(parents=True, exist_ok=True)
        manifest_path = _build_example(work)
        outputs = [Path(p) for p in (args.output or str(work / "demo_grid.png")).split(",")]
    else:
        manifest_path = Path(args.input)
        outputs = [Path(p) for p in (args.output or str(manifest_path.with_suffix(".png"))).split(",")]

    manifest = json.loads(Path(manifest_path).read_text())
    base_dir = Path(manifest.get("base_dir", manifest_path.parent)).resolve()
    cache_dir = Path(args.outdir) if args.outdir else outputs[0].parent / "_grid_work"
    cache_dir = cache_dir.resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)

    rows = manifest["rows"]
    cols = manifest["cols"]
    defaults = dict(manifest.get("defaults", {}))

    # Map cells onto a dense M x N grid.
    grid_cells: list[list[dict[str, Any] | None]] = [[None] * len(cols) for _ in rows]
    for cell in manifest.get("cells", []):
        ri = _resolve_index(cell.get("row"), rows, "row")
        ci = _resolve_index(cell.get("col"), cols, "col")
        grid_cells[ri][ci] = cell

    rendered: list[list[Path | None]] = []
    for ri in range(len(rows)):
        row_imgs: list[Path | None] = []
        for ci in range(len(cols)):
            cell = grid_cells[ri][ci] or {"empty": True}
            row_imgs.append(_cell_render(
                cell, defaults, base_dir, cache_dir, ri, ci,
                rerender=args.rerender,
            ))
        rendered.append(row_imgs)

    layout = {**LAYOUT_DEFAULTS, **manifest.get("layout", {})}
    saved = compose_grid(manifest, rendered, layout, outputs)
    print(json.dumps({"saved": [str(p) for p in saved], "cache_dir": str(cache_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
