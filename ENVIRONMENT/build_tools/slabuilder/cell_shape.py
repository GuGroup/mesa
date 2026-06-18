"""Cell-shape scoring and periodic-safe transforms for slab generation."""

from __future__ import annotations

from dataclasses import dataclass
from math import acos, degrees, log
from typing import Iterable

import numpy as np
from ase import Atoms
from ase.build import make_supercell
from ase.constraints import FixAtoms


@dataclass(frozen=True)
class CellShapeMetrics:
    """Geometry metrics for a 3D cell."""

    lengths: tuple[float, float, float]
    angles: tuple[float, float, float]
    area_ab: float
    volume: float
    lateral_aspect_ratio: float
    full_aspect_ratio: float
    max_lateral_length: float
    inplane_angle_deviation: float
    offdiagonal_ratio: float


def cell_matrix(cell_like) -> np.ndarray:
    """Return a 3x3 float cell matrix from ASE, pymatgen, or array-like input."""
    if isinstance(cell_like, Atoms):
        matrix = np.array(cell_like.get_cell(), dtype=float)
    elif hasattr(cell_like, "matrix"):
        matrix = np.array(cell_like.matrix, dtype=float)
    elif hasattr(cell_like, "lattice") and hasattr(cell_like.lattice, "matrix"):
        matrix = np.array(cell_like.lattice.matrix, dtype=float)
    else:
        matrix = np.array(cell_like, dtype=float)

    if matrix.shape == (2, 2):
        out = np.eye(3, dtype=float)
        out[:2, :2] = matrix
        return out
    if matrix.shape == (2, 3):
        out = np.eye(3, dtype=float)
        out[:2, :] = matrix
        return out
    if matrix.shape != (3, 3):
        raise ValueError(f"cell must be 2x2, 2x3, or 3x3; got shape {matrix.shape}")
    return matrix


def cell_shape_metrics(cell_like) -> CellShapeMetrics:
    """Compute shape metrics for a cell without changing its basis."""
    matrix = cell_matrix(cell_like)
    a, b, c = matrix
    la = _norm(a)
    lb = _norm(b)
    lc = _norm(c)
    alpha = _angle_deg(b, c)
    beta = _angle_deg(a, c)
    gamma = _angle_deg(a, b)
    area_ab = float(np.linalg.norm(np.cross(a, b)))
    volume = float(abs(np.linalg.det(matrix)))
    lateral_aspect = _safe_ratio(max(la, lb), min(la, lb))
    positive_lengths = [value for value in (la, lb, lc) if value > 1e-12]
    full_aspect = _safe_ratio(max(positive_lengths), min(positive_lengths)) if positive_lengths else float("inf")
    offdiag = _offdiagonal_ratio(matrix)
    return CellShapeMetrics(
        lengths=(la, lb, lc),
        angles=(alpha, beta, gamma),
        area_ab=area_ab,
        volume=volume,
        lateral_aspect_ratio=lateral_aspect,
        full_aspect_ratio=full_aspect,
        max_lateral_length=max(la, lb),
        inplane_angle_deviation=abs(gamma - 90.0),
        offdiagonal_ratio=offdiag,
    )


