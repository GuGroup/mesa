"""
slab_gen.py — Tool 3: Slab generation from bulk structures.

Backend selection
-----------------
``generate_slab`` accepts a ``backend`` parameter:

    'catkit'    — CatKit SlabGenerator (ASE-native, auto surface atom
                detection, 4 termination modes, bond graph attached).
    'pymatgen'  — pymatgen SlabGenerator (lll_reduce, polar/symmetry filters).
    'surfaxe'   — surfaxe.generate_slabs (oxide/nitride only; symmetrized,
                non-polar; falls back to 'pymatgen' if unavailable).

Target-based routing (generate_slab unified API)
------------------------------------------------
    The unified API searches layer counts and lateral supercells, then chooses
    the candidate closest to the target atom count, a/b size, and slab
    thickness. When backend is omitted, oxide/nitride-like compositions are
    routed to surfaxe and other compositions to catkit.

All slabs are returned as both pymatgen Slab and ASE Atoms objects.
Layer fixing uses ASE FixAtoms constraints (VASP selective dynamics on export).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
from ase import Atoms
from ase.constraints import FixAtoms
from pymatgen.core import Structure
from pymatgen.core.surface import SlabGenerator as PmgSlabGenerator, Slab

from slabuilder.backend_policy import Backend, choose_backend_for_structure
from slabuilder.config import (
    DEFAULT_VACUUM_ANGSTROM,
    TARGET_LATERAL_SIZE_ANGSTROM,
    LATERAL_TOLERANCE_ANGSTROM,
    TARGET_SLAB_THICKNESS_ANGSTROM,
    TARGET_ATOM_COUNT,
    ATOM_COUNT_TOLERANCE,
)
from slabuilder.cell_shape import (
    cell_shape_metrics,
    enumerate_2d_integer_transforms,
    make_2d_supercell,
    score_2d_cell_shape,
    transform_2d_cell,
)
from slabuilder.utils import get_conventional_structure, pymatgen_to_ase, ase_to_pymatgen

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SlabResult:
    """A generated slab structure with metadata.

    Attributes:
        slab:          pymatgen Slab object when available; Structure fallback
                       only if a backend cannot preserve slab metadata.
        ase_atoms:     ASE Atoms object (with FixAtoms constraint applied).
        miller_index:  Miller index used to generate this slab.
        n_atoms:       Total number of atoms in the slab.
        n_layers:      Estimated number of atomic layers.
        termination:   Termination index (for slabs with multiple terminations).
        is_polar:      Whether the slab has a net dipole moment.
        is_symmetric:  Whether top and bottom surfaces are equivalent.
        fix_indices:   Indices of fixed (bottom) atoms in the ASE Atoms object.
        lateral_a:     Lattice parameter a (Å) of the slab supercell.
        lateral_b:     Lattice parameter b (Å) of the slab supercell.
        slab_thickness: Slab thickness in Å, excluding vacuum.
        backend:       Which backend was actually used to generate this slab.
    """
    slab: Slab | Structure | None
    ase_atoms: Atoms
    miller_index: tuple[int, int, int]
    n_atoms: int
    n_layers: int
    termination: int = 0
    is_polar: bool = False
    is_symmetric: bool = True
    fix_indices: list[int] = field(default_factory=list)
    lateral_a: float = 0.0
    lateral_b: float = 0.0
    slab_thickness: float = 0.0
    backend: str = "catkit"
    supercell_na: int = 1
    supercell_nb: int = 1
    supercell_matrix: tuple[tuple[int, int], tuple[int, int]] = ((1, 0), (0, 1))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _estimate_layers_ase(atoms: Atoms) -> int:
    """Estimate number of distinct atomic layers from ASE Atoms z-coordinates."""
    z_coords = np.sort(atoms.positions[:, 2])
    if len(z_coords) == 0:
        return 0
    layers = 1
    for z1, z2 in zip(z_coords, z_coords[1:]):
        if abs(z2 - z1) > 0.5:
            layers += 1
    return layers


def _estimate_layers(slab: Slab) -> int:
    """Estimate number of distinct atomic layers from pymatgen Slab."""
    z_coords = np.sort([site.coords[2] for site in slab])
    if len(z_coords) == 0:
        return 0
    layers = 1
    for z1, z2 in zip(z_coords, z_coords[1:]):
        if abs(z2 - z1) > 0.5:
            layers += 1
    return layers


def _slab_thickness_ase(atoms: Atoms) -> float:
    """Return slab thickness in Å from atom z-span, excluding vacuum."""
    if len(atoms) == 0:
        return 0.0
    z = atoms.positions[:, 2]
    return float(z.max() - z.min())


def _slab_thickness_pmg(slab: Slab) -> float:
    """Return slab thickness in Å from site z-span, excluding vacuum."""
    if len(slab) == 0:
        return 0.0
    z = np.array([site.coords[2] for site in slab], dtype=float)
    return float(z.max() - z.min())


def _apply_supercell(
    atoms: Atoms,
    na: int,
    nb: int,
) -> Atoms:
    """Tile ASE Atoms na × nb times in the ab plane."""
    if na == 1 and nb == 1:
        return atoms
    return make_2d_supercell(atoms, ((int(na), 0), (0, int(nb))))


def _diagonal_repeat_guess(matrix_2d: tuple[tuple[int, int], tuple[int, int]]) -> tuple[int, int]:
    """Return old na/nb fields for compatibility with existing API/UI."""
    if matrix_2d[0][1] == 0 and matrix_2d[1][0] == 0:
        return max(1, abs(int(matrix_2d[0][0]))), max(1, abs(int(matrix_2d[1][1])))
    det = abs(int(matrix_2d[0][0] * matrix_2d[1][1] - matrix_2d[0][1] * matrix_2d[1][0]))
    return max(1, det), 1


def _diag_supercell_matrix(supercell: tuple[int, int]) -> tuple[tuple[int, int], tuple[int, int]]:
    return ((int(supercell[0]), 0), (0, int(supercell[1])))


def _auto_2d_transform_candidates() -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Return diagonal candidates plus a bounded off-diagonal pool."""
    candidates = {
        _diag_supercell_matrix((na, nb))
        for na in range(1, 9)
        for nb in range(1, 9)
    }
    candidates.update(enumerate_2d_integer_transforms(
        max_area_multiple=16,
        max_element=4,
    ))
    return sorted(
        candidates,
        key=lambda matrix: (
            abs(matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]),
            sum(abs(value) for row in matrix for value in row),
            matrix,
        ),
    )


def _get_supercell_matrix(
    a: float,
    b: float,
    target_size: float = TARGET_LATERAL_SIZE_ANGSTROM,
    tolerance: float = LATERAL_TOLERANCE_ANGSTROM,
) -> tuple[int, int]:
    """Determine (na, nb) supercell repeats to reach target lateral size.

    Args:
        a, b: Lattice vector lengths in Å.
    Returns:
        (na, nb) supercell multipliers.
    """
    best = None
    best_score = float("inf")
    low = target_size - tolerance
    high = target_size + tolerance

    for na in range(1, 8):
        for nb in range(1, 8):
            la = na * a
            lb = nb * b
            if low <= la <= high and low <= lb <= high:
                score = abs(la - lb) + (la + lb) * 0.01
                if score < best_score:
                    best_score = score
                    best = (na, nb)

    if best is None:
        na = max(1, int(np.ceil(low / a)))
        nb = max(1, int(np.ceil(low / b)))
        best = (na, nb)

    return best


