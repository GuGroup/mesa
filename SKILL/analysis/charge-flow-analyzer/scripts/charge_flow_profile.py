from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
from numpy.typing import NDArray
from pymatgen.io.vasp.outputs import Chgcar

from charge_flow_metrics import build_z_profile
from charge_flow_rendering import Camera, RenderScene, isosurface_meshes, lobe_threshold, project, render_points, render_view, slab_views

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


def write_side_profile_plot(path: Path, delta_chgcar: Chgcar, _title: str) -> None:
    delta = np.asarray(delta_chgcar.data["total"], dtype=np.float64)
    z_profile = build_z_profile(delta_chgcar)
    threshold = lobe_threshold(delta)
    scene = RenderScene(
        structure=delta_chgcar.structure,
        meshes=isosurface_meshes(delta, delta_chgcar.structure, threshold),
    )
    side_a = slab_views(delta_chgcar.structure)[1]
    y_limits = active_y_limits(scene, side_a.camera, z_profile.z_ang, z_profile.delta_n_avg_e_per_ang3)
    side_width = side_panel_width(scene, side_a.camera, y_limits)
    profile_width = 0.32
    height_inches = 3.05

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(height_inches * (side_width + profile_width), height_inches),
        gridspec_kw={"width_ratios": [side_width, profile_width], "wspace": 0.0},
    )
    render_view(axes[0], scene, side_a)
    for text in list(axes[0].texts):
        text.remove()
    x_limits = active_x_limits(scene, side_a.camera)
    remove_full_cell_lines(axes[0])
    axes[0].set_xlim(*x_limits)
    axes[0].set_ylim(*y_limits)
    axes[0].set_anchor("E")
    draw_cropped_cell_frame(axes[0], x_limits, y_limits)
    draw_vertical_profile(axes[1], z_profile.delta_n_avg_e_per_ang3, z_profile.z_ang, y_limits)
    fig.subplots_adjust(left=0.0, right=1.0, top=1.0, bottom=0.0, wspace=0.0)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=260, transparent=True, bbox_inches="tight", pad_inches=0.0)
    plt.close(fig)


def draw_vertical_profile(ax, plane_average: NDArray[np.float64], z_grid: NDArray[np.float64], y_limits: tuple[float, float]) -> None:
    max_abs = max(float(np.max(np.abs(plane_average))), 1e-12)
    x_limits = (-1.02 * max_abs, 1.02 * max_abs)
    ax.axvline(0.0, color="0.35", linewidth=0.65)
    ax.fill_betweenx(z_grid, 0.0, plane_average, where=plane_average >= 0, color="#D55E00", alpha=0.34)
    ax.fill_betweenx(z_grid, 0.0, plane_average, where=plane_average < 0, color="#0072B2", alpha=0.34)
    ax.plot(plane_average, z_grid, color="0.12", linewidth=1.0)
    ax.set_xlim(*x_limits)
    ax.set_ylim(*y_limits)
    ax.set_anchor("W")
    ax.set_xticks([-max_abs, 0.0, max_abs])
    ax.set_xticklabels(["-", "0", "+"])
    ax.set_yticks([])
    ax.set_xlabel(r"$\Delta\rho(z)$", fontsize=7, fontweight="bold", labelpad=-1)
    ax.tick_params(axis="x", labelsize=5.5, length=2, pad=0)
    ax.grid(axis="x", color="0.88", linewidth=0.45)
    ax.spines["left"].set_visible(True)
    ax.spines["left"].set_linewidth(0.55)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_linewidth(0.55)
    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)


def remove_full_cell_lines(ax) -> None:
    for line in list(ax.lines):
        if float(line.get_zorder()) == 1.0:
            line.remove()


def draw_cropped_cell_frame(ax, x_limits: tuple[float, float], y_limits: tuple[float, float]) -> None:
    x_low, x_high = inset_limits(x_limits)
    y_low, y_high = inset_limits(y_limits)
    ax.plot([x_low, x_high, x_high, x_low, x_low], [y_low, y_low, y_high, y_high, y_low], color="0.58", linewidth=0.55, zorder=1)


def inset_limits(limits: tuple[float, float]) -> tuple[float, float]:
    low, high = limits
    inset = max((high - low) * 0.003, 0.015)
    return low + inset, high - inset


def active_y_limits(scene: RenderScene, camera: Camera, z_grid: NDArray[np.float64], plane_average: NDArray[np.float64]) -> tuple[float, float]:
    points = [np.asarray(scene.structure.cart_coords, dtype=np.float64)]
    points.extend(mesh.vertices for mesh in scene.meshes)
    y_values = [project(np.vstack(points), camera)[:, 1]]
    max_abs = float(np.max(np.abs(plane_average)))
    if max_abs > 0.0:
        y_values.append(z_grid[np.abs(plane_average) > 0.01 * max_abs])
    active = np.concatenate(y_values)
    low = float(active.min())
    high = float(active.max())
    pad = max((high - low) * 0.025, 0.24)
    return low - pad, high + pad


def active_x_limits(scene: RenderScene, camera: Camera) -> tuple[float, float]:
    x_values = project(render_points(scene), camera)[:, 0]
    low = float(x_values.min())
    high = float(x_values.max())
    pad = max((high - low) * 0.006, 0.02)
    return low - pad, high + pad


def side_panel_width(scene: RenderScene, camera: Camera, y_limits: tuple[float, float]) -> float:
    x_limits = active_x_limits(scene, camera)
    x_span = max(float(x_limits[1] - x_limits[0]), 1e-6)
    y_span = max(float(y_limits[1] - y_limits[0]), 1e-6)
    return x_span / y_span
