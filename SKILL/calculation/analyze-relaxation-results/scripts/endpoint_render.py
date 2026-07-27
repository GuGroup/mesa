"""Render initial and final relaxation endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

import render_core as rc
import render_style

OVERLAY_BACKGROUND = "#ffffff"
INITIAL_ENDPOINT_COLOR = (0.86, 0.15, 0.12)
FINAL_ENDPOINT_COLOR = (0.15, 0.34, 0.92)
INITIAL_ENDPOINT_HEX = "#dc2626"
FINAL_ENDPOINT_HEX = "#2563eb"


def _unwrap_endpoints(frames: list[Any]) -> list[Any]:
    from ase.geometry import find_mic

    if not frames:
        return []
    first = frames[0].copy()
    last = frames[-1].copy()
    if len(first) != len(last):
        return [first, last]
    delta = np.asarray(last.positions, dtype=float) - np.asarray(first.positions, dtype=float)
    cell = last.cell.array if hasattr(last, "cell") else None
    pbc = [bool(value) for value in getattr(last, "pbc", [False, False, False])]
    if cell is not None and any(pbc) and abs(np.linalg.det(cell)) > 1e-8:
        delta, _ = find_mic(delta, cell=cell, pbc=pbc)
    last.positions[:] = np.asarray(first.positions, dtype=float) + delta
    return [first, last]


def _camera_views(atoms: Any) -> dict[str, tuple[list[float], list[float]]]:
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
        "top": (normal.tolist(), b.tolist()),
        "side_a": (a.tolist(), normal.tolist()),
        "side_b": (b.tolist(), normal.tolist()),
    }


def _render_initial_final_view(
    endpoints: list[Any],
    frame: rc.Frame,
    out_path: Path,
    *,
    width: int,
    height: int,
    show_fixed_halo: bool,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    first, last = endpoints[0], endpoints[-1]
    bounds = rc.frame_bounds(endpoints, frame, atom_scale=0.72, margin_frac=0.06)
    fig, ax = rc.figure_for_bounds(bounds, width, height, dpi=200)
    fig.patch.set_facecolor(OVERLAY_BACKGROUND)
    ax.set_facecolor(OVERLAY_BACKGROUND)

    first_items = rc.frame_items(
        first,
        frame,
        alpha=0.68,
        show_cell=False,
        show_fixed_halo=show_fixed_halo,
        ads_mask=None,
    )
    last_items = rc.frame_items(
        last,
        frame,
        alpha=0.72,
        show_fixed_halo=show_fixed_halo,
        ads_mask=None,
    )
    items = render_style.recolor_atoms(first_items, INITIAL_ENDPOINT_COLOR)
    items += render_style.recolor_atoms(last_items, FINAL_ENDPOINT_COLOR)
    rc.draw_items(ax, items)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_path), transparent=False, facecolor=OVERLAY_BACKGROUND)
    plt.close(fig)


def render_initial_final_comparison(
    frames: list[Any],
    outdir: Path,
    prefix: str,
    *,
    width: int,
    height: int,
) -> dict[str, Any]:
    last_index = len(frames) - 1
    result: dict[str, Any] = {
        "indices": [0, last_index] if frames else [],
        "paths": {},
        "colors": {"initial": INITIAL_ENDPOINT_HEX, "final": FINAL_ENDPOINT_HEX},
        "error": None,
    }
    endpoints = _unwrap_endpoints(frames)
    if not endpoints:
        result["error"] = "no frames to render"
        return result
    try:
        views = _camera_views(endpoints[-1])
        for name, (direction, up) in views.items():
            cam = rc.camera_frame(direction, up)
            path = outdir / f"{prefix}_{name}.png"
            _render_initial_final_view(
                endpoints,
                cam,
                path,
                width=width,
                height=height,
                show_fixed_halo=(name != "top"),
            )
            result["paths"][name] = str(path)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result