def _detect_layers(z_coords: np.ndarray, gap: float = 0.8) -> list[list[int]]:
    """Group atom indices into layers by finding z-gaps > gap Å.

    Compares each atom against the lowest z in the current layer (not the
    last added atom) to avoid chaining artefacts across wide intra-layer ranges.

    Returns a list of layers (bottom-first), each layer being a list of
    atom indices belonging to that layer.
    """
    order = np.argsort(z_coords)
    layers: list[list[int]] = [[int(order[0])]]
    for idx in order[1:]:
        layer_z_min = z_coords[layers[-1][0]]   # min z of current layer
        if z_coords[idx] - layer_z_min > gap:
            layers.append([int(idx)])
        else:
            layers[-1].append(int(idx))
    return layers


DEFAULT_FIX_RATIO = 0.48


def _fix_bottom_by_ratio(
    atoms: Atoms,
    fix_ratio: float,
) -> tuple[Atoms, list[int]]:
    """Fix the bottom ``fix_ratio`` fraction of the slab material via FixAtoms.

    The fraction is measured along the c-axis in fractional coordinates, so it
    stays correct for tilted / non-orthogonal cells where Cartesian z mixes in
    in-plane position. It is taken against the material's own atom span
    (f_min..f_max), not the full cell, so vacuum added along c does not change
    which atoms are fixed — i.e. the ratio is referenced to the pre-vacuum slab.

    Returns:
        (atoms_with_constraint, list_of_fixed_indices)
    """
    if len(atoms) == 0 or fix_ratio <= 0.0:
        atoms.set_constraint()
        return atoms, []

    frac_c = atoms.get_scaled_positions(wrap=False)[:, 2]
    f_min = float(frac_c.min())
    span = float(frac_c.max()) - f_min
    if span <= 0.0:
        atoms.set_constraint()
        return atoms, []

    threshold = f_min + min(float(fix_ratio), 1.0) * span
    fix_indices = [int(i) for i in range(len(atoms)) if frac_c[i] <= threshold]
    atoms.set_constraint(FixAtoms(indices=fix_indices))
    return atoms, fix_indices


def _fix_bottom_layers_ase(
    atoms: Atoms,
    n_fix: int,
) -> tuple[Atoms, list[int]]:
    """Apply FixAtoms constraint to the n_fix bottom layers.

    Uses gap-based layer detection and a midpoint threshold between the
    last fixed layer and the first free layer, so the result is robust
    regardless of interlayer spacing variations.

    Returns:
        (atoms_with_constraint, list_of_fixed_indices)
    """
    if len(atoms) == 0:
        atoms.set_constraint()
        return atoms, []

    if n_fix <= 0:
        atoms.set_constraint()
        return atoms, []

    z = atoms.positions[:, 2]
    layers = _detect_layers(z)

    n_fix = min(int(n_fix), len(layers))

    z_top_fixed = float(np.mean(z[layers[n_fix - 1]]))
    if n_fix < len(layers):
        z_bottom_free = float(np.mean(z[layers[n_fix]]))
        z_thresh = (z_top_fixed + z_bottom_free) / 2.0
    else:
        z_thresh = z_top_fixed + 0.5

    fix_indices = [int(i) for i in range(len(atoms)) if z[i] <= z_thresh]
    atoms.set_constraint(FixAtoms(indices=fix_indices))
    return atoms, fix_indices


def _valid_site_property(structure: Structure, name: str) -> list | None:
    values = structure.site_properties.get(name)
    if values is None or len(values) != len(structure):
        return None
    return list(values)


def _same_site_property_value(left, right) -> bool:
    try:
        return abs(float(left) - float(right)) <= 1e-6
    except (TypeError, ValueError):
        return left == right


def _uniform_site_property_by_species(
    structure: Structure,
    name: str,
) -> dict[str, object] | None:
    values = _valid_site_property(structure, name)
    if values is None:
        return None

    by_species: dict[str, object] = {}
    for site, value in zip(structure, values):
        key = site.species_string
        if key in by_species and not _same_site_property_value(by_species[key], value):
            return None
        by_species[key] = value
    return by_species


def _transfer_site_property_by_nearest(
    source: Structure,
    target: Structure,
    name: str,
    *,
    tolerance: float = 0.25,
) -> Structure:
    """Carry a per-site property through standard/primitive cell transforms.

    pymatgen's symmetry standardization can drop site_properties. For magnetic
    moments, preserve MP-provided values by matching each transformed site back
    to the nearest periodic source site of the same species.
    """
    source_values = _valid_site_property(source, name)
    if source_values is None:
        return target

    uniform_by_species = _uniform_site_property_by_species(source, name)
    if len(target) < len(source) and uniform_by_species is None:
        if _valid_site_property(target, name) is None:
            return target
        updated = target.copy()
        updated.remove_site_property(name)
        return updated

    if _valid_site_property(target, name) is not None:
        return target

    if uniform_by_species is not None and all(
        site.species_string in uniform_by_species for site in target
    ):
        updated = target.copy()
        updated.add_site_property(
            name,
            [uniform_by_species[site.species_string] for site in target],
        )
        return updated

    mapped_values: list = []
    for target_site in target:
        best: tuple[float, int] | None = None
        for neighbor in source.get_sites_in_sphere(
            target_site.coords,
            r=tolerance,
            include_index=True,
        ):
            if neighbor.species != target_site.species:
                continue
            distance = float(getattr(neighbor, "nn_distance", 0.0))
            index = int(getattr(neighbor, "index"))
            if best is None or distance < best[0]:
                best = (distance, index)
        if best is None:
            return target
        mapped_values.append(source_values[best[1]])

    updated = target.copy()
    updated.add_site_property(name, mapped_values)
    return updated


def _preserve_magnetic_moments(source: Structure, target: Structure) -> Structure:
    """Preserve MP magmom site property when available."""
    return _transfer_site_property_by_nearest(source, target, "magmom")


def _uniform_initial_magmoms_by_number(atoms: Atoms) -> dict[int, float] | None:
    if "initial_magmoms" not in atoms.arrays:
        return None
    by_number: dict[int, float] = {}
    for number, magmom in zip(atoms.numbers, atoms.get_initial_magnetic_moments()):
        number = int(number)
        magmom = float(magmom)
        if number in by_number and abs(by_number[number] - magmom) > 1e-6:
            return None
        by_number[number] = magmom
    return by_number


def _apply_uniform_initial_magmoms_by_number(
    atoms: Atoms,
    magmoms_by_number: dict[int, float] | None,
) -> None:
    if not magmoms_by_number:
        return
    if any(int(number) not in magmoms_by_number for number in atoms.numbers):
        return
    atoms.set_initial_magnetic_moments(
        [magmoms_by_number[int(number)] for number in atoms.numbers]
    )


def _make_pmg_slab_from_ase(
    atoms: Atoms,
    miller_index: tuple[int, int, int],
    oriented_unit_cell: Structure,
) -> Slab:
    """Wrap ASE slab atoms as a pymatgen Slab so slab metadata is computable."""
    pmg_structure = ase_to_pymatgen(atoms)
    return Slab(
        lattice=pmg_structure.lattice,
        species=[site.species for site in pmg_structure],
        coords=pmg_structure.frac_coords,
        miller_index=miller_index,
        oriented_unit_cell=oriented_unit_cell,
        shift=0.0,
        scale_factor=np.eye(3, dtype=int),
        reorient_lattice=False,
        to_unit_cell=False,
        site_properties=pmg_structure.site_properties,
    )


