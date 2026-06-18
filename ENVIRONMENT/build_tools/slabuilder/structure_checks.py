"""Shared structure sanity checks."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from ase import Atoms


@dataclass(frozen=True)
class MinDistanceCheck:
    """Minimum interatomic distance result."""

    passed: bool
    min_distance: float
    atom_i: int | None = None
    atom_j: int | None = None
    threshold: float = 0.5


def check_min_distance(
    atoms: Atoms,
    *,
    threshold: float = 0.5,
    mic: bool = True,
) -> MinDistanceCheck:
    """Check for implausibly close atom contacts.

    The default threshold is intentionally weak. It catches overlaps from bad
    placement while leaving normal bonds untouched.
    """
    if len(atoms) < 2:
        return MinDistanceCheck(True, float("inf"), threshold=threshold)
    if threshold < 0:
        raise ValueError("threshold must be non-negative")

    distances = atoms.get_all_distances(mic=mic)
    # Mask only the diagonal self-distances. Masking every near-zero value (the old
    # `distances <= 1e-12 = inf`) also hid REAL off-diagonal zeros, so two distinct
    # atoms at the exact same position were reported as min_distance=inf, passed=True
    # — silently admitting physically impossible structures (MODELING-1).
    np.fill_diagonal(distances, np.inf)
    flat_index = int(np.argmin(distances))
    i, j = np.unravel_index(flat_index, distances.shape)
    min_distance = float(distances[i, j])
    passed = bool(min_distance >= threshold)
    return MinDistanceCheck(
        passed=passed,
        min_distance=min_distance,
        atom_i=int(i),
        atom_j=int(j),
        threshold=float(threshold),
    )

