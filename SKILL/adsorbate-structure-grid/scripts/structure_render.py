#!/usr/bin/env python3
"""Render single slab/adsorbate structures to publication-style PNGs.

This module is the rendering half of the ``adsorbate-structure-grid`` skill. It
loads an ASE-readable structure, renders a fixed-but-overridable "paper" view
(shaded jmol spheres, bonds on, dashed halo around FixAtoms-constrained atoms)
for the ``top`` / ``side_a`` / ``side_b`` camera directions with the pure-ASE +
matplotlib engine in ``render_core.py``, and crops the result to the
structure's bounding box so the cell tiles cleanly in a grid.

Run inside the ``modeling`` env (needs ase, matplotlib, Pillow, numpy — no
aseview, no browser):

    mamba run -n modeling python structure_render.py \
        --input slab.cif ads.traj --views top side_a side_b --outdir renders

Fixed atoms only render as fixed if the input format preserves ASE
constraints: ``.traj``/``.extxyz`` and VASP ``POSCAR``/``CONTCAR`` (Selective
Dynamics) all round-trip ``FixAtoms``; plain ``.cif`` does not.

It is also imported by ``build_grid_figure.py``; keep the public helpers
(``DEFAULT_STYLE``, ``camera_views``, ``load_structure``, ``render_view``,
``crop_to_content``, ``pad_to_canvas``) stable.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

import render_core as rc

# Fixed-but-overridable paper template, tuned for a clean figure cell: shaded
# spheres sized off a Jmol-style reference radius table (ball-and-stick, not
# space-filling), thin bonds drawn only within the adsorbate and between
# adsorbate-slab (never slab-slab, when the adsorbate can be identified —
# see ``render_core.adsorbate_mask``), unit cell wireframe, an X mark on
# FixAtoms-constrained atoms, transparent background (so the crop is exact).
DEFAULT_STYLE: dict[str, Any] = {
    "atom_scale": 0.72,
    "bond_scale": 1.05,
    "show_cell": True,
    "show_fixed_halo": True,  # side_a/side_b default; "top" defaults to off, see render_view()
    "margin_frac": 0.05,
    "dpi": 220,
}

# Camera kwargs are passed positionally per-view, not part of the style dict.
_CAMERA_KEYS = ("viewDirection", "viewUp")

VIEW_NAMES = ("top", "side_a", "side_b")


def camera_views(atoms: Any) -> dict[str, tuple[list[float], list[float]]]:
    """Top / Side-a / Side-b perspective directions from the cell basis.

    Falls back to fixed Cartesian axes for non-periodic / degenerate cells.
    Matches the analyzer skill so the look is consistent across skills.
    """
    cell = atoms.cell.array if hasattr(atoms, "cell") else None
    if cell is not None and abs(np.linalg.det(cell)) > 1e-8:
        a = cell[0] / np.linalg.norm(cell[0])
        b = cell[1] / np.linalg.norm(cell[1])
        normal = np.cross(cell[0], cell[1])
        normal = normal / np.linalg.norm(normal)
    else:
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0])
        normal = np.array([0.0, 0.0, 1.0])
    return {
        # True top-down: look straight along the surface normal, so stacked
        # layers project exactly onto each other.
        "top": (normal.tolist(), b.tolist()),
        # Straight-on in-plane profiles (no tilt): look exactly along a or b,
        # with the surface normal as screen-up.
        "side_a": (a.tolist(), normal.tolist()),
        "side_b": (b.tolist(), normal.tolist()),
    }


def load_structure(path: str | Path, index: int = -1, repeat: tuple[int, int, int] | None = None) -> Any:
    """Read a structure file with ASE and optionally tile it.

    ``index`` selects a frame from a multi-frame file (default last). ``repeat``
    tiles the cell, useful for top-down views of small surface cells.
    """
    from ase.io import read

    atoms = read(str(path), index=index)
    if isinstance(atoms, list):  # some readers ignore int index
        atoms = atoms[index]
    if repeat and tuple(repeat) != (1, 1, 1):
        n_per_cell = len(atoms)
        raw = atoms.info.get("adsorbate_atom_indices_json")
        tiled = atoms * tuple(int(x) for x in repeat)
        if raw:
            # ``*`` lays repeated copies out as contiguous index blocks
            # (copy k occupies [k*n_per_cell, (k+1)*n_per_cell)), but only
            # copies the pre-tile indices verbatim into .info — restate them
            # per copy so the bond-suppression mask covers every repeated
            # adsorbate, not just the first cell.
            try:
                orig_indices = json.loads(raw) if isinstance(raw, str) else raw
                n_tiles = len(tiled) // n_per_cell
                tiled.info["adsorbate_atom_indices_json"] = json.dumps([
                    int(i) + k * n_per_cell for k in range(n_tiles) for i in orig_indices
                ])
            except Exception:
                pass
        atoms = tiled
    return atoms


def render_view(
    atoms: Any,
    view: str,
    out_png: str | Path,
    *,
    style: dict[str, Any] | None = None,
    width: int = 600,
    height: int = 600,
    background_color: str | None = None,
    transparent: bool = True,
) -> Path:
    """Render one camera view of ``atoms`` to ``out_png`` (transparent by default).

    ``view`` is one of ``top`` / ``side_a`` / ``side_b``, or ``"as_is"`` to use
    an isometric-ish default camera (plus any ``viewDirection``/``viewUp`` in
    ``style``).
    """
    import matplotlib.pyplot as plt

    merged = {**DEFAULT_STYLE, **(style or {})}
    cam_override = {k: merged.pop(k) for k in _CAMERA_KEYS if k in merged}

    if view != "as_is" and view not in VIEW_NAMES:
        raise ValueError(f"unknown view {view!r}; use one of {VIEW_NAMES} or 'as_is'")
    if "viewDirection" in cam_override and "viewUp" in cam_override:
        direction, up = cam_override["viewDirection"], cam_override["viewUp"]
    elif view == "as_is":
        direction, up = (1.0, 1.0, 1.0), (0.0, 0.0, 1.0)
    else:
        direction, up = camera_views(atoms)[view]

    # Fixed-atom marker policy: on by default, but "top" hides it unless the
    # caller explicitly asked for it — from directly above, the frozen bottom
    # layer sits behind the relaxed top layer anyway, and the marker mostly
    # just adds clutter to a view whose job is showing site/coverage.
    if view == "top" and "show_fixed_halo" not in (style or {}):
        merged["show_fixed_halo"] = False

    frame = rc.camera_frame(direction, up)
    atom_scale = float(merged.pop("atom_scale"))
    bond_scale = float(merged.pop("bond_scale"))
    show_cell = bool(merged.pop("show_cell"))
    show_fixed_halo = bool(merged.pop("show_fixed_halo"))
    margin_frac = float(merged.pop("margin_frac"))
    dpi = int(merged.pop("dpi"))

    bounds = rc.frame_bounds([atoms], frame, atom_scale=atom_scale, margin_frac=margin_frac)
    fig, ax = rc.figure_for_bounds(bounds, width, height, dpi=dpi)
    rc.draw_frame(
        ax, atoms, frame,
        atom_scale=atom_scale, bond_scale=bond_scale,
        show_cell=show_cell, show_fixed_halo=show_fixed_halo,
    )

    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs: dict[str, Any] = {"transparent": transparent}
    if background_color is not None:
        fig.patch.set_facecolor(background_color)
        ax.set_facecolor(background_color)
        save_kwargs = {"transparent": False, "facecolor": background_color}
    fig.savefig(str(out_png), **save_kwargs)
    plt.close(fig)
    return out_png


def crop_to_content(png_path: str | Path, *, pad_frac: float = 0.04, out_path: str | Path | None = None) -> Path:
    """Crop a rendered PNG to its non-empty bounding box plus a small margin.

    For a transparent render the box comes from the alpha channel; for an opaque
    render it comes from difference against the corner background color.
    """
    from PIL import Image

    png_path = Path(png_path)
    img = Image.open(png_path).convert("RGBA")
    bbox = img.getbbox()  # alpha-based for transparent renders
    if bbox is None:
        # Fully opaque/empty: fall back to diff against the top-left pixel color.
        from PIL import ImageChops

        bg = Image.new("RGBA", img.size, img.getpixel((0, 0)))
        bbox = ImageChops.difference(img, bg).getbbox()
    if bbox is None:
        cropped = img
    else:
        w, h = img.size
        pad = int(round(pad_frac * max(bbox[2] - bbox[0], bbox[3] - bbox[1])))
        left = max(0, bbox[0] - pad)
        top = max(0, bbox[1] - pad)
        right = min(w, bbox[2] + pad)
        bottom = min(h, bbox[3] + pad)
        cropped = img.crop((left, top, right, bottom))
    out_path = Path(out_path) if out_path is not None else png_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(out_path)
    return out_path


def pad_to_canvas(png_path: str | Path, width: int, height: int, *, out_path: str | Path | None = None) -> Path:
    """Center an image on a transparent canvas of the given size (no scaling).

    Used to give every grid cell identical pixel dimensions so the table aligns.
    """
    from PIL import Image

    png_path = Path(png_path)
    img = Image.open(png_path).convert("RGBA")
    canvas = Image.new("RGBA", (int(width), int(height)), (0, 0, 0, 0))
    x = (int(width) - img.width) // 2
    y = (int(height) - img.height) // 2
    canvas.alpha_composite(img, (max(0, x), max(0, y)))
    out_path = Path(out_path) if out_path is not None else png_path
    canvas.save(out_path)
    return out_path


def render_and_crop(
    structure: str | Path,
    view: str,
    out_png: str | Path,
    *,
    index: int = -1,
    repeat: tuple[int, int, int] | None = None,
    style: dict[str, Any] | None = None,
    width: int = 600,
    height: int = 600,
    pad_frac: float = 0.04,
) -> Path:
    """Convenience: load -> render one view -> crop, returning the cropped path."""
    atoms = load_structure(structure, index=index, repeat=repeat)
    render_view(
        atoms, view, out_png,
        style=style, width=width, height=height,
    )
    return crop_to_content(out_png, pad_frac=pad_frac)


def _main() -> int:
    ap = argparse.ArgumentParser(description="Render + crop slab/adsorbate structures (pure ASE + matplotlib).")
    ap.add_argument("--input", nargs="+", required=True, help="Structure file(s) (cif/POSCAR/traj/extxyz/xyz...).")
    ap.add_argument("--views", nargs="+", default=["side_a"], choices=[*VIEW_NAMES, "as_is"], help="Camera views to render.")
    ap.add_argument("--outdir", default="renders", help="Output directory for cropped PNGs.")
    ap.add_argument("--index", type=int, default=-1, help="Frame index for multi-frame files (default last).")
    ap.add_argument("--repeat", nargs=3, type=int, default=None, metavar=("NX", "NY", "NZ"), help="Tile the cell before rendering.")
    ap.add_argument("--width", type=int, default=600)
    ap.add_argument("--height", type=int, default=600)
    ap.add_argument("--pad-frac", type=float, default=0.04, help="Crop margin as a fraction of the content box.")
    ap.add_argument("--style-json", default=None, help="JSON file or inline JSON of style overrides (see DEFAULT_STYLE).")
    args = ap.parse_args()

    style = None
    if args.style_json:
        p = Path(args.style_json)
        style = json.loads(p.read_text()) if p.exists() else json.loads(args.style_json)

    outdir = Path(args.outdir)
    written: list[str] = []
    for inp in args.input:
        stem = Path(inp).stem
        for view in args.views:
            out_png = outdir / f"{stem}_{view}.png"
            render_and_crop(
                inp, view, out_png,
                index=args.index, repeat=tuple(args.repeat) if args.repeat else None,
                style=style, width=args.width, height=args.height,
                pad_frac=args.pad_frac,
            )
            written.append(str(out_png))
            print(f"rendered {inp} [{view}] -> {out_png}")
    print(json.dumps({"written": written}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
