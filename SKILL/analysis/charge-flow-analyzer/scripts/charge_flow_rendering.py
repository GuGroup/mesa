from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib
import numpy as np
from ase.data import atomic_numbers, covalent_radii
from ase.data.colors import jmol_colors
from matplotlib.collections import PolyCollection
from matplotlib.colors import to_rgba
from matplotlib.patches import Circle, Ellipse
from numpy.typing import NDArray
from pymatgen.core import Structure
from pymatgen.io.vasp.outputs import Chgcar
from skimage.measure import marching_cubes

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

# --- Rendering tunables -------------------------------------------------------
# Atom marker size (Angstrom): drawn radius = clip(SCALE * covalent_radius, MIN, MAX).
# Covalent radii are ~0.3 (H) .. ~1.5 (TM); SCALE ~0.5-0.6 gives balanced ball-and-stick.
ATOM_RADIUS_SCALE = 0.30
ATOM_RADIUS_MIN = 0.19
ATOM_RADIUS_MAX = 0.42
# Isosurface level for the +/- delta-density lobes. The level is the larger of a
# high percentile of |delta| and a fraction of its peak; lower values -> fuller lobes.
ISO_PERCENTILE = 96.5
ISO_MAX_FRACTION = 0.10


@dataclass(frozen=True, slots=True)
class Mesh:
    vertices: NDArray[np.float64]
    faces: NDArray[np.int64]
    color: str


@dataclass(frozen=True, slots=True)
class Camera:
    right: NDArray[np.float64]
    up: NDArray[np.float64]
    forward: NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class View:
    name: str
    camera: Camera


@dataclass(frozen=True, slots=True)
class RenderScene:
    structure: Structure
    meshes: list[Mesh]


@dataclass(frozen=True, slots=True)
class MeshRequest:
    volume: NDArray[np.float64]
    threshold: float
    structure: Structure
    color: str


def write_slice_plots(path: Path, delta_chgcar: Chgcar, title: str) -> None:
    delta = np.asarray(delta_chgcar.data["total"], dtype=np.float64)
    ix, iy, iz = peak_index(delta)
    x_grid = np.asarray(delta_chgcar.get_axis_grid(0), dtype=float)
    y_grid = np.asarray(delta_chgcar.get_axis_grid(1), dtype=float)
    z_grid = np.asarray(delta_chgcar.get_axis_grid(2), dtype=float)
    vmax = max(float(np.max(np.abs(delta))), 1e-12)

    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.2), constrained_layout=True)
    panels = [
        (axes[0], x_grid, y_grid, delta[:, :, iz].T, f"xy at z index {iz}", "x (Angstrom)", "y (Angstrom)"),
        (axes[1], x_grid, z_grid, delta[:, iy, :].T, f"xz at y index {iy}", "x (Angstrom)", "z (Angstrom)"),
        (axes[2], y_grid, z_grid, delta[ix, :, :].T, f"yz at x index {ix}", "y (Angstrom)", "z (Angstrom)"),
    ]
    contour = None
    for ax, grid_a, grid_b, values, panel_title, x_label, y_label in panels:
        contour = ax.contourf(grid_a, grid_b, values, levels=25, cmap="RdBu_r", vmin=-vmax, vmax=vmax)
        ax.contour(grid_a, grid_b, values, levels=[0.0], colors="0.25", linewidths=0.5)
        ax.set_title(panel_title, fontsize=9)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
    if contour is not None:
        fig.colorbar(contour, ax=axes, shrink=0.82, label=r"$\Delta\rho$")
    fig.suptitle(title)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=220)
    plt.close(fig)


def write_lobe_isosurface(path: Path, delta_chgcar: Chgcar, _title: str) -> None:
    delta = np.asarray(delta_chgcar.data["total"], dtype=np.float64)
    threshold = lobe_threshold(delta)
    meshes = isosurface_meshes(delta, delta_chgcar.structure, threshold)

    scene = RenderScene(structure=delta_chgcar.structure, meshes=meshes)
    views = slab_views(delta_chgcar.structure)
    width_ratios = panel_width_ratios(scene, views)
    height_inches = 2.45
    fig, axes = plt.subplots(
        1,
        3,
        figsize=(height_inches * sum(width_ratios), height_inches),
        gridspec_kw={"width_ratios": width_ratios, "wspace": 0.0},
    )
    for ax, view in zip(axes, views):
        render_view(ax, scene, view)
    fig.subplots_adjust(left=0.0, right=1.0, top=1.0, bottom=0.065, wspace=0.0)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=260, transparent=True, bbox_inches="tight", pad_inches=0.0)
    plt.close(fig)


def peak_index(delta: NDArray[np.float64]) -> tuple[int, int, int]:
    return tuple(int(value) for value in np.unravel_index(int(np.argmax(np.abs(delta))), delta.shape))


