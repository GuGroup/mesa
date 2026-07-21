#!/usr/bin/env python3
# noqa: SIZE_OK
from __future__ import annotations

import argparse
import contextlib
from collections import Counter
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

import numpy as np
from ase import Atoms


DEFAULT_CELL_SIZE: tuple[float, float, float] = (20.0, 20.0, 21.0)


def json_default(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return str(value)


def safe_name(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text.strip())
    return text.strip("_") or "gas_molecule"


def resolve_spin_multiplicity(override: int | None) -> dict[str, Any]:
    """Resolve the gas-phase spin multiplicity and calculation hints.

    Defaults to a closed-shell singlet (multiplicity 1). Open-shell references
    (e.g. O2, NO, radicals) are the caller's responsibility via
    ``--spin-multiplicity``; the formula is not used to guess a multiplicity."""
    if override is not None:
        if override < 1:
            raise ValueError("--spin-multiplicity must be >= 1")  # noqa: GENERIC_ERR_OK
        multiplicity = int(override)
        source = "override"
    else:
        multiplicity = 1
        source = "default_singlet"
    n_unpaired = multiplicity - 1
    return {
        "spin_multiplicity": multiplicity,
        "spin_multiplicity_source": source,
        "n_unpaired_electrons": n_unpaired,
        "recommended_ispin": 2 if n_unpaired > 0 else 1,
        # NUPDOWN locks the multiplicity for an isolated molecule; total initial
        # moment equals the number of unpaired electrons.
        "recommended_nupdown": n_unpaired,
        "recommended_total_magmom": float(n_unpaired),
        "note": (
            "Open-shell reference: request spin-polarized setup and use spin_reference for the initial moment."
            if n_unpaired > 0
            else "Closed-shell singlet: ispin 1 is appropriate."
        ),
    }


def dipole_hint(atoms: Atoms) -> dict[str, Any]:
    """Heuristic flag for a net molecular dipole in a periodic box.

    A single atom and a homonuclear diatomic have no dipole; anything else may,
    so we advise checking dipole correction (over-recommending is harmless — a
    correction on a truly nonpolar molecule is a no-op)."""
    symbols = atoms.get_chemical_symbols()
    n = len(symbols)
    homonuclear_diatomic = n == 2 and symbols[0] == symbols[1]
    likely_polar = not (n <= 1 or homonuclear_diatomic)
    return {
        "likely_polar": likely_polar,
        "heuristic": "false for single atom and homonuclear diatomic; true otherwise",
        "recommended": (
            "Net dipole possible: consider a dipole-correction setting in downstream calculation setup."
            if likely_polar
            else "No dipole correction needed (single atom or homonuclear diatomic)."
        ),
    }


def composition_counts(atoms: Atoms) -> dict[str, int]:
    return dict(sorted(Counter(atoms.get_chemical_symbols()).items()))


def cell_lengths(atoms: Atoms) -> list[float]:
    return [float(x) for x in atoms.cell.lengths()]


def center_in_cell(atoms: Atoms, cell_size: tuple[float, float, float]) -> Atoms:
    if any(length <= 0 for length in cell_size):
        raise ValueError("--cell-size lengths must be positive.")  # noqa: GENERIC_ERR_OK
    result = atoms.copy()
    result.set_constraint()
    result.set_cell(list(cell_size))
    result.set_pbc([True, True, True])
    result.center()
    return result


def validate_gas_molecule(
    atoms: Atoms,
    *,
    min_distance: float,
    max_atoms: int,
    cell_size: tuple[float, float, float],
) -> dict[str, Any]:
    from slabuilder.structure_checks import check_min_distance

    checks: list[dict[str, Any]] = []

    cell = atoms.cell.array
    finite = bool(np.isfinite(cell).all() and np.isfinite(atoms.positions).all())
    checks.append({
        "name": "finite_cell_and_positions",
        "passed": finite,
        "message": "cell and positions are finite" if finite else "cell or positions contain non-finite values",
    })

    lengths = cell_lengths(atoms)
    positive_lengths = all(length > 0 for length in lengths)
    checks.append({
        "name": "cell_lengths",
        "passed": positive_lengths,
        "message": "cell lengths are positive" if positive_lengths else "cell has non-positive length",
        "lengths": lengths,
    })

    centered = True
    margin = None
    if len(atoms):
        mins = atoms.positions.min(axis=0)
        maxs = atoms.positions.max(axis=0)
        cell_lengths_array = np.asarray(cell_size, dtype=float)
        margin = float(np.min(np.minimum(mins, cell_lengths_array - maxs)))
        centered = bool(margin > 1.0)
    checks.append({
        "name": "box_margin",
        "passed": centered,
        "message": f"minimum molecule-to-cell-edge margin {margin:.3f} Å" if margin is not None else "empty molecule",
        "minimum_margin": margin,
    })

    min_distance_check = check_min_distance(atoms, threshold=min_distance, mic=False)
    checks.append({
        "name": "min_distance",
        "passed": min_distance_check.passed,
        "message": (
            f"min intramolecular distance {min_distance_check.min_distance:.3f} Å >= {min_distance:.3f} Å"
            if min_distance_check.passed
            else f"min intramolecular distance {min_distance_check.min_distance:.3f} Å < {min_distance:.3f} Å"
        ),
        "min_distance": min_distance_check.min_distance,
        "threshold": min_distance_check.threshold,
        "pair": [min_distance_check.atom_i, min_distance_check.atom_j],
    })

    atom_count_ok = len(atoms) <= max_atoms
    checks.append({
        "name": "atom_count",
        "passed": atom_count_ok,
        "message": f"{len(atoms)} atoms <= {max_atoms}" if atom_count_ok else f"{len(atoms)} atoms > {max_atoms}",
        "n_atoms": len(atoms),
        "max_atoms": max_atoms,
    })

    return {
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
    }


def builder_provenance(atoms: Atoms) -> dict[str, Any]:
    keys = [
        "adsorbate_builder",
        "adsorbate_smiles",
        "adsorbate_smiles_source",
        "adsorbate_surrogate_smiles",
        "adsorbate_fallback_reason",
        "smiles",
        "surrogate_smiles",
    ]
    return {key: atoms.info[key] for key in keys if key in atoms.info}


@contextlib.contextmanager
def redirect_stdout_to_stderr() -> Any:
    """Keep script stdout machine-readable even if builders print directly."""
    sys.stdout.flush()
    sys.stderr.flush()
    saved_stdout_fd = os.dup(1)
    try:
        os.dup2(2, 1)
        with contextlib.redirect_stdout(sys.stderr):
            yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved_stdout_fd, 1)
        os.close(saved_stdout_fd)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build neutral gas-phase molecule POSCAR files in an isolated orthorhombic cell.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--species", required=True, help="Label, alias, raw SMILES, smiles:<SMILES>, or supported name.")
    parser.add_argument("--label", help="Output label. Defaults to a safe name derived from --species.")
    parser.add_argument("--cell-size", nargs=3, type=float, default=DEFAULT_CELL_SIZE, metavar=("A", "B", "C"), help="Orthorhombic cell lengths in Angstrom.")
    parser.add_argument("--box-size", type=float, help="Backward-compatible cubic cell length in Angstrom; overrides --cell-size when set.")
    parser.add_argument("--spin-multiplicity", type=int, default=None, help="Gas-phase spin multiplicity (2S+1). Default: closed-shell singlet (1).")
    parser.add_argument("--min-distance", type=float, default=0.5, help="Minimum intramolecular distance threshold in Angstrom.")
    parser.add_argument("--max-atoms", type=int, default=80, help="Maximum atom count accepted by validation.")
    parser.add_argument("--write-extxyz", action="store_true", help="Also write an extxyz copy.")
    parser.add_argument("--outdir", default="gas_phase_outputs", help="Output directory for POSCAR and metadata.")
    args = parser.parse_args()
    if args.box_size is not None and args.box_size <= 0:
        parser.error("--box-size must be positive.")
    if args.box_size is None and any(length <= 0 for length in args.cell_size):
        parser.error("--cell-size lengths must be positive.")

    try:
        from slabuilder import build_adsorbate_atoms
        from slabuilder.adsorption import resolve_adsorbate_smiles
        from slabuilder.utils import save_structure
    except ImportError as exc:
        raise SystemExit(
            "Could not import slabuilder. Install it in the active environment. "
            f"Original error: {exc}"
        )

    with redirect_stdout_to_stderr():
        source_atoms = build_adsorbate_atoms(args.species)

    cell_size = (
        (float(args.box_size), float(args.box_size), float(args.box_size))
        if args.box_size is not None
        else (float(args.cell_size[0]), float(args.cell_size[1]), float(args.cell_size[2]))
    )
    atoms = center_in_cell(source_atoms, cell_size)
    spin_reference = resolve_spin_multiplicity(args.spin_multiplicity)
    dipole = dipole_hint(atoms)
    validation = validate_gas_molecule(
        atoms,
        min_distance=args.min_distance,
        max_atoms=args.max_atoms,
        cell_size=cell_size,
    )

    label = safe_name(args.label or args.species.replace("smiles:", "smiles_"))
    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    stem = safe_name(f"{label}_gas")
    poscar_path = save_structure(atoms, outdir / f"{stem}_POSCAR", fmt="poscar")
    paths = {"poscar": str(poscar_path)}
    if args.write_extxyz:
        extxyz_path = save_structure(atoms, outdir / f"{stem}.extxyz", fmt="extxyz")
        paths["extxyz"] = str(extxyz_path)

    smiles_resolution = resolve_adsorbate_smiles(args.species)
    metadata = {
        "kind": "gas_molecule",
        "input_species": args.species,
        "label": label,
        "formula": atoms.get_chemical_formula(),
        "composition": composition_counts(atoms),
        "n_atoms": len(atoms),
        "cell_size": [float(x) for x in cell_size],
        "box_size": float(cell_size[0]) if len(set(cell_size)) == 1 else None,
        "cell_lengths": cell_lengths(atoms),
        "pbc": [bool(x) for x in atoms.get_pbc()],
        "centered_in_box": True,
        "builder_provenance": builder_provenance(source_atoms),
        "smiles_resolution": {
            "smiles": smiles_resolution.smiles,
            "source": smiles_resolution.source,
            "error": smiles_resolution.error,
        },
        "charge_spin_policy": {
            "charge": "unsupported",
            "spin": "see spin_reference",
            "note": "Neutral geometry only; charge is not inferred. Spin multiplicity is provided in spin_reference for downstream calculation setup.",
        },
        "spin_reference": spin_reference,
        "dipole_hint": dipole,
        "calculation_boundary": {
            "relaxation": "calculation_workflow",
            "static_energy": "calculation_workflow",
            "frequency": "calculation_workflow",
        },
        "validation": validation,
        "paths": paths,
    }
    meta_path = outdir / f"{stem}.metadata.json"
    metadata["paths"]["metadata"] = str(meta_path)
    meta_path.write_text(json.dumps(metadata, indent=2, default=json_default))

    print(json.dumps(metadata, indent=2, default=json_default))
    return 0 if validation["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