def _result_from_ase(
    atoms: Atoms,
    miller_index: tuple[int, int, int],
    n_fix: int,
    backend: str,
    termination: int = 0,
    supercell_na: int = 1,
    supercell_nb: int = 1,
    supercell_matrix: tuple[tuple[int, int], tuple[int, int]] = ((1, 0), (0, 1)),
    oriented_unit_cell: Structure | None = None,
) -> SlabResult:
    """Build a SlabResult from an ASE Atoms object (CatKit path)."""
    atoms, fix_indices = _fix_bottom_layers_ase(atoms, n_fix)

    is_polar = False
    is_symmetric = True
    pmg_slab = None
    try:
        if oriented_unit_cell is not None:
            pmg_slab = _make_pmg_slab_from_ase(atoms, miller_index, oriented_unit_cell)
            is_polar = pmg_slab.is_polar()
            is_symmetric = pmg_slab.is_symmetric()
        else:
            pmg_slab = ase_to_pymatgen(atoms)
    except Exception:
        pass

    cell = atoms.cell
    return SlabResult(
        slab=pmg_slab,
        ase_atoms=atoms,
        miller_index=miller_index,
        n_atoms=len(atoms),
        n_layers=_estimate_layers_ase(atoms),
        termination=termination,
        is_polar=is_polar,
        is_symmetric=is_symmetric,
        fix_indices=fix_indices,
        lateral_a=float(np.linalg.norm(cell[0])),
        lateral_b=float(np.linalg.norm(cell[1])),
        slab_thickness=_slab_thickness_ase(atoms),
        backend=backend,
        supercell_na=supercell_na,
        supercell_nb=supercell_nb,
        supercell_matrix=supercell_matrix,
    )


def _result_from_pmg(
    slab: Slab,
    miller_index: tuple[int, int, int],
    n_fix: int,
    backend: str,
    termination: int = 0,
    target_lateral_size: float = TARGET_LATERAL_SIZE_ANGSTROM,
    lateral_tolerance: float = LATERAL_TOLERANCE_ANGSTROM,
    supercell: tuple[int, int] | None = None,
    supercell_matrix: tuple[tuple[int, int], tuple[int, int]] | None = None,
) -> SlabResult:
    """Build a SlabResult from a pymatgen Slab (pymatgen/surfaxe path)."""
    a = float(np.linalg.norm(slab.lattice.matrix[0]))
    b = float(np.linalg.norm(slab.lattice.matrix[1]))
    if supercell is not None:
        matrix_2d = _diag_supercell_matrix(supercell)
    elif supercell_matrix is not None:
        matrix_2d = tuple(tuple(int(value) for value in row) for row in supercell_matrix)
    else:
        matrix_2d = _diag_supercell_matrix(_get_supercell_matrix(a, b, target_lateral_size, lateral_tolerance))
    na, nb = _diagonal_repeat_guess(matrix_2d)
    if matrix_2d != ((1, 0), (0, 1)):
        slab.make_supercell([
            [matrix_2d[0][0], matrix_2d[0][1], 0],
            [matrix_2d[1][0], matrix_2d[1][1], 0],
            [0, 0, 1],
        ])

    atoms = pymatgen_to_ase(slab)
    atoms.set_pbc([True, True, False])
    atoms, fix_indices = _fix_bottom_layers_ase(atoms, n_fix)

    lat = slab.lattice
    return SlabResult(
        slab=slab,
        ase_atoms=atoms,
        miller_index=miller_index,
        n_atoms=len(atoms),
        n_layers=_estimate_layers(slab),
        termination=termination,
        is_polar=slab.is_polar(),
        is_symmetric=slab.is_symmetric(),
        fix_indices=fix_indices,
        lateral_a=float(np.linalg.norm(lat.matrix[0])),
        lateral_b=float(np.linalg.norm(lat.matrix[1])),
        slab_thickness=_slab_thickness_pmg(slab),
        backend=backend,
        supercell_na=na,
        supercell_nb=nb,
        supercell_matrix=matrix_2d,
    )


# ---------------------------------------------------------------------------
# Auto layer estimation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _TargetSlabChoice:
    n_layers: int
    n_fix: int
    supercell: tuple[int, int]
    supercell_matrix: tuple[tuple[int, int], tuple[int, int]]
    score: float
    estimated_atoms: int
    estimated_lateral_a: float
    estimated_lateral_b: float
    estimated_thickness: float


def _det2(matrix_2d: tuple[tuple[int, int], tuple[int, int]]) -> int:
    return int(matrix_2d[0][0] * matrix_2d[1][1] - matrix_2d[0][1] * matrix_2d[1][0])


def _target_score(
    n_atoms: float,
    lateral_a: float,
    lateral_b: float,
    slab_thickness: float,
    target_n_atoms: int,
    atom_tolerance: int,
    target_lateral_size: float,
    lateral_tolerance: float,
    target_slab_thickness: float,
) -> float:
    """Score a candidate slab against target atom, lateral, and thickness goals."""
    atom_scale = max(float(atom_tolerance), 1.0)
    lateral_scale = max(float(lateral_tolerance), 0.1)
    thickness_scale = max(float(target_slab_thickness) * 0.25, 1.0)

    atom_delta = n_atoms - target_n_atoms
    atom_penalty = abs(atom_delta) / atom_scale
    oversized_atom_penalty = max(0.0, atom_delta) / max(float(target_n_atoms), 1.0)
    lateral_penalty = (
        abs(lateral_a - target_lateral_size)
        + abs(lateral_b - target_lateral_size)
    ) / (2.0 * lateral_scale)
    oversized_lateral_penalty = (
        max(0.0, lateral_a - target_lateral_size)
        + max(0.0, lateral_b - target_lateral_size)
    ) / max(float(target_lateral_size), 1.0)
    thickness_penalty = abs(slab_thickness - target_slab_thickness) / thickness_scale
    oversized_thickness_penalty = max(0.0, slab_thickness - target_slab_thickness) / max(
        float(target_slab_thickness),
        1.0,
    )
    aspect_penalty = abs(lateral_a - lateral_b) / max(target_lateral_size, 1.0)

    return (
        atom_penalty
        + 0.9 * oversized_atom_penalty
        + 1.5 * lateral_penalty
        + 0.75 * oversized_lateral_penalty
        + 1.25 * thickness_penalty
        + 0.75 * oversized_thickness_penalty
        + 0.15 * aspect_penalty
    )