def lobe_threshold(delta: NDArray[np.float64]) -> float:
    abs_values = np.abs(delta).ravel()
    nonzero = abs_values[abs_values > 0.0]
    if len(nonzero) == 0:
        return 1.0
    return max(float(np.percentile(nonzero, ISO_PERCENTILE)), ISO_MAX_FRACTION * float(nonzero.max()))


def isosurface_meshes(delta: NDArray[np.float64], structure: Structure, threshold: float) -> list[Mesh]:
    meshes: list[Mesh] = []
    if float(delta.max()) > threshold:
        meshes.append(make_mesh(MeshRequest(delta, threshold, structure, "#D55E00")))
    depletion = -delta
    if float(depletion.max()) > threshold:
        meshes.append(make_mesh(MeshRequest(depletion, threshold, structure, "#0072B2")))
    return meshes


def make_mesh(request: MeshRequest) -> Mesh:
    vertices, faces, _, _ = marching_cubes(request.volume.astype(np.float32), level=request.threshold, allow_degenerate=False)
    frac = vertices.astype(np.float64) / np.asarray(request.volume.shape, dtype=np.float64)
    matrix = np.asarray(request.structure.lattice.matrix, dtype=np.float64)
    cart = frac[:, 0, None] * matrix[0] + frac[:, 1, None] * matrix[1] + frac[:, 2, None] * matrix[2]
    return Mesh(vertices=cart, faces=faces.astype(np.int64), color=request.color)


def render_view(ax, scene: RenderScene, view: View) -> None:
    for mesh in scene.meshes:
        add_mesh(ax, mesh, view.camera)
    draw_cell(ax, scene.structure, view.camera)
    draw_bonds(ax, scene.structure, view.camera)
    draw_atoms(ax, scene.structure, view.camera)
    set_equal_axes(ax, project(render_points(scene), view.camera))
    ax.text(0.5, -0.026, view.name, transform=ax.transAxes, ha="center", va="top", fontsize=6.5, fontweight="bold", color="black")
    ax.set_axis_off()


def panel_width_ratios(scene: RenderScene, views: list[View]) -> list[float]:
    points = render_points(scene)
    ratios = []
    for view in views:
        projected = project(points, view.camera)
        span = padded_span(projected)
        ratios.append(float(span[0] / span[1]))
    return ratios


def add_mesh(ax, mesh: Mesh, camera: Camera) -> None:
    triangles = mesh.vertices[mesh.faces]
    polygons = project(triangles.reshape(-1, 3), camera).reshape(-1, 3, 2)
    depth = dot_rows(triangles.mean(axis=1), camera.forward)
    order = np.argsort(depth)
    collection = PolyCollection(polygons[order], facecolors=shaded_face_colors(mesh)[order], edgecolors="none", linewidths=0.0, antialiased=True)
    ax.add_collection(collection)


def shaded_face_colors(mesh: Mesh) -> NDArray[np.float64]:
    triangles = mesh.vertices[mesh.faces]
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    normal_lengths = np.linalg.norm(normals, axis=1)
    normals = normals / np.maximum(normal_lengths[:, None], 1e-12)
    light = np.asarray([0.35, -0.45, 0.82], dtype=np.float64)
    light = light / np.linalg.norm(light)
    shade = 0.52 + 0.48 * np.clip((dot_rows(normals, light) + 1.0) / 2.0, 0.0, 1.0)
    base = np.asarray(to_rgba(mesh.color, alpha=0.62), dtype=np.float64)
    colors = np.tile(base, (len(mesh.faces), 1))
    colors[:, :3] = np.clip(colors[:, :3] * shade[:, None], 0.0, 1.0)
    return colors


def draw_atoms(ax, structure: Structure, camera: Camera) -> None:
    coords = np.asarray(structure.cart_coords, dtype=float)
    numbers = [atomic_numbers.get(site.specie.symbol, 0) for site in structure]
    colors = [jmol_colors[number] if number < len(jmol_colors) else (0.15, 0.15, 0.15) for number in numbers]
    projected = project(coords, camera)
    order = np.argsort(dot_rows(coords, camera.forward))
    for rank, index in enumerate(order):
        xy = projected[index]
        radius = min(ATOM_RADIUS_MAX, max(ATOM_RADIUS_MIN, ATOM_RADIUS_SCALE * covalent_radius(numbers[index])))
        zorder = 5.0 + float(rank) * 0.01
        ax.add_patch(Circle(xy, radius, facecolor=colors[index], edgecolor="black", linewidth=0.35, zorder=zorder))
        offset = radius * 0.30
        ax.add_patch(Ellipse((xy[0] - offset, xy[1] + offset), radius * 0.85, radius * 0.55, angle=32, facecolor="white", edgecolor="none", alpha=0.28, zorder=zorder + 0.01))