def enumerate_2d_integer_transforms(
    max_area_multiple: int,
    max_element: int,
    *,
    include_identity: bool = True,
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Enumerate right-handed 2D integer basis transforms.

    The returned matrices are suitable for periodic supercell construction using
    row-vector convention: ``new_vectors = matrix @ old_vectors``.
    """
    max_area_multiple = int(max_area_multiple)
    max_element = int(max_element)
    if max_area_multiple < 1:
        raise ValueError("max_area_multiple must be >= 1")
    if max_element < 1:
        raise ValueError("max_element must be >= 1")

    values = range(-max_element, max_element + 1)
    transforms: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    for p in values:
        for q in values:
            for r in values:
                for s in values:
                    det = p * s - q * r
                    if det <= 0 or det > max_area_multiple:
                        continue
                    matrix = _canonical_transform(((p, q), (r, s)))
                    if matrix == ((1, 0), (0, 1)) and not include_identity:
                        continue
                    transforms.add(matrix)

    return sorted(
        transforms,
        key=lambda matrix: (
            _det2(matrix),
            sum(abs(value) for row in matrix for value in row),
            matrix,
        ),
    )


def transform_2d_cell(
    cell_2d,
    transform: Iterable[Iterable[int]],
) -> np.ndarray:
    """Apply a 2D integer transform to the first two cell vectors."""
    base = _cell_2d(cell_2d)
    matrix = _transform_matrix(transform)
    return matrix @ base


def score_2d_cell_shape(
    cell_2d,
    *,
    atom_count: int | None = None,
    target_atom_count: int | None = None,
    target_lateral_size: float | None = None,
    max_lateral_length: float | None = None,
) -> float:
    """Return a scalar shape score; lower is better.

    The score is intentionally dimensionless and conservative. It strongly
    penalizes non-orthogonal in-plane cells, then aspect ratio, then target-size
    and atom-count deviations.
    """
    cell = _cell_2d(cell_2d)
    metrics = cell_shape_metrics(_cell_3d_from_2d(cell))
    angle_penalty = metrics.inplane_angle_deviation / 90.0
    aspect_penalty = abs(log(max(metrics.lateral_aspect_ratio, 1e-12)))
    offdiag_penalty = metrics.offdiagonal_ratio
    score = 4.0 * angle_penalty + 1.5 * aspect_penalty + 0.1 * offdiag_penalty

    if target_lateral_size is not None and target_lateral_size > 0:
        lengths = metrics.lengths[:2]
        size_penalty = sum(abs(length - target_lateral_size) / target_lateral_size for length in lengths) / 2.0
        score += 0.75 * size_penalty

    if atom_count is not None and target_atom_count is not None and target_atom_count > 0:
        score += 0.75 * abs(int(atom_count) - int(target_atom_count)) / float(target_atom_count)

    if max_lateral_length is not None and max_lateral_length > 0:
        excess = max(0.0, metrics.max_lateral_length - max_lateral_length) / max_lateral_length
        score += 20.0 * excess

    return float(score)


def make_2d_supercell(atoms: Atoms, transform: Iterable[Iterable[int]], *, wrap: bool = True) -> Atoms:
    """Apply a 2D integer transform to ASE atoms while preserving the c vector."""
    matrix = _transform_matrix(transform)
    area_multiple = int(round(np.linalg.det(matrix)))
    if area_multiple <= 0:
        raise ValueError("2D transform determinant must be positive")
    supercell_matrix = np.eye(3, dtype=int)
    supercell_matrix[:2, :2] = matrix
    result = make_supercell(atoms, supercell_matrix, wrap=wrap, order="atom-major")
    result.set_pbc(atoms.get_pbc())
    fixed_indices = _fixed_indices(atoms)
    if fixed_indices:
        remapped = [
            new_index
            for old_index in fixed_indices
            for new_index in range(old_index * area_multiple, (old_index + 1) * area_multiple)
        ]
        result.set_constraint(FixAtoms(indices=remapped))
    return result


def _cell_2d(cell_2d) -> np.ndarray:
    arr = np.array(cell_2d, dtype=float)
    if arr.shape == (3, 3):
        arr = arr[:2, :]
    elif arr.shape == (2, 2):
        out = np.zeros((2, 3), dtype=float)
        out[:, :2] = arr
        arr = out
    elif arr.shape != (2, 3):
        raise ValueError(f"2D cell must be 2x2, 2x3, or 3x3; got shape {arr.shape}")
    if np.linalg.norm(np.cross(arr[0], arr[1])) <= 1e-12:
        raise ValueError("2D cell vectors must span a non-zero area")
    return arr


def _cell_3d_from_2d(cell_2d: np.ndarray) -> np.ndarray:
    cell = np.eye(3, dtype=float)
    cell[:2, :] = _cell_2d(cell_2d)
    c = np.cross(cell[0], cell[1])
    norm = _norm(c)
    if norm > 1e-12:
        cell[2] = c / norm
    return cell


def _transform_matrix(transform: Iterable[Iterable[int]]) -> np.ndarray:
    matrix = np.array(transform, dtype=int)
    if matrix.shape != (2, 2):
        raise ValueError(f"2D transform must be 2x2; got shape {matrix.shape}")
    det = int(round(np.linalg.det(matrix)))
    if det == 0:
        raise ValueError("2D transform determinant must be non-zero")
    return matrix


def _det2(matrix: tuple[tuple[int, int], tuple[int, int]]) -> int:
    return int(matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0])


def _canonical_transform(
    matrix: tuple[tuple[int, int], tuple[int, int]],
) -> tuple[tuple[int, int], tuple[int, int]]:
    first_row = matrix[0]
    first_nonzero = next((value for value in first_row if value != 0), 0)
    if first_nonzero < 0:
        return tuple(tuple(-value for value in row) for row in matrix)  # type: ignore[return-value]
    return matrix


def _norm(vector: np.ndarray) -> float:
    return float(np.linalg.norm(vector))


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 1e-12:
        return float("inf")
    return float(numerator / denominator)


def _angle_deg(v1: np.ndarray, v2: np.ndarray) -> float:
    n1 = _norm(v1)
    n2 = _norm(v2)
    if n1 <= 1e-12 or n2 <= 1e-12:
        return 0.0
    cosang = float(np.dot(v1, v2) / (n1 * n2))
    return float(degrees(acos(max(-1.0, min(1.0, cosang)))))


def _offdiagonal_ratio(matrix: np.ndarray) -> float:
    diagonal = np.diag(np.diag(matrix))
    offdiag_norm = float(np.linalg.norm(matrix - diagonal))
    total_norm = float(np.linalg.norm(matrix))
    if total_norm <= 1e-12:
        return 0.0
    return offdiag_norm / total_norm


def _fixed_indices(atoms: Atoms) -> list[int]:
    indices: list[int] = []
    for constraint in atoms.constraints:
        if isinstance(constraint, FixAtoms):
            indices.extend(int(index) for index in constraint.get_indices())
    return sorted(set(indices))


__all__ = [
    "CellShapeMetrics",
    "cell_matrix",
    "cell_shape_metrics",
    "enumerate_2d_integer_transforms",
    "make_2d_supercell",
    "score_2d_cell_shape",
    "transform_2d_cell",
]