def _square_lateral_score(
    cell_2d: np.ndarray,
    *,
    atom_count: int,
    target_atom_count: int,
    target_lateral_size: float,
    lateral_tolerance: float,
) -> float:
    """Score how close an in-plane cell is to a compact square target.

    This deliberately evaluates the transformed cell itself, not just diagonal
    repeats. A good slab cell should be near-orthogonal, have similar a/b
    lengths, stay near the requested side length and area, and avoid atom-count
    overshoot. None of these are hard constraints because some surfaces cannot
    form a clean square within a small integer transform search.
    """
    metrics = cell_shape_metrics(cell_2d)
    side_a, side_b = metrics.lengths[:2]
    target_side = max(float(target_lateral_size), 1.0)
    target_area = target_side * target_side
    atom_target = max(float(target_atom_count), 1.0)

    angle_penalty = (metrics.inplane_angle_deviation / 15.0) ** 2
    aspect_penalty = abs(np.log(max(metrics.lateral_aspect_ratio, 1e-12))) / np.log(1.25)
    aspect_penalty = aspect_penalty ** 2
    side_penalty = (abs(side_a - target_side) + abs(side_b - target_side)) / (2.0 * target_side)
    area_penalty = abs(metrics.area_ab - target_area) / target_area
    max_side = max(side_a, side_b)
    min_side = min(side_a, side_b)
    max_allowed = target_side + max(float(lateral_tolerance), 0.0)
    min_preferred = max(target_side - max(float(lateral_tolerance), 0.0), target_side * 0.55)
    excess_side_penalty = max(0.0, max_side - max_allowed) / target_side
    undersized_penalty = max(0.0, min_preferred - min_side) / target_side
    atom_delta = float(atom_count) - atom_target
    atom_penalty = abs(atom_delta) / atom_target
    atom_oversize_penalty = max(0.0, atom_delta) / atom_target

    return float(
        3.5 * angle_penalty
        + 2.5 * aspect_penalty
        + 1.0 * side_penalty
        + 0.6 * area_penalty
        + 5.0 * excess_side_penalty
        + 1.0 * undersized_penalty
        + 0.5 * atom_penalty
        + 1.2 * atom_oversize_penalty
    )


def _ideal_copy_multiple(
    base_cell_2d: np.ndarray,
    *,
    base_atom_count: float,
    target_atom_count: int,
    target_lateral_size: float,
) -> float:
    """Estimate the preferred 2D copy determinant from the base cell.

    A square-ish target has area ``target_lateral_size ** 2``. The atom-count
    target gives an independent preferred determinant. Blend both so a material
    with a large primitive surface cell does not get blindly copied to an
    oversized slab just to hit a lateral side length, and a tiny primitive cell
    does not get a huge cell solely to satisfy a square shape score.
    """
    metrics = cell_shape_metrics(base_cell_2d)
    target_side = max(float(target_lateral_size), 1.0)
    by_area = (target_side * target_side) / max(metrics.area_ab, 1e-8)
    by_atoms = float(target_atom_count) / max(float(base_atom_count), 1.0)
    return max(1.0, 0.55 * by_atoms + 0.45 * by_area)


def _copy_multiple_penalty(det: int, ideal_det: float) -> float:
    """Penalty for copy count mismatch, with extra cost for oversizing."""
    det = max(int(det), 1)
    ideal = max(float(ideal_det), 1.0)
    mismatch = abs(np.log(det / ideal))
    oversize = max(0.0, det - ideal) / ideal
    return float(mismatch + 0.8 * oversize)