def draw_bonds(ax, structure: Structure, camera: Camera) -> None:
    coords = np.asarray(structure.cart_coords, dtype=np.float64)
    numbers = [atomic_numbers.get(site.specie.symbol, 0) for site in structure]
    segments: list[tuple[float, NDArray[np.float64]]] = []
    for left in range(len(coords)):
        for right in range(left + 1, len(coords)):
            segment = np.asarray([coords[left], coords[right]], dtype=np.float64)
            distance = float(np.linalg.norm(segment[0] - segment[1]))
            cutoff = bond_cutoff(numbers[left], numbers[right])
            if cutoff > 0.0 and distance <= cutoff:
                depth = float(np.mean(dot_rows(segment, camera.forward)))
                segments.append((depth, segment))
    for _, segment in sorted(segments, key=lambda item: item[0]):
        points = project(segment, camera)
        ax.plot(points[:, 0], points[:, 1], color="0.34", linewidth=0.75, solid_capstyle="round", alpha=0.62, zorder=3)


def bond_cutoff(left_number: int, right_number: int) -> float:
    left_radius = covalent_radius(left_number)
    right_radius = covalent_radius(right_number)
    if left_radius > 1.05 and right_radius > 1.05:
        return 0.0
    return min(2.45, 1.08 * (left_radius + right_radius) + 0.08)


def covalent_radius(number: int) -> float:
    if 0 < number < len(covalent_radii):
        return float(covalent_radii[number])
    return 0.8


def draw_cell(ax, structure: Structure, camera: Camera) -> None:
    matrix = np.asarray(structure.lattice.matrix, dtype=float)
    corners = {(i, j, k): i * matrix[0] + j * matrix[1] + k * matrix[2] for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    for left_key, left in corners.items():
        for right_key, right in corners.items():
            if left_key < right_key and sum(abs(a - b) for a, b in zip(left_key, right_key)) == 1:
                points = project(np.asarray([left, right], dtype=np.float64), camera)
                ax.plot(points[:, 0], points[:, 1], color="0.58", linewidth=0.55, zorder=1)


def render_points(scene: RenderScene) -> NDArray[np.float64]:
    matrix = np.asarray(scene.structure.lattice.matrix, dtype=float)
    corners = np.asarray([i * matrix[0] + j * matrix[1] + k * matrix[2] for i in (0, 1) for j in (0, 1) for k in (0, 1)], dtype=np.float64)
    arrays = [corners, np.asarray(scene.structure.cart_coords, dtype=np.float64)]
    arrays.extend(mesh.vertices for mesh in scene.meshes)
    return np.vstack(arrays)


def slab_views(structure: Structure) -> list[View]:
    matrix = np.asarray(structure.lattice.matrix, dtype=np.float64)
    a_vec, b_vec, c_vec = matrix[0], matrix[1], matrix[2]
    return [
        View("Top", make_camera(c_vec, a_vec)),
        View("Side A", make_camera(a_vec, c_vec)),
        View("Side B", make_camera(b_vec, c_vec)),
    ]


def make_camera(forward_hint: NDArray[np.float64], up_hint: NDArray[np.float64]) -> Camera:
    forward = normalize(forward_hint)
    up = up_hint - forward * float(np.sum(forward * up_hint))
    if float(np.linalg.norm(up)) < 1e-8:
        up = np.asarray([0.0, 0.0, 1.0], dtype=np.float64) - forward * forward[2]
    up = normalize(up)
    right = normalize(np.cross(forward, up))
    up = normalize(np.cross(right, forward))
    return Camera(right=right, up=up, forward=forward)


def normalize(vector: NDArray[np.float64]) -> NDArray[np.float64]:
    return vector / max(float(np.linalg.norm(vector)), 1e-12)


def project(points: NDArray[np.float64], camera: Camera) -> NDArray[np.float64]:
    return np.column_stack((dot_rows(points, camera.right), dot_rows(points, camera.up))).astype(np.float64)


def dot_rows(points: NDArray[np.float64], vector: NDArray[np.float64]) -> NDArray[np.float64]:
    return np.sum(points * vector[None, :], axis=1)


def set_equal_axes(ax, points: NDArray[np.float64]) -> None:
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    centers = (maxs + mins) / 2.0
    span = padded_span(points)
    ax.set_xlim(centers[0] - span[0] / 2.0, centers[0] + span[0] / 2.0)
    ax.set_ylim(centers[1] - span[1] / 2.0, centers[1] + span[1] / 2.0)
    ax.set_aspect("equal", adjustable="box")
    ax.set_anchor("C")


def padded_span(points: NDArray[np.float64]) -> NDArray[np.float64]:
    ranges = np.maximum(points.max(axis=0) - points.min(axis=0), 1e-6)
    pad = max(float(ranges.max()) * 0.02, 0.08)
    return ranges + 2.0 * pad
