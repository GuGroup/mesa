#!/usr/bin/env python3
"""Pure ASE + matplotlib relaxation rendering core (no aseview, no browser).

Projects atoms with an orthographic camera (a view direction + up vector,
same convention as ``camera_views()``), depth-sorts bonds and atoms with a
painter's algorithm, and draws shaded jmol-colored spheres with a dashed halo
ring around FixAtoms-constrained atoms.
"""
from __future__ import annotations

import json
from typing import Any, Sequence

import numpy as np

Frame = tuple[np.ndarray, np.ndarray, np.ndarray]


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else v


def camera_frame(direction: Sequence[float], up: Sequence[float]) -> Frame:
    """Orthonormal (screen_x, screen_y, view_axis) camera basis.

    ``direction`` is the vector from the target to the camera (matches the
    existing ``camera_views()`` convention: "top" uses the surface normal so
    the camera sits above the slab looking down). Projected depth grows
    toward the camera (larger = nearer), used to depth-sort for painter's
    algorithm.
    """
    view_axis = _unit(np.asarray(direction, dtype=float))
    up_hint = _unit(np.asarray(up, dtype=float))
    screen_x = _unit(np.cross(up_hint, view_axis))
    if float(np.linalg.norm(screen_x)) < 1e-8:
        fallback = np.array([1.0, 0.0, 0.0]) if abs(view_axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        screen_x = _unit(np.cross(fallback, view_axis))
    screen_y = _unit(np.cross(view_axis, screen_x))
    return screen_x, screen_y, view_axis


def project(positions: np.ndarray, frame: Frame) -> tuple[np.ndarray, np.ndarray]:
    """Project Nx3 positions to camera-plane (x, y) and depth (higher = nearer)."""
    screen_x, screen_y, view_axis = frame
    positions = np.asarray(positions, dtype=float)
    xy = np.column_stack([positions @ screen_x, positions @ screen_y])
    depth = positions @ view_axis
    return xy, depth


# ---------------------------------------------------------------------------
# Element table — radius (Å) + color, keyed by symbol.
# ---------------------------------------------------------------------------
# Matches a specific reference table (three.js/Jmol-style) rather than ASE's
# own jmol_colors/covalent_radii, so renders match that palette exactly.
# Hex ints are 0xRRGGBB.

_ELEMENT_TABLE: dict[str, tuple[float, int]] = {
    "H": (0.31, 0xFFFFFF), "He": (0.28, 0xD9FFFF),
    "Li": (1.28, 0xCC80FF), "Be": (0.96, 0xC2FF00),
    "B": (0.84, 0xFFB5B5), "C": (0.76, 0x909090),
    "N": (0.71, 0x3050F8), "O": (0.66, 0xFF0D0D),
    "F": (0.57, 0x90E050), "Ne": (0.58, 0xB3E3F5),
    "Na": (1.66, 0xAB5CF2), "Mg": (1.41, 0x8AFF00),
    "Al": (1.21, 0xBFA6A6), "Si": (1.11, 0xF0C8A0),
    "P": (1.07, 0xFF8000), "S": (1.05, 0xFFFF30),
    "Cl": (1.02, 0x1FF01F), "Ar": (1.06, 0x80D1E3),
    "K": (2.03, 0x8F40D4), "Ca": (1.76, 0x3DFF00),
    "Sc": (1.70, 0xE6E6E6), "Ti": (1.60, 0xBFC2C7),
    "V": (1.53, 0xA6A6AB), "Cr": (1.39, 0x8A99C7),
    "Mn": (1.61, 0x9C7AC7), "Fe": (1.52, 0xE06633),
    "Co": (1.50, 0xF090A0), "Ni": (1.24, 0x50D050),
    "Cu": (1.32, 0xC88033), "Zn": (1.22, 0x7D80B0),
    "Ga": (1.22, 0xC28F8F), "Ge": (1.20, 0x668F8F),
    "As": (1.19, 0xBD80E3), "Se": (1.20, 0xFFA100),
    "Br": (1.20, 0xA62929), "Kr": (1.16, 0x5CB8D1),
    "Rb": (2.20, 0x702EB0), "Sr": (1.95, 0x00FF00),
    "Y": (1.90, 0x94FFFF), "Zr": (1.75, 0x94E0E0),
    "Nb": (1.64, 0x73C2C9), "Mo": (1.54, 0x54B5B5),
    "Tc": (1.47, 0x3B9E9E), "Ru": (1.46, 0x248F8F),
    "Rh": (1.42, 0x0A7D8C), "Pd": (1.39, 0x006985),
    "Ag": (1.45, 0xC0C0C0), "Cd": (1.44, 0xFFD98F),
    "In": (1.42, 0xA67573), "Sn": (1.39, 0x668080),
    "Sb": (1.39, 0x9E63B5), "Te": (1.38, 0xD47A00),
    "I": (1.39, 0x940094), "Xe": (1.40, 0x429EB0),
    "Cs": (2.44, 0x57178F), "Ba": (2.15, 0x00C900),
    "La": (2.07, 0x70D4FF), "Ce": (2.04, 0xFFFFC7),
    "Pr": (2.03, 0xD9FFC7), "Nd": (2.01, 0xC7FFC7),
    "Pm": (1.99, 0xA3FFC7), "Sm": (1.98, 0x8FFFC7),
    "Eu": (1.98, 0x61FFC7), "Gd": (1.96, 0x45FFC7),
    "Tb": (1.94, 0x30FFC7), "Dy": (1.92, 0x1FFFC7),
    "Ho": (1.92, 0x00FF9C), "Er": (1.89, 0x00E675),
    "Tm": (1.90, 0x00D452), "Yb": (1.87, 0x00BF38),
    "Lu": (1.87, 0x00AB24), "Hf": (1.75, 0x4DC2FF),
    "Ta": (1.70, 0x4DA6FF), "W": (1.62, 0x2194D6),
    "Re": (1.51, 0x267DAB), "Os": (1.44, 0x266696),
    "Ir": (1.41, 0x175487), "Pt": (1.36, 0xD0D0E0),
    "Au": (1.36, 0xFFD123), "Hg": (1.32, 0xB8B8D0),
    "Tl": (1.45, 0xA6544D), "Pb": (1.46, 0x575961),
    "Bi": (1.48, 0x9E4FB5), "Po": (1.40, 0xAB5C00),
    "At": (1.50, 0x754F45), "Rn": (1.50, 0x428296),
    "Fr": (2.60, 0x420066), "Ra": (2.21, 0x007D00),
    "Ac": (2.15, 0x70ABFA), "Th": (2.06, 0x00BAFF),
    "Pa": (2.00, 0x00A1FF), "U": (1.96, 0x008FFF),
    "Np": (1.90, 0x0080FF), "Pu": (1.87, 0x006BFF),
    "Am": (1.80, 0x545CF2), "Cm": (1.69, 0x785CE3),
    "Bk": (1.70, 0x8A4FE3), "Cf": (1.70, 0xA136D4),
    "Es": (1.70, 0xB31FD4), "Fm": (1.70, 0xB31FBA),
    "Md": (1.70, 0xB30DA6), "No": (1.70, 0xBD0D87),
    "Lr": (1.70, 0xC70066), "Rf": (1.70, 0xCC0059),
    "Db": (1.70, 0xD1004F), "Sg": (1.70, 0xD90045),
    "Bh": (1.70, 0xE00038), "Hs": (1.70, 0xE6002E),
    "Mt": (1.70, 0xEB0026),
}
_DEFAULT_ELEMENT = (0.70, 0xFFC0CB)  # pink, for anything not in the table above


def _hex_to_rgb(hex_int: int) -> tuple[float, float, float]:
    return ((hex_int >> 16 & 255) / 255.0, (hex_int >> 8 & 255) / 255.0, (hex_int & 255) / 255.0)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def element_visuals(numbers: np.ndarray, atom_scale: float) -> tuple[np.ndarray, np.ndarray]:
    from ase.data import chemical_symbols

    numbers = np.asarray(numbers, dtype=int)
    radii = np.empty(len(numbers), dtype=float)
    colors = np.empty((len(numbers), 3), dtype=float)
    for k, z in enumerate(numbers):
        symbol = chemical_symbols[z] if 0 <= z < len(chemical_symbols) else None
        radius, hex_color = _ELEMENT_TABLE.get(symbol, _DEFAULT_ELEMENT)
        radii[k] = radius * atom_scale
        colors[k] = _hex_to_rgb(hex_color)
    return radii, colors


def adsorbate_mask(atoms: Any) -> np.ndarray | None:
    """Boolean mask (True = adsorbate atom), or ``None`` if it can't be told apart.

    Prefers slabuilder's explicit atom-index metadata (least ambiguous), then
    its tag convention — confirmed via the info markers slabuilder itself
    writes, since a raw tag value alone is not a portable signal (plain
    ``ase.build`` surface tagging uses an unrelated per-layer 1..N scheme, and
    ``add_adsorbate`` leaves the adsorbate at the default tag 0, which is the
    *opposite* of slabuilder's own 0/1/2 convention). Returns ``None`` — draw
    every bond, same as before — when no such marker exists at all, which is
    the common case for a bare VASP CONTCAR/vasprun.xml/OUTCAR: VASP has no
    concept of adsorbate identity, so nothing survives to those formats.
    """
    info = getattr(atoms, "info", None) or {}
    for key in ("adsorbate_atom_indices_json", "adsorbate_metadata_json"):
        raw = info.get(key)
        if not raw:
            continue
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        indices = parsed.get("atom_indices") if isinstance(parsed, dict) else parsed
        if indices:
            mask = np.zeros(len(atoms), dtype=bool)
            mask[[int(i) for i in indices]] = True
            return mask
    if "adsorbate_tag" in info and "tags" in atoms.arrays:
        return np.asarray(atoms.get_tags()) == int(info["adsorbate_tag"])
    return None


def compute_bonds(
    atoms: Any,
    scale: float = 1.05,
    ads_mask: np.ndarray | None = None,
) -> list[tuple[int, int]]:
    """Same-image adsorbate-scoped covalent bonds as (i, j) pairs, i < j.

    Bonds only get drawn when the adsorbate can actually be identified —
    ``ads_mask`` must be given and non-``None``. This is deliberately
    opt-in rather than "draw everything when we can't tell": with no
    adsorbate info at all (e.g. a bare VASP CONTCAR, or a clean slab with no
    adsorbate), there is nothing bonds would usefully distinguish, and
    guessing risks drawing a dense, misleading slab-lattice mesh. When
    ``ads_mask`` is given, only adsorbate-adsorbate and adsorbate-slab bonds
    are kept — slab-slab bonds (neither endpoint an adsorbate atom) are
    dropped so the substrate renders as bare spheres. Bonds that only exist
    through a periodic shift (an atom bonded to a neighbor's periodic image)
    are always dropped: drawing them as a straight line would cut across the
    whole cell.
    """
    from ase.neighborlist import natural_cutoffs, neighbor_list

    if len(atoms) == 0 or ads_mask is None:
        return []
    cutoffs = natural_cutoffs(atoms, mult=scale)
    i, j, S = neighbor_list("ijS", atoms, cutoffs)
    pairs: set[tuple[int, int]] = set()
    for a, b, shift in zip(i, j, S):
        if a == b or np.any(shift != 0):
            continue
        if not (ads_mask[a] or ads_mask[b]):
            continue
        pairs.add((int(a), int(b)) if a < b else (int(b), int(a)))
    return sorted(pairs)


def cell_edges(cell: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """The 12 edges of the cell parallelepiped as (start, end) point pairs."""
    a, b, c = np.asarray(cell, dtype=float)
    corners = {(i, j, k): i * a + j * b + k * c for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    edges = []
    keys = list(corners)
    for p in keys:
        for q in keys:
            if p < q and sum(abs(pi - qi) for pi, qi in zip(p, q)) == 1:
                edges.append((corners[p], corners[q]))
    return edges


def fixed_indices(atoms: Any) -> list[int]:
    indices: list[int] = []
    for constraint in getattr(atoms, "constraints", []):
        value = getattr(constraint, "index", None)
        if value is None:
            continue
        try:
            indices.extend(int(i) for i in np.asarray(value).ravel())
        except Exception:
            continue
    return sorted(set(i for i in indices if 0 <= i < len(atoms)))


def has_real_cell(atoms: Any) -> bool:
    cell = getattr(atoms, "cell", None)
    return cell is not None and abs(np.linalg.det(np.asarray(cell))) > 1e-8


# ---------------------------------------------------------------------------
# Bounds (computed analytically so the figure is sized tight up front)
# ---------------------------------------------------------------------------

def frame_bounds(
    atoms_list: Sequence[Any],
    frame: Frame,
    *,
    atom_scale: float,
    margin_frac: float = 0.06,
    include_cell: bool = True,
) -> tuple[float, float, float, float]:
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    for atoms in atoms_list:
        xy, _ = project(np.asarray(atoms.positions, dtype=float), frame)
        radii, _ = element_visuals(atoms.get_atomic_numbers(), atom_scale)
        xs.append(xy[:, 0] - radii)
        xs.append(xy[:, 0] + radii)
        ys.append(xy[:, 1] - radii)
        ys.append(xy[:, 1] + radii)
        if include_cell and has_real_cell(atoms):
            corners = np.array([p for edge in cell_edges(atoms.cell.array) for p in edge])
            cxy, _ = project(corners, frame)
            xs.append(cxy[:, 0])
            ys.append(cxy[:, 1])
    xmin, xmax = float(np.concatenate(xs).min()), float(np.concatenate(xs).max())
    ymin, ymax = float(np.concatenate(ys).min()), float(np.concatenate(ys).max())
    pad_x = max((xmax - xmin) * margin_frac, 1e-3)
    pad_y = max((ymax - ymin) * margin_frac, 1e-3)
    return xmin - pad_x, xmax + pad_x, ymin - pad_y, ymax + pad_y


def figure_for_bounds(bounds: tuple[float, float, float, float], width_px: int, height_px: int, dpi: int = 200):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    xmin, xmax, ymin, ymax = bounds
    aspect = (xmax - xmin) / (ymax - ymin)
    target_aspect = width_px / height_px
    # Grow the shorter data axis so the content aspect matches the requested
    # canvas aspect without distortion (no stretch, no leftover margin).
    if aspect > target_aspect:
        cy = 0.5 * (ymin + ymax)
        half = 0.5 * (xmax - xmin) / target_aspect
        ymin, ymax = cy - half, cy + half
    else:
        cx = 0.5 * (xmin + xmax)
        half = 0.5 * (ymax - ymin) * target_aspect
        xmin, xmax = cx - half, cx + half
    fig = plt.figure(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)
    ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    return fig, ax


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------
#
# Everything (cell wireframe, bonds, atoms — including, for the trajectory
# overlay, several faded copies of the same mover atom from other frames) is
# collected as depth-tagged "items" and painter's-algorithm sorted *together*
# before drawing. This matters most for a top-down view of a close-packed
# slab: without a single shared depth sort, an adsorbate sitting above the
# surface would be drawn behind the opaque substrate whenever a fixed
# z-order band put "substrate" above "adsorbate", even though the adsorbate
# is genuinely nearer the camera.

Item = tuple[float, str, Any]


def _draw_atom(ax, xy, radius, color, *, alpha, zorder, is_fixed, show_fixed_halo):
    from matplotlib.lines import Line2D
    from matplotlib.patches import Circle, Ellipse

    fill_alpha = (0.82 if is_fixed else 1.0) * alpha
    ax.add_patch(Circle(
        xy, radius, facecolor=color, edgecolor=(0.12, 0.12, 0.12),
        linewidth=0.6, alpha=fill_alpha, zorder=zorder + 0.3,
    ))
    highlight_offset = radius * 0.32
    ax.add_patch(Ellipse(
        (xy[0] - highlight_offset, xy[1] + highlight_offset),
        width=radius * 0.85, height=radius * 0.6, angle=32,
        facecolor="white", edgecolor="none", alpha=0.38 * alpha, zorder=zorder + 0.6,
    ))
    if is_fixed and show_fixed_halo:
        # ase-gui's own convention for a constrained atom: a small X drawn on
        # top of the sphere, rather than a ring around it — stays inside the
        # atom's own footprint instead of expanding it, so fixed layers don't
        # look bigger/spikier than mobile ones in a tightly packed slab.
        s = radius * 0.62
        for dy1, dy2 in ((-s, s), (s, -s)):
            ax.add_line(Line2D(
                [xy[0] - s, xy[0] + s], [xy[1] + dy1, xy[1] + dy2],
                color="black", linewidth=1.8, alpha=0.95 * alpha, zorder=zorder + 0.7,
                solid_capstyle="round",
            ))


_AUTO_ADS_MASK = object()


def frame_items(
    atoms: Any,
    frame: Frame,
    *,
    alpha: float = 1.0,
    bond_scale: float = 1.05,
    atom_scale: float = 0.72,
    show_cell: bool = True,
    show_fixed_halo: bool = True,
    fixed: Sequence[int] | None = None,
    ads_mask: Any = _AUTO_ADS_MASK,
) -> list[Item]:
    """Depth-tagged (depth, kind, payload) primitives for one ``Atoms`` frame.

    Depth grows toward the camera; combine lists from several frames and pass
    the concatenation to ``draw_items`` for a single correctly-occluded
    painter's-algorithm pass.

    ``ads_mask`` defaults to auto-detecting via ``adsorbate_mask(atoms)``.
    Pass an explicit mask (or ``None`` to disable suppression) when ``atoms``
    is a sub-selection — e.g. ``full_atoms[some_indices]`` — since its
    ``.info`` still carries the *parent's* index metadata, which no longer
    lines up with the subset's own local indices.
    """
    positions = np.asarray(atoms.positions, dtype=float)
    numbers = atoms.get_atomic_numbers()
    xy, depth = project(positions, frame)
    radii, colors = element_visuals(numbers, atom_scale)
    fixed_set = set(fixed) if fixed is not None else set(fixed_indices(atoms))
    ads_mask = adsorbate_mask(atoms) if ads_mask is _AUTO_ADS_MASK else ads_mask

    items: list[Item] = []
    if show_cell and has_real_cell(atoms):
        cell_depth = float(depth.min()) - 1.0 if len(depth) else 0.0
        for p, q in cell_edges(atoms.cell.array):
            pts, _ = project(np.array([p, q]), frame)
            items.append((cell_depth, "cell", (pts, alpha)))

    for i in range(len(atoms)):
        items.append((
            float(depth[i]), "atom",
            (xy[i], radii[i], colors[i], alpha, i in fixed_set, show_fixed_halo),
        ))
    for i, j in compute_bonds(atoms, scale=bond_scale, ads_mask=ads_mask):
        # Trim to surface-to-surface (not center-to-center): atoms always
        # draw over bonds now (see draw_items), but if the line still ran
        # all the way to each center, a big enough atom_scale could shrink
        # the *visible* sliver between the two circles down to nothing even
        # though the bond itself is real. Trimming means the full gap always
        # shows regardless of how large the spheres are.
        p, q = xy[i], xy[j]
        vec = q - p
        dist = float(np.linalg.norm(vec))
        if dist > 1e-9:
            unit = vec / dist
            p, q = p + unit * radii[i], q - unit * radii[j]
        items.append((float((depth[i] + depth[j]) / 2.0), "bond", (p, q, alpha)))
    return items


def draw_items(ax, items: Sequence[Item]) -> None:
    """Sort depth-tagged items back-to-front and draw them (painter's algorithm).

    Atoms are always drawn after (on top of) every cell/bond line, regardless
    of true depth: a bond's z-order is the *average* of its two endpoints, so
    whichever endpoint is farther from the camera would otherwise get a bond
    line drawn across its face instead of tucking behind it. Depth order is
    still respected *within* each group — atom-vs-atom and bond-vs-bond — so
    e.g. a foreground adsorbate atom still correctly occludes a background
    substrate atom.
    """
    from matplotlib.lines import Line2D

    ordered = sorted(items, key=lambda it: it[0])
    non_atoms = [it for it in ordered if it[1] != "atom"]
    atoms = [it for it in ordered if it[1] == "atom"]

    for rank, (_, kind, payload) in enumerate(non_atoms):
        z = rank * 10.0
        if kind == "cell":
            pts, alpha = payload
            ax.add_line(Line2D(
                pts[:, 0], pts[:, 1], color="#64748b", linewidth=1.0, alpha=0.85 * alpha, zorder=z,
            ))
        elif kind == "bond":
            p, q, alpha = payload
            ax.add_line(Line2D(
                [p[0], q[0]], [p[1], q[1]], color=(0.15, 0.15, 0.15),
                linewidth=1.6, alpha=0.9 * alpha, zorder=z, solid_capstyle="round",
            ))

    base = len(non_atoms) * 10.0
    for rank, (_, kind, payload) in enumerate(atoms):
        z = base + rank * 10.0
        xy, radius, color, alpha, is_fixed, show_fixed_halo = payload
        _draw_atom(ax, xy, radius, color, alpha=alpha, zorder=z, is_fixed=is_fixed, show_fixed_halo=show_fixed_halo)


def draw_frame(
    ax,
    atoms: Any,
    frame: Frame,
    *,
    alpha: float = 1.0,
    bond_scale: float = 1.05,
    atom_scale: float = 0.72,
    show_cell: bool = True,
    show_fixed_halo: bool = True,
    fixed: Sequence[int] | None = None,
) -> None:
    """Depth-sorted render of one ``Atoms`` frame onto ``ax``."""
    draw_items(ax, frame_items(
        atoms, frame, alpha=alpha, bond_scale=bond_scale, atom_scale=atom_scale,
        show_cell=show_cell, show_fixed_halo=show_fixed_halo, fixed=fixed,
    ))