def _choose_actual_2d_transform(
    base_cell_2d: np.ndarray,
    *,
    base_atom_count: int,
    slab_thickness: float,
    target_n_atoms: int,
    atom_tolerance: int,
    target_lateral_size: float,
    lateral_tolerance: float,
    target_slab_thickness: float,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Choose a 2D transform against the actual backend surface cell.

    The target layer/supercell search estimates a surface cell with pymatgen,
    but CatKit can return the same surface in a different in-plane basis. Score
    non-diagonal transforms on the actual CatKit base cell before applying one;
    otherwise a matrix that is near-orthogonal in the estimator basis can become
    highly oblique in the final POSCAR.
    """
    candidates = _auto_2d_transform_candidates()
    scored: list[tuple[float, tuple[tuple[int, int], tuple[int, int]]]] = []
    ideal_det = _ideal_copy_multiple(
        base_cell_2d,
        base_atom_count=base_atom_count,
        target_atom_count=target_n_atoms,
        target_lateral_size=target_lateral_size,
    )
    for matrix_2d in candidates:
        det = _det2(matrix_2d)
        if det < 1:
            continue
        transformed_cell = transform_2d_cell(base_cell_2d, matrix_2d)
        metrics = cell_shape_metrics(transformed_cell)
        lateral_a, lateral_b = metrics.lengths[:2]
        n_atoms = int(base_atom_count * det)
        score = _target_score(
            n_atoms=n_atoms,
            lateral_a=lateral_a,
            lateral_b=lateral_b,
            slab_thickness=slab_thickness,
            target_n_atoms=target_n_atoms,
            atom_tolerance=atom_tolerance,
            target_lateral_size=target_lateral_size,
            lateral_tolerance=lateral_tolerance,
            target_slab_thickness=target_slab_thickness,
        )
        score += 1.8 * _square_lateral_score(
            transformed_cell,
            atom_count=n_atoms,
            target_atom_count=target_n_atoms,
            target_lateral_size=target_lateral_size,
            lateral_tolerance=lateral_tolerance,
        )
        score += 0.02 * score_2d_cell_shape(
            transformed_cell,
            atom_count=n_atoms,
            target_atom_count=target_n_atoms,
            target_lateral_size=target_lateral_size,
        )
        score += 0.03 * (n_atoms / max(target_n_atoms, 1))
        score += 0.01 * det
        score += 1.4 * _copy_multiple_penalty(det, ideal_det)
        scored.append((float(score), matrix_2d))

    if not scored:
        return ((1, 0), (0, 1))

    return min(scored, key=lambda item: item[0])[1]


def _score_result_against_targets(
    result: SlabResult,
    target_n_atoms: int,
    atom_tolerance: int,
    target_lateral_size: float,
    lateral_tolerance: float,
    target_slab_thickness: float,
) -> float:
    """Score an actual generated slab result against the target geometry."""
    return _target_score(
        n_atoms=result.n_atoms,
        lateral_a=result.lateral_a,
        lateral_b=result.lateral_b,
        slab_thickness=result.slab_thickness,
        target_n_atoms=target_n_atoms,
        atom_tolerance=atom_tolerance,
        target_lateral_size=target_lateral_size,
        lateral_tolerance=lateral_tolerance,
        target_slab_thickness=target_slab_thickness,
    )


def _estimate_surface_cell_metrics(
    bulk_structure: Structure,
    miller_index: tuple[int, int, int],
    standardize_bulk: bool = True,
) -> tuple[np.ndarray, float, float, float, float]:
    """Estimate base surface cell, a/b, atoms per layer, and d-spacing.

    When ``standardize_bulk`` is False, ``miller_index`` is interpreted
    against ``bulk_structure`` exactly as given (no conventional/primitive
    reduction), matching the actual generation backends below.
    """
    if standardize_bulk:
        conv = get_conventional_structure(bulk_structure)
        prim = conv.get_primitive_structure()
    else:
        prim = bulk_structure
    d_hkl = max(float(prim.lattice.d_hkl(miller_index)), 0.5)

    gen = PmgSlabGenerator(
        prim,
        miller_index=miller_index,
        min_slab_size=max(4 * d_hkl, 1.0),
        min_vacuum_size=0,
        in_unit_planes=False,
        primitive=standardize_bulk,
    )
    slabs = gen.get_slabs()
    if not slabs:
        raise RuntimeError(f"Could not estimate surface cell for {miller_index}.")

    slab = slabs[0]
    base_cell_2d = np.array(slab.lattice.matrix[:2], dtype=float)
    a = float(np.linalg.norm(slab.lattice.matrix[0]))
    b = float(np.linalg.norm(slab.lattice.matrix[1]))
    n_layers = max(1, _estimate_layers(slab))
    atoms_per_layer = max(1.0, len(slab) / n_layers)
    if n_layers > 1:
        d_est = max(_slab_thickness_pmg(slab) / (n_layers - 1), 0.5)
    else:
        d_est = d_hkl
    return base_cell_2d, a, b, atoms_per_layer, d_est


def _choose_target_slab_parameters(
    bulk_structure: Structure,
    miller_index: tuple[int, int, int],
    target_n_atoms: int = TARGET_ATOM_COUNT,
    atom_tolerance: int = ATOM_COUNT_TOLERANCE,
    target_lateral_size: float = TARGET_LATERAL_SIZE_ANGSTROM,
    lateral_tolerance: float = LATERAL_TOLERANCE_ANGSTROM,
    target_slab_thickness: float = TARGET_SLAB_THICKNESS_ANGSTROM,
    supercell: tuple[int, int] | None = None,
    n_layers_override: int | None = None,
    standardize_bulk: bool = True,
) -> _TargetSlabChoice:
    """Find layer and supercell parameters closest to the requested slab targets."""
    base_cell_2d, base_a, base_b, atoms_per_layer, d_spacing = _estimate_surface_cell_metrics(
        bulk_structure, miller_index, standardize_bulk=standardize_bulk
    )

    layer_center = max(2, int(round(target_slab_thickness / d_spacing)) + 1)
    max_layers = max(8, layer_center + 10, int(np.ceil((target_slab_thickness + 8.0) / d_spacing)) + 1)
    layer_candidates = [int(n_layers_override)] if n_layers_override is not None else range(2, max_layers + 1)

    if supercell is not None:
        transform_candidates = [_diag_supercell_matrix(supercell)]
    else:
        transform_candidates = _auto_2d_transform_candidates()

    best: _TargetSlabChoice | None = None
    for n_layers in layer_candidates:
        if n_layers < 1:
            continue
        thickness = max(n_layers - 1, 1) * d_spacing
        base_atom_count = atoms_per_layer * n_layers
        ideal_det = _ideal_copy_multiple(
            base_cell_2d,
            base_atom_count=base_atom_count,
            target_atom_count=target_n_atoms,
            target_lateral_size=target_lateral_size,
        )
        for matrix_2d in transform_candidates:
            det = matrix_2d[0][0] * matrix_2d[1][1] - matrix_2d[0][1] * matrix_2d[1][0]
            if det < 1:
                continue
            transformed_cell = transform_2d_cell(base_cell_2d, matrix_2d)
            lateral_a = float(np.linalg.norm(transformed_cell[0]))
            lateral_b = float(np.linalg.norm(transformed_cell[1]))
            n_atoms = int(round(atoms_per_layer * n_layers * det))
            score = _target_score(
                n_atoms=n_atoms,
                lateral_a=lateral_a,
                lateral_b=lateral_b,
                slab_thickness=thickness,
                target_n_atoms=target_n_atoms,
                atom_tolerance=atom_tolerance,
                target_lateral_size=target_lateral_size,
                lateral_tolerance=lateral_tolerance,
                target_slab_thickness=target_slab_thickness,
            )
            score += 1.2 * _square_lateral_score(
                transformed_cell,
                atom_count=n_atoms,
                target_atom_count=target_n_atoms,
                target_lateral_size=target_lateral_size,
                lateral_tolerance=lateral_tolerance,
            )
            score += 0.05 * score_2d_cell_shape(
                transformed_cell,
                atom_count=n_atoms,
                target_atom_count=target_n_atoms,
                target_lateral_size=target_lateral_size,
            )
            # Tie-break toward compact DFT-ready cells when scores are close.
            score += 0.02 * (n_atoms / max(target_n_atoms, 1))
            score += 0.01 * ((lateral_a + lateral_b) / max(2.0 * target_lateral_size, 1.0))
            score += 1.0 * _copy_multiple_penalty(det, ideal_det)
            na, nb = _diagonal_repeat_guess(matrix_2d)
            choice = _TargetSlabChoice(
                n_layers=n_layers,
                n_fix=max(1, round(n_layers / 3)),
                supercell=(na, nb),
                supercell_matrix=matrix_2d,
                score=score,
                estimated_atoms=n_atoms,
                estimated_lateral_a=lateral_a,
                estimated_lateral_b=lateral_b,
                estimated_thickness=thickness,
            )
            if best is None or choice.score < best.score:
                best = choice

    if best is None:
        raise RuntimeError("Could not find a valid target slab parameter set.")
    return best


def _estimate_interlayer_spacing(
    bulk_structure: Structure,
    miller_index: tuple[int, int, int],
) -> float:
    """Return the plane-to-plane d-spacing (Å) for the given Miller index.

    Generates a thin 5-layer slab and measures the mean spacing between
    adjacent distinct z-planes. This is more accurate than using the
    oriented unit cell c-vector, which may contain multiple planes per
    repeat unit (e.g. Pt(111): c=3.94Å but plane spacing=1.97Å).
    """
    conv = get_conventional_structure(bulk_structure)
    try:
        gen = PmgSlabGenerator(
            conv,
            miller_index=miller_index,
            min_slab_size=5,
            min_vacuum_size=8,
            in_unit_planes=True,
            primitive=True,
        )
        slabs = gen.get_slabs()
        if slabs:
            z_coords = np.sort([site.coords[2] for site in slabs[0]])
            planes: list[float] = [float(z_coords[0])]
            for z in z_coords[1:]:
                if abs(z - planes[-1]) > 0.3:
                    planes.append(float(z))
            if len(planes) >= 2:
                return float(np.mean(np.diff(planes)))
    except Exception:
        pass

    # Fallback: use oriented unit cell c-vector (may overestimate for some surfaces)
    gen_fb = PmgSlabGenerator(
        conv,
        miller_index=miller_index,
        min_slab_size=1,
        min_vacuum_size=0,
        in_unit_planes=True,
        primitive=False,
    )
    return float(gen_fb.oriented_unit_cell.lattice.c)


def _min_slab_thickness_from_layers(
    bulk_structure: Structure,
    miller_index: tuple[int, int, int],
    n_layers: int,
) -> float:
    """Approximate a layer-count request as a minimum slab thickness in Å."""
    spacing = _estimate_interlayer_spacing(bulk_structure, miller_index)
    return max(float(max(n_layers - 1, 1)) * spacing, spacing)


def _auto_n_layers_and_fix(
    bulk_structure: Structure,
    miller_index: tuple[int, int, int],
    target_thickness: float = TARGET_SLAB_THICKNESS_ANGSTROM,
    target_atoms: int = TARGET_ATOM_COUNT,
    target_lateral: float = TARGET_LATERAL_SIZE_ANGSTROM,
    lateral_tolerance: float = LATERAL_TOLERANCE_ANGSTROM,
) -> tuple[int, int]:
    """Backward-compatible wrapper around target-based slab parameter search."""
    choice = _choose_target_slab_parameters(
        bulk_structure=bulk_structure,
        miller_index=miller_index,
        target_n_atoms=target_atoms,
        target_lateral_size=target_lateral,
        lateral_tolerance=lateral_tolerance,
        target_slab_thickness=target_thickness,
    )
    return choice.n_layers, choice.n_fix


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------

def _generate_via_catkit(
    bulk_structure: Structure,
    miller_index: tuple[int, int, int],
    n_layers: int,
    n_fix: int,
    vacuum: float,
    target_lateral_size: float,
    lateral_tolerance: float,
    target_n_atoms: int,
    atom_tolerance: int,
    target_slab_thickness: float,
    layer_type: str = "trim",
    supercell: tuple[int, int] | None = None,
    supercell_matrix: tuple[tuple[int, int], tuple[int, int]] | None = None,
    standardize_bulk: bool = True,
) -> list[SlabResult]:
    """Generate slabs using CatKit SlabGenerator.

    CatKit advantages over pymatgen for this task:
    - Automatically identifies and tags surface atoms (top/bottom) via Voronoi.
    - Directly returns ASE Atoms (Gratoms) — no conversion needed.
    - layer_type='trim' makes the public n_layers argument mean atomic layers.
    - Use surfaxe or pymatgen symmetrization when symmetric oxide slabs matter.
    - Attaches bond graph to Gratoms for downstream CatKit adsorption tools.

    ``standardize_bulk=False`` skips conventional/primitive reduction (both
    ours and CatKit's own) and uses ``bulk_structure`` exactly as given —
    ``miller_index`` is then interpreted against that exact lattice. Use this
    only when the supplied cell encodes site-level physics (e.g.
    antiferromagnetic ordering, dopant/defect placement) that reduction could
    silently collapse.
    """
    from catkit.gen.surface import SlabGenerator as CatKitSlabGen

    # CatKit works with ASE Atoms — convert pymatgen Structure
    if standardize_bulk:
        conv_struct = _preserve_magnetic_moments(
            bulk_structure,
            get_conventional_structure(bulk_structure),
        )
    else:
        conv_struct = bulk_structure
    ase_bulk = pymatgen_to_ase(conv_struct)
    uniform_magmoms_by_number = _uniform_initial_magmoms_by_number(ase_bulk)

    gen = CatKitSlabGen(
        bulk=ase_bulk,
        miller_index=list(miller_index),
        layers=n_layers,
        vacuum=vacuum / 2,   # CatKit adds vacuum to each side; our API uses total vacuum
        fixed=n_fix,
        layer_type=layer_type,
        attach_graph=True,
        standardize_bulk=standardize_bulk,
    )

    terminations = gen.get_unique_terminations()
    results: list[SlabResult] = []

    for iterm, _ in enumerate(terminations):
        slab_gratoms = gen.get_slab(iterm=iterm)

        # Convert to plain ASE Atoms immediately (drop Gratoms graph)
        atoms = Atoms(
            numbers=slab_gratoms.numbers,
            positions=slab_gratoms.positions,
            cell=slab_gratoms.cell,
            pbc=slab_gratoms.pbc,
        )
        if "initial_magmoms" in slab_gratoms.arrays:
            atoms.set_initial_magnetic_moments(
                slab_gratoms.get_initial_magnetic_moments()
            )
        _apply_uniform_initial_magmoms_by_number(atoms, uniform_magmoms_by_number)

        if supercell is not None:
            matrix_2d = _diag_supercell_matrix(supercell)
        else:
            matrix_2d = _choose_actual_2d_transform(
                np.array(atoms.cell[:2], dtype=float),
                base_atom_count=len(atoms),
                slab_thickness=_slab_thickness_ase(atoms),
                target_n_atoms=target_n_atoms,
                atom_tolerance=atom_tolerance,
                target_lateral_size=target_lateral_size,
                lateral_tolerance=lateral_tolerance,
                target_slab_thickness=target_slab_thickness,
            )
        na, nb = _diagonal_repeat_guess(matrix_2d)

        # Use ASE make_supercell instead of CatKit set_size to avoid
        # layer-count artefacts from non-orthogonal cell tiling.
        if matrix_2d != ((1, 0), (0, 1)):
            atoms = make_2d_supercell(atoms, matrix_2d)

        result = _result_from_ase(
            atoms=atoms,
            miller_index=miller_index,
            n_fix=n_fix,
            backend="catkit",
            termination=iterm,
            supercell_na=na,
            supercell_nb=nb,
            supercell_matrix=matrix_2d,
            oriented_unit_cell=conv_struct,
        )
        results.append(result)

    return results


def _generate_via_pymatgen(
    bulk_structure: Structure,
    miller_index: tuple[int, int, int],
    n_layers: int,
    n_fix: int,
    vacuum: float,
    target_lateral_size: float,
    lateral_tolerance: float,
    symmetrize: bool = False,
    supercell: tuple[int, int] | None = None,
    supercell_matrix: tuple[tuple[int, int], tuple[int, int]] | None = None,
    standardize_bulk: bool = True,
) -> list[SlabResult]:
    """Generate slabs using pymatgen SlabGenerator.

    ``standardize_bulk=False`` skips the conventional/primitive reduction
    below and slices ``bulk_structure`` exactly as given (``miller_index`` is
    then interpreted against that exact lattice, and pymatgen's own
    slab-level ``primitive`` reduction is also disabled so the result is not
    silently shrunk back down after slicing).
    """
    # Use primitive cell so the surface unit cell matches CatKit's starting cell.
    # CatKit internally standardizes to the primitive bulk (standardize_bulk=True),
    # while pymatgen with conventional cell produces a 2× larger surface unit cell.
    if standardize_bulk:
        conv_struct = _preserve_magnetic_moments(
            bulk_structure,
            get_conventional_structure(bulk_structure),
        )
        prim_struct = _preserve_magnetic_moments(
            conv_struct,
            conv_struct.get_primitive_structure(),
        )
    else:
        prim_struct = bulk_structure

    # Use in_unit_planes=False so both min_slab_size and min_vacuum_size are in Å.
    # n_layers (plane count) → Å via d-spacing; vacuum is passed directly in Å.
    # This gives consistent vacuum with catkit (ASE center adds v on each side)
    # and surfaxe (also uses in_unit_planes=False internally).
    d_hkl = prim_struct.lattice.d_hkl(miller_index)
    min_slab_size_ang = max(n_layers * d_hkl, 1.0)

    gen = PmgSlabGenerator(
        prim_struct,
        miller_index=miller_index,
        min_slab_size=min_slab_size_ang,
        min_vacuum_size=vacuum,  # total vacuum in Å; center_slab=True splits 50/50
        in_unit_planes=False,
        lll_reduce=True,
        center_slab=True,
        primitive=standardize_bulk,  # start from minimal cell, then supercell to target size
    )

    slabs = gen.get_slabs(symmetrize=symmetrize, repair=symmetrize)
    if not slabs:
        raise RuntimeError(
            f"pymatgen generated no slabs for {prim_struct.formula} {miller_index}."
        )

    if symmetrize:
        filtered = [s for s in slabs if not s.is_polar() and s.is_symmetric()]
        if filtered:
            slabs = filtered
        else:
            warnings.warn(
                f"No symmetric, non-polar slabs found for {prim_struct.formula} "
                f"{miller_index}. Returning all {len(slabs)} candidates.",
                stacklevel=3,
            )

    results = []
    for term_idx, slab in enumerate(slabs):
        results.append(_result_from_pmg(
            slab=slab,
            miller_index=miller_index,
            n_fix=n_fix,
            backend="pymatgen",
            termination=term_idx,
            target_lateral_size=target_lateral_size,
            lateral_tolerance=lateral_tolerance,
            supercell=supercell,
            supercell_matrix=supercell_matrix,
        ))
    return results


def _generate_via_surfaxe(
    bulk_structure: Structure,
    miller_index: tuple[int, int, int],
    n_layers: int,
    n_fix: int,
    vacuum: float,
    target_lateral_size: float,
    lateral_tolerance: float,
    supercell: tuple[int, int] | None = None,
    supercell_matrix: tuple[tuple[int, int], tuple[int, int]] | None = None,
    standardize_bulk: bool = True,
) -> list[SlabResult]:
    """Generate slabs using surfaxe (oxide/nitride preferred).

    surfaxe.generate_slabs returns None by default (saves to disk).
    Must pass save_slabs=False to get a list of dicts back.
    Each dict has key 'slab' (pymatgen Slab) and metadata fields.
    The public API's n_layers is converted to surfaxe's Å-based thicknesses
    argument before calling surfaxe.

    ``standardize_bulk=False`` skips conventional/primitive reduction and
    slices ``bulk_structure`` exactly as given; ``miller_index`` is then
    interpreted against that exact lattice.
    """
    from surfaxe.generation import generate_slabs as sx_generate

    if standardize_bulk:
        conv_struct = _preserve_magnetic_moments(
            bulk_structure,
            get_conventional_structure(bulk_structure),
        )
        prim_struct = _preserve_magnetic_moments(
            conv_struct,
            conv_struct.get_primitive_structure(),
        )
    else:
        prim_struct = bulk_structure
    min_slab_thickness = _min_slab_thickness_from_layers(
        bulk_structure, miller_index, n_layers
    )

    try:
        sx_results = sx_generate(
            structure=prim_struct,
            hkl=[tuple(miller_index)],
            thicknesses=[min_slab_thickness],
            vacuums=[vacuum],
            center_slab=True,
            is_symmetric=True,
            save_slabs=False,     # REQUIRED: return list instead of writing files
            save_metadata=False,
            parallelise=False,
        )
    except ValueError as e:
        # surfaxe raises ValueError when no zero-dipole slabs found
        raise RuntimeError(str(e))

    # sx_results is None when save_slabs=True (default), list of dicts when False
    if not sx_results:
        raise RuntimeError(f"surfaxe returned no slabs for {prim_struct.formula} {miller_index}.")

    raw_slabs: list[Slab] = []
    for r in sx_results:
        if isinstance(r, dict) and "slab" in r:
            raw_slabs.append(r["slab"])
        elif hasattr(r, "lattice"):
            raw_slabs.append(r)

    if not raw_slabs:
        raise RuntimeError(f"surfaxe returned no valid slabs for {prim_struct.formula} {miller_index}.")

    results = []
    for term_idx, slab in enumerate(raw_slabs):
        results.append(_result_from_pmg(
            slab=slab,
            miller_index=miller_index,
            n_fix=n_fix,
            backend="surfaxe",
            termination=term_idx,
            target_lateral_size=target_lateral_size,
            lateral_tolerance=lateral_tolerance,
            supercell=supercell,
            supercell_matrix=supercell_matrix,
        ))
    return results


# ---------------------------------------------------------------------------
# Unified public API
# ---------------------------------------------------------------------------


def generate_slab(
    bulk_structure: Structure,
    miller_index: tuple[int, int, int],
    vacuum: float = DEFAULT_VACUUM_ANGSTROM,
    target_lateral_size: float = TARGET_LATERAL_SIZE_ANGSTROM,
    lateral_tolerance: float = LATERAL_TOLERANCE_ANGSTROM,
    target_slab_thickness: float = TARGET_SLAB_THICKNESS_ANGSTROM,
    target_n_atoms: int = TARGET_ATOM_COUNT,
    atom_tolerance: int = ATOM_COUNT_TOLERANCE,
    fix_layers: int | None = None,
    fix_ratio: float | None = None,
    backend: Backend | None = None,
    prefer_symmetry: bool = False,
    supercell: tuple[int, int] | None = None,
    n_layers_override: int | None = None,
    catkit_layer_type: str = "trim",
    standardize_bulk: bool = True,
) -> list[SlabResult]:
    """Generate slab structures from a bulk structure.

    The unified API is target-based. It searches candidate layer counts and
    lateral supercells, then picks the combination closest to:
        - atom count       ≈ ``target_n_atoms`` (default 70, tolerance 40)
        - lateral a and b  ≈ ``target_lateral_size`` Å (default 7.5 Å; 2 Å soft scale)
        - slab thickness   ≈ ``target_slab_thickness`` Å (default 8 Å, vacuum excluded)

    When ``backend`` is omitted, the backend is chosen from composition:
    oxide/nitride-like structures use surfaxe, everything else uses catkit.
    Use ``backend`` to override the generator.

    Args:
        bulk_structure:        pymatgen Structure of the bulk material.
        miller_index:          Surface Miller index, e.g. (1, 1, 1).
        vacuum:                Total vacuum thickness in Å (default 15 Å).
        target_lateral_size:   Target lateral cell size in Å (default 7.5 Å).
        lateral_tolerance:     Lateral penalty scale in Å, not a hard bound (default 2 Å).
        target_slab_thickness: Target slab thickness excluding vacuum (default 8 Å).
        target_n_atoms:        Target total atom count for auto mode (default 70).
        atom_tolerance:        Atom-count deviation scale (default ±40 atoms).
        fix_layers:            Fix an explicit number of bottom atomic layers.
                               When given it takes precedence over fix_ratio and
                               selects the layer-count fixing mode.
        fix_ratio:             Fraction (0..1) of the slab's material thickness to
                               fix from the bottom, measured in c-axis fractional
                               coordinates (tilt-safe, vacuum-independent). This is
                               the default fixing mode; None uses DEFAULT_FIX_RATIO
                               (0.48). Ignored when fix_layers is given.
        backend:               Override backend: 'catkit' | 'pymatgen' | 'surfaxe'.
                               None auto-selects surfaxe for oxide/nitride-like
                               compositions and catkit otherwise.
        prefer_symmetry:       When backend is None, prefer pymatgen's symmetry
                               and polar filtering path.
        catkit_layer_type:     CatKit layer mode. Use 'stoich' for stoichiometric
                               slabs and 'trim' when intentionally enumerating
                               non-stoichiometric terminations.
        standardize_bulk:      When True (default), reduce ``bulk_structure`` to
                               its conventional/primitive form before slicing —
                               this is a pure symmetry-and-species analysis
                               (spglib) that ignores per-site properties such as
                               magmom. Set False to slice ``bulk_structure``
                               exactly as given, with ``miller_index``
                               interpreted against that exact lattice instead of
                               a re-derived standard cell. Use False when the
                               supplied cell encodes site-level physics that
                               reduction could silently collapse or misassign —
                               e.g. antiferromagnetic ordering (alternating
                               magmom on otherwise-equivalent sites), a dopant
                               supercell, or a defect cell — since spglib cannot
                               tell those sites apart from a plain reduction.

    Returns:
        List of SlabResult objects, one per unique termination.
    """
    if standardize_bulk:
        magmoms = _valid_site_property(bulk_structure, "magmom")
        if magmoms is not None and _uniform_site_property_by_species(bulk_structure, "magmom") is None:
            warnings.warn(
                "bulk_structure has per-site magmom values that differ within "
                "the same species (e.g. antiferromagnetic ordering). The "
                "default standardize_bulk=True reduction only considers "
                "geometry and species, not magmom, and can silently collapse "
                "or misassign this ordering. Pass standardize_bulk=False to "
                "slice the supplied cell exactly as given if this pattern "
                "must be preserved.",
                stacklevel=2,
            )

    choice = _choose_target_slab_parameters(
        bulk_structure=bulk_structure,
        miller_index=miller_index,
        target_n_atoms=target_n_atoms,
        atom_tolerance=atom_tolerance,
        target_lateral_size=target_lateral_size,
        lateral_tolerance=lateral_tolerance,
        target_slab_thickness=target_slab_thickness,
        supercell=supercell,
        n_layers_override=n_layers_override,
        standardize_bulk=standardize_bulk,
    )
    n_fix = fix_layers if fix_layers is not None else choice.n_fix
    if fix_layers is not None and fix_ratio is not None:
        warnings.warn(
            "Both fix_layers and fix_ratio given; fix_layers takes precedence "
            "and fix_ratio is ignored.",
            stacklevel=2,
        )
    # Ratio-based fixing is the default. fix_layers (explicit) switches back to
    # layer-count mode and leaves the backend's constraint untouched.
    effective_fix_ratio = (
        None
        if fix_layers is not None
        else (fix_ratio if fix_ratio is not None else DEFAULT_FIX_RATIO)
    )
    resolved_backend = choose_backend_for_structure(
        bulk_structure,
        explicit_backend=backend,
        prefer_symmetry=prefer_symmetry,
    )
    backend_n_layers = choice.n_layers
    if (
        resolved_backend == "catkit"
        and n_layers_override is None
        and catkit_layer_type == "stoich"
    ):
        # CatKit's stoichiometric trimming can return one fewer useful atomic
        # layer than the target estimator predicts. Start one layer higher so
        # compact default slabs do not briefly pass through a too-thin geometry.
        backend_n_layers += 1
        if fix_layers is None:
            n_fix = max(1, round(backend_n_layers / 3))

    kw = dict(
        bulk_structure=bulk_structure,
        miller_index=miller_index,
        n_layers=backend_n_layers,
        n_fix=n_fix,
        vacuum=vacuum,
        target_lateral_size=target_lateral_size,
        lateral_tolerance=lateral_tolerance,
        supercell=supercell,
        supercell_matrix=choice.supercell_matrix,
        standardize_bulk=standardize_bulk,
    )

    def _run_backend(params: dict) -> list[SlabResult]:
        if resolved_backend == "catkit":
            try:
                return _generate_via_catkit(
                    **params,
                    target_n_atoms=target_n_atoms,
                    atom_tolerance=atom_tolerance,
                    target_slab_thickness=target_slab_thickness,
                    layer_type=catkit_layer_type,
                )
            except Exception as exc:
                warnings.warn(
                    f"CatKit SlabGenerator failed: {exc}. Falling back to pymatgen.",
                    stacklevel=2,
                )
                return _generate_via_pymatgen(**params)
        if resolved_backend == "pymatgen":
            return _generate_via_pymatgen(**params)
        if resolved_backend == "surfaxe":
            try:
                return _generate_via_surfaxe(**params)
            except Exception as exc:
                warnings.warn(
                    f"surfaxe failed for {miller_index}: {exc}. Falling back to pymatgen.",
                    stacklevel=2,
                )
                return _generate_via_pymatgen(**params, symmetrize=True)
        raise ValueError(f"Unknown backend {resolved_backend!r}. Use 'catkit', 'pymatgen', or 'surfaxe'.")

    def _best_score(results: list[SlabResult]) -> float:
        return min(
            _score_result_against_targets(
                r,
                target_n_atoms=target_n_atoms,
                atom_tolerance=atom_tolerance,
                target_lateral_size=target_lateral_size,
                lateral_tolerance=lateral_tolerance,
                target_slab_thickness=target_slab_thickness,
            )
            for r in results
        )

    def _best_thickness_result(results: list[SlabResult]) -> SlabResult:
        return min(results, key=lambda r: abs(r.slab_thickness - target_slab_thickness))

    def _thickness_retry_quality(results: list[SlabResult]) -> tuple[float, float, float]:
        """Rank retry candidates, prioritizing physically useful slab thickness."""
        best_result = _best_thickness_result(results)
        tolerance = max(1.5, target_slab_thickness * 0.25)
        min_auto_layers = 4 if target_slab_thickness >= 4.0 else 2
        thin_deficit = max(0.0, target_slab_thickness - tolerance - best_result.slab_thickness)
        layer_deficit = max(0, min_auto_layers - int(best_result.n_layers))
        underbuilt_penalty = (thin_deficit / tolerance) + float(layer_deficit)
        thickness_error = abs(best_result.slab_thickness - target_slab_thickness) / tolerance
        return (
            underbuilt_penalty,
            thickness_error,
            _best_score(results),
        )

    results = _run_backend(kw)

    # CatKit can start from a compact surface cell, which is desirable, but its
    # effective z-layer spacing can differ from the estimator. If the generated
    # slab is too thin/thick, rescale only n_layers. CatKit retries rescore the
    # a/b transform against the actual regenerated surface cell.
    if n_layers_override is None and results:
        best = _best_thickness_result(results)
        if best.slab_thickness > 0:
            thickness_error = abs(best.slab_thickness - target_slab_thickness)
            tolerance = max(1.5, target_slab_thickness * 0.25)
            if thickness_error > tolerance:
                current_quality = _thickness_retry_quality(results)
                base_layers = int(kw["n_layers"])
                scale = target_slab_thickness / max(best.slab_thickness, 0.1)
                scaled_layers = max(2, int(round(base_layers * scale)))
                if best.slab_thickness < target_slab_thickness:
                    trial_layers = {
                        *range(base_layers + 1, min(60, base_layers + 8) + 1),
                        scaled_layers - 1,
                        scaled_layers,
                        scaled_layers + 1,
                    }
                else:
                    trial_layers = {
                        *range(max(2, base_layers - 8), base_layers),
                        scaled_layers - 1,
                        scaled_layers,
                        scaled_layers + 1,
                    }
                trial_layers = sorted(
                    {
                        max(2, min(60, int(n_layers)))
                        for n_layers in trial_layers
                        if int(n_layers) != base_layers
                    },
                    key=lambda n_layers: (
                        abs(n_layers - base_layers),
                        abs(n_layers - scaled_layers),
                    ),
                )
                for next_layers in trial_layers:
                    params = dict(kw)
                    params["n_layers"] = next_layers
                    if fix_layers is None:
                        params["n_fix"] = max(1, round(next_layers / 3))
                    candidate = _run_backend(params)
                    candidate_best = _best_thickness_result(candidate)
                    candidate_quality = _thickness_retry_quality(candidate)
                    if candidate_quality < current_quality:
                        results = candidate
                        current_quality = candidate_quality
                        best = candidate_best
                    if abs(best.slab_thickness - target_slab_thickness) <= tolerance:
                        break

    # Default (ratio) fixing mode: override the backend's layer-count constraint
    # with a c-axis fractional ratio of the material thickness. Applied once here
    # so it holds across all backends and the adaptive thickness retry above.
    if effective_fix_ratio is not None:
        for r in results:
            _, r.fix_indices = _fix_bottom_by_ratio(r.ase_atoms, effective_fix_ratio)

    return results
