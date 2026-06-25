#!/usr/bin/env python3
"""Render single slab/adsorbate structures to publication-style PNGs via aseview.

This module is the rendering half of the ``adsorbate-structure-grid`` skill. It
loads an ASE-readable structure, renders a fixed-but-overridable "paper" view
(Rowan style, bonds on, compact atoms) for the ``top`` / ``side_a`` / ``side_b``
camera directions through aseview's headless ``save_png``, and crops the result
to the structure's bounding box so the cell tiles cleanly in a grid.

Run inside the ``modeling`` env (needs ase, aseview[export] + a chromium for
playwright, Pillow, numpy):

    mamba run -n modeling python structure_render.py \
        --input slab.cif ads.traj --views top side_a side_b --outdir renders

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

# Fixed-but-overridable paper template, tuned for a clean figure cell:
# transparent background (set at save time) so the crop is exact, orthographic
# camera (parallel cell edges, no perspective foreshortening — the usual choice
# for structure panels), unit cell box drawn, "rowan" style + soft shadow for a
# bright, clean look with enough depth (other aseview styles: "default",
# "metallic", "glossy", "cinematic"). aseview accepts ``viewMode`` of
# "Orthographic" or "Perspective"; set ``showCell: false`` per cell to hide the
# box.
DEFAULT_STYLE: dict[str, Any] = {
    "colorBy": "Atom",
    "showBond": True,
    "style": "rowan",
    "atomSize": 0.75,
    "viewMode": "Orthographic",
    "showCell": True,
    "showShadow": True,
    "viewFit": 0.62,
}

# Side views additionally reveal the fixed (FixAtoms) bottom layers by default,
# so a relaxed-vs-frozen split is obvious. Top views look straight down and the
# frozen layers are hidden behind the surface, so the policy does not apply.
_SIDE_VIEWS = ("side_a", "side_b")

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
        # True top-down: look straight along the surface normal (no tilt), so
        # stacked layers project exactly onto each other.
        "top": (normal.tolist(), b.tolist()),
        # Slightly tilted in-plane perspectives for adsorbate height / layering.
        "side_a": ((a + 0.12 * b + 0.08 * normal).tolist(), normal.tolist()),
        "side_b": ((b - 0.12 * a + 0.08 * normal).tolist(), normal.tolist()),
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
        atoms = atoms * tuple(int(x) for x in repeat)
    return atoms


def render_view(
    atoms: Any,
    view: str,
    out_png: str | Path,
    *,
    style: dict[str, Any] | None = None,
    width: int = 600,
    height: int = 600,
    chrome_path: str | None = None,
    background_color: str | None = None,
    transparent: bool = True,
) -> Path:
    """Render one camera view of ``atoms`` to ``out_png`` (transparent by default).

    ``view`` is one of ``top`` / ``side_a`` / ``side_b``, or ``"as_is"`` to use
    aseview's default camera (plus any ``viewDirection``/``viewUp`` in ``style``).
    """
    from aseview import MolecularViewer

    merged = {**DEFAULT_STYLE, **(style or {})}
    # Side-view policy: reveal the fixed bottom layers unless the caller set
    # showConstraint explicitly.
    if view in _SIDE_VIEWS and "showConstraint" not in (style or {}):
        merged["showConstraint"] = True
    # Pull explicit camera overrides out of style so the view choice wins unless
    # the caller deliberately set a camera.
    cam_override = {k: merged.pop(k) for k in _CAMERA_KEYS if k in merged}

    kwargs: dict[str, Any] = dict(merged)
    if view != "as_is":
        if view not in VIEW_NAMES:
            raise ValueError(f"unknown view {view!r}; use one of {VIEW_NAMES} or 'as_is'")
        direction, up = camera_views(atoms)[view]
        kwargs["viewDirection"] = direction
        kwargs["viewUp"] = up
    kwargs.update(cam_override)  # explicit camera in style overrides the view

    viewer = MolecularViewer(atoms, **kwargs)
    save_kwargs: dict[str, Any] = {"width": width, "height": height, "transparent": transparent}
    if background_color is not None:
        save_kwargs["background_color"] = background_color
        save_kwargs["transparent"] = False
    if chrome_path:
        save_kwargs["browser_executable_path"] = chrome_path
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    viewer.save_png(str(out_png), **save_kwargs)
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
    chrome_path: str | None = None,
) -> Path:
    """Convenience: load -> render one view -> crop, returning the cropped path."""
    atoms = load_structure(structure, index=index, repeat=repeat)
    render_view(
        atoms, view, out_png,
        style=style, width=width, height=height, chrome_path=chrome_path,
    )
    return crop_to_content(out_png, pad_frac=pad_frac)


def _main() -> int:
    ap = argparse.ArgumentParser(description="Render + crop slab/adsorbate structures via aseview.")
    ap.add_argument("--input", nargs="+", required=True, help="Structure file(s) (cif/POSCAR/traj/extxyz/xyz...).")
    ap.add_argument("--views", nargs="+", default=["side_a"], choices=[*VIEW_NAMES, "as_is"], help="Camera views to render.")
    ap.add_argument("--outdir", default="renders", help="Output directory for cropped PNGs.")
    ap.add_argument("--index", type=int, default=-1, help="Frame index for multi-frame files (default last).")
    ap.add_argument("--repeat", nargs=3, type=int, default=None, metavar=("NX", "NY", "NZ"), help="Tile the cell before rendering.")
    ap.add_argument("--width", type=int, default=600)
    ap.add_argument("--height", type=int, default=600)
    ap.add_argument("--pad-frac", type=float, default=0.04, help="Crop margin as a fraction of the content box.")
    ap.add_argument("--style-json", default=None, help="JSON file or inline JSON of aseview style overrides.")
    ap.add_argument("--chrome-path", default=None, help="Browser executable for aseview PNG export. Default: playwright chromium.")
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
                pad_frac=args.pad_frac, chrome_path=args.chrome_path,
            )
            written.append(str(out_png))
            print(f"rendered {inp} [{view}] -> {out_png}")
    print(json.dumps({"written": written}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
