#!/usr/bin/env python3
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


def json_default(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    try:
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return float(value)
    except Exception:
        pass
    return str(value)


def safe_name(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text.strip())
    return text.strip("_") or "gas_molecule"


def composition_counts(atoms: Atoms) -> dict[str, int]:
    return dict(sorted(Counter(atoms.get_chemical_symbols()).items()))


def cell_lengths(atoms: Atoms) -> list[float]:
    return [float(x) for x in atoms.cell.lengths()]


def center_in_cubic_box(atoms: Atoms, box_size: float) -> Atoms:
    if box_size <= 0:
        raise ValueError("--box-size must be positive.")
    result = atoms.copy()
    result.set_constraint()
    result.set_cell([box_size, box_size, box_size])
    result.set_pbc([True, True, True])
    result.center()
    return result


def validate_gas_molecule(atoms: Atoms, *, min_distance: float, max_atoms: int, box_size: float) -> dict[str, Any]:
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
        margin = float(min(np.min(mins), box_size - np.max(maxs)))
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
        description="Build neutral gas-phase molecule POSCAR files in a cubic box.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--species", required=True, help="Label, alias, raw SMILES, smiles:<SMILES>, or supported name.")
    parser.add_argument("--label", help="Output label. Defaults to a safe name derived from --species.")
    parser.add_argument("--box-size", type=float, default=15.0, help="Cubic box length in Angstrom.")
    parser.add_argument("--min-distance", type=float, default=0.5, help="Minimum intramolecular distance threshold in Angstrom.")
    parser.add_argument("--max-atoms", type=int, default=80, help="Maximum atom count accepted by validation.")
    parser.add_argument("--write-extxyz", action="store_true", help="Also write an extxyz copy.")
    parser.add_argument("--outdir", default="gas_phase_outputs", help="Output directory for POSCAR and metadata.")
    args = parser.parse_args()

    try:
        from slabuilder import build_adsorbate_atoms
        from slabuilder.adsorption import resolve_adsorbate_smiles
        from slabuilder.utils import save_structure
    except Exception as exc:
        raise SystemExit(
            "Could not import slabuilder. Install it in the active environment. "
            f"Original error: {exc}"
        )

    with redirect_stdout_to_stderr():
        source_atoms = build_adsorbate_atoms(args.species)
    atoms = center_in_cubic_box(source_atoms, args.box_size)
    validation = validate_gas_molecule(
        atoms,
        min_distance=args.min_distance,
        max_atoms=args.max_atoms,
        box_size=args.box_size,
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
        "box_size": float(args.box_size),
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
            "spin": "unsupported",
            "note": "Generated neutral geometry only. Set charge/spin explicitly in downstream vasp-job spec if needed.",
        },
        "calculation_boundary": {
            "relaxation": "vasp-job",
            "static_energy": "vasp-job",
            "frequency": "vasp-job",
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
