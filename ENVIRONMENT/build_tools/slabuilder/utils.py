"""Common conversion and export utilities used by the skill scripts."""

from __future__ import annotations

from pathlib import Path

from ase import Atoms
from pymatgen.core import Structure
from pymatgen.io.ase import AseAtomsAdaptor
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer


# ---------------------------------------------------------------------------
# pymatgen ↔ ASE conversion
# ---------------------------------------------------------------------------

def pymatgen_to_ase(structure: Structure) -> Atoms:
    """Convert a pymatgen Structure (or Slab) to an ASE Atoms object.

    Uses pymatgen's AseAtomsAdaptor, which is the maintained, recommended
    bridge (replaces mpinterfaces.utils.get_ase_slab).
    """
    return AseAtomsAdaptor.get_atoms(structure)


def ase_to_pymatgen(atoms: Atoms) -> Structure:
    """Convert an ASE Atoms object to a pymatgen Structure."""
    return AseAtomsAdaptor.get_structure(atoms)


# ---------------------------------------------------------------------------
# Crystal structure helpers
# ---------------------------------------------------------------------------

def get_conventional_structure(structure: Structure) -> Structure:
    """Return the conventional standard structure.

    Always use the conventional cell (not primitive) for surface generation
    to ensure correct layer counting and termination handling, especially
    for oxides and nitrides.
    """
    analyzer = SpacegroupAnalyzer(structure)
    return analyzer.get_conventional_standard_structure()


def get_space_group(structure: Structure) -> tuple[int, str]:
    """Return (space_group_number, space_group_symbol) of a structure."""
    analyzer = SpacegroupAnalyzer(structure)
    return analyzer.get_space_group_number(), analyzer.get_space_group_symbol()


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

_FORMAT_EXTENSIONS = {
    "poscar": ".vasp",
    "vasp": ".vasp",
    "extxyz": ".extxyz",
    "xyz": ".xyz",
}


def stable_element_group_order(symbols: list[str]) -> list[int]:
    """Return indices grouped by element while preserving first-seen order."""
    groups: dict[str, list[int]] = {}
    for index, symbol in enumerate(symbols):
        groups.setdefault(symbol, []).append(index)
    return [index for group in groups.values() for index in group]


def prepare_vasp_export_atoms(atoms: Atoms) -> Atoms:
    """Return a VASP-export copy with atoms grouped by element.

    The canonical in-memory structure order is intentionally left untouched.
    ASE slicing applies the same permutation to per-atom arrays such as tags
    and initial_magmoms, and remaps FixAtoms indices on the copied object.
    """
    order = stable_element_group_order(atoms.get_chemical_symbols())
    return atoms[order]


def _species_counts(symbols: list[str]) -> tuple[list[str], list[int]]:
    species: list[str] = []
    counts: list[int] = []
    for symbol in symbols:
        if species and species[-1] == symbol:
            counts[-1] += 1
        else:
            species.append(symbol)
            counts.append(1)
    return species, counts


def _format_magmom(value: float) -> str:
    value = float(value)
    if abs(value) < 1e-12:
        value = 0.0
    return f"{value:g}"


def vasp_export_metadata(atoms: Atoms) -> dict:
    """Return minimal sidecar metadata for the POSCAR export."""
    poscar_index_to_extxyz_index = [
        int(index)
        for index in stable_element_group_order(atoms.get_chemical_symbols())
    ]
    extxyz_index_to_poscar_index = [0] * len(poscar_index_to_extxyz_index)
    for poscar_index, extxyz_index in enumerate(poscar_index_to_extxyz_index):
        extxyz_index_to_poscar_index[extxyz_index] = poscar_index

    export_atoms = prepare_vasp_export_atoms(atoms)

    species, counts = _species_counts(export_atoms.get_chemical_symbols())
    metadata: dict = {
        "species": species,
        "counts": [int(count) for count in counts],
        "poscar_order_matches_extxyz": poscar_index_to_extxyz_index == list(range(len(atoms))),
    }
    if not metadata["poscar_order_matches_extxyz"]:
        metadata["poscar_index_to_extxyz_index"] = poscar_index_to_extxyz_index
        metadata["extxyz_index_to_poscar_index"] = [
            int(index)
            for index in extxyz_index_to_poscar_index
        ]

    if "initial_magmoms" in export_atoms.arrays:
        magmoms = [float(value) for value in export_atoms.get_initial_magnetic_moments()]
        metadata["initial_magmoms"] = magmoms
        metadata["incar_magmom"] = "MAGMOM = " + " ".join(_format_magmom(value) for value in magmoms)

    return metadata


def save_structure(
    atoms: Atoms,
    path: str | Path,
    fmt: str = "poscar",
) -> Path:
    """Save an ASE structure as POSCAR/VASP or extxyz."""
    path = Path(path)
    fmt = fmt.lower()
    ext = _FORMAT_EXTENSIONS.get(fmt)
    if ext and path.suffix != ext:
        path = path.with_suffix(ext)
    path.parent.mkdir(parents=True, exist_ok=True)

    if fmt in ("poscar", "vasp"):
        from pymatgen.io.vasp import Poscar
        poscar = Poscar(ase_to_pymatgen(prepare_vasp_export_atoms(atoms)))
        poscar.write_file(str(path))

    elif fmt in ("extxyz", "xyz"):
        from ase.io import write
        write(str(path), atoms, format="extxyz")

    else:
        raise ValueError(f"Unsupported format: {fmt!r}. Use 'poscar' or 'extxyz'.")

    return path.resolve()
