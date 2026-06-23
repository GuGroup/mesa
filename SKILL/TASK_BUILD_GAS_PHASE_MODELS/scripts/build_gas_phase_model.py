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


# Ground-state spin multiplicities (2S+1) for common gas-phase references that
# are NOT closed-shell singlets. Anything not listed defaults to a singlet.
# Keyed by ASE Hill-notation chemical formula. These matter for ORR/OER (O2),
# NOxRR (NO, NO2), and atomic/radical references; a wrong default (ispin 1)
# gives qualitatively wrong reference energies.
KNOWN_SPIN_MULTIPLICITY: dict[str, int] = {
    "H": 2,      # H atom, doublet
    "C": 3,      # C atom, 3P triplet
    "N": 4,      # N atom, 4S quartet
    "O": 3,      # O atom, 3P triplet
    "O2": 3,     # dioxygen, triplet ground state
    "NO": 2,     # nitric oxide, doublet
    "NO2": 2,    # nitrogen dioxide, doublet
    "HO": 2,     # hydroxyl radical (OH), doublet
    "HO2": 2,    # hydroperoxyl radical, doublet
    "CH3": 2,    # methyl radical, doublet
    "O3": 1,     # ozone is a closed-shell singlet (listed to avoid confusion)
}


def lookup_spin_multiplicity(atoms: Atoms, override: int | None) -> dict[str, Any]:
    """Resolve the gas-phase spin multiplicity and the VASP settings it implies."""
    if override is not None:
        if override < 1:
            raise ValueError("--spin-multiplicity must be >= 1")
        multiplicity = int(override)
        source = "override"
    else:
        hill = atoms.get_chemical_formula(mode="hill")
        multiplicity = KNOWN_SPIN_MULTIPLICITY.get(hill, 1)
        source = "lookup" if hill in KNOWN_SPIN_MULTIPLICITY else "default_singlet"
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
            "Open-shell reference: set ispin 2 and (nupdown/magmom) in vasp-job."
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
            "Net dipole possible: set ldipol true and idipol 4 in the vasp-job spec."
            if likely_polar
            else "No dipole correction needed (single atom or homonuclear diatomic)."
        ),
    }


def auto_box_size(atoms: Atoms, min_vacuum: float, floor: float = 8.0) -> float:
    """Cubic box side = largest molecular extent + 2*min_vacuum, with a floor.

    Sizing to the molecule (instead of a fixed 15 Å cube) keeps small molecules
    cheap and gives large molecules enough vacuum. The image separation along the
    longest axis equals 2*min_vacuum."""
    if len(atoms) == 0:
        return max(floor, 2.0 * min_vacuum)
    spans = atoms.positions.max(axis=0) - atoms.positions.min(axis=0)
    extent = float(np.max(spans)) if len(atoms) > 1 else 0.0
    return float(max(floor, extent + 2.0 * min_vacuum))


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
    parser.add_argument("--box-size", type=float, default=None, help="Fixed cubic box length in Angstrom. Omit to auto-size from the molecule extent + 2*--min-vacuum.")
    parser.add_argument("--min-vacuum", type=float, default=6.0, help="Minimum vacuum padding per side (Angstrom) used by auto box sizing. Ignored when --box-size is set.")
    parser.add_argument("--spin-multiplicity", type=int, default=None, help="Override the gas-phase spin multiplicity (2S+1). Default: lookup table, else singlet.")
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

    if args.box_size is not None:
        box_size = float(args.box_size)
        box_size_mode = "fixed"
    else:
        box_size = auto_box_size(source_atoms, args.min_vacuum)
        box_size_mode = "auto"
    atoms = center_in_cubic_box(source_atoms, box_size)
    spin_reference = lookup_spin_multiplicity(atoms, args.spin_multiplicity)
    dipole = dipole_hint(atoms)
    validation = validate_gas_molecule(
        atoms,
        min_distance=args.min_distance,
        max_atoms=args.max_atoms,
        box_size=box_size,
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
        "box_size": float(box_size),
        "box_size_mode": box_size_mode,
        "min_vacuum": float(args.min_vacuum) if box_size_mode == "auto" else None,
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
            "note": "Neutral geometry only; charge is not inferred. Spin multiplicity is provided in spin_reference for vasp-job to apply.",
        },
        "spin_reference": spin_reference,
        "dipole_hint": dipole,
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
