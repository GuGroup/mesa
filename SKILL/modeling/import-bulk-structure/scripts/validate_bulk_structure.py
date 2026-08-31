#!/usr/bin/env python3
"""Run the general source-bulk phase validation gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from ase import Atoms
from ase.io import read

MAX_BULK_CELL_ASPECT_RATIO = 5.0
MIN_DISTANCE = 0.5


def validate_bulk_structure(atoms: Atoms) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, message: str, **details: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "message": message, **details})

    cell = np.asarray(atoms.get_cell(), dtype=float)
    positions = np.asarray(atoms.get_positions(), dtype=float)
    finite = bool(cell.shape == (3, 3) and np.all(np.isfinite(cell)) and np.all(np.isfinite(positions)))
    volume = float(abs(np.linalg.det(cell))) if finite else 0.0
    lengths = [float(np.linalg.norm(vector)) for vector in cell] if finite else [0.0, 0.0, 0.0]
    aspect_ratio = (
        float(max(lengths) / min(lengths))
        if len(lengths) == 3 and min(lengths) > 1e-12
        else float("inf")
    )
    minimum_distance = _minimum_distance(atoms)
    pbc = [bool(value) for value in atoms.get_pbc()]
    elongated_cell_detected = bool(aspect_ratio > MAX_BULK_CELL_ASPECT_RATIO)

    add("nonempty", len(atoms) > 0, f"atom count={len(atoms)}")
    add("finite", finite, "cell and positions are finite")
    add("cell", volume > 1e-8 and all(pbc), f"volume={volume:.6g} Ang^3; pbc={pbc}")
    add(
        "minimum_distance",
        minimum_distance >= MIN_DISTANCE,
        f"minimum distance={minimum_distance:.6g} Ang",
        threshold=MIN_DISTANCE,
    )
    add(
        "bulk_cell_shape",
        not elongated_cell_detected,
        (
            f"cell aspect ratio={aspect_ratio:.6g} exceeds {MAX_BULK_CELL_ASPECT_RATIO}"
            if elongated_cell_detected
            else "bulk cell aspect ratio is acceptable"
        ),
        elongated_cell_detected=elongated_cell_detected,
        aspect_ratio=aspect_ratio,
        threshold=MAX_BULK_CELL_ASPECT_RATIO,
    )

    passed = all(check["passed"] for check in checks)
    return {
        "schema_version": "1.0",
        "kind": "source_bulk_validation",
        "status": "accepted" if passed else "rejected",
        "passed": passed,
        "metrics": {
            "formula": atoms.get_chemical_formula(),
            "atom_count": len(atoms),
            "cell_lengths": lengths,
            "cell_aspect_ratio": aspect_ratio,
            "cell_volume": volume,
            "minimum_distance": minimum_distance,
            "elongated_cell_detected": elongated_cell_detected,
        },
        "checks": checks,
    }


def _minimum_distance(atoms: Atoms) -> float:
    if len(atoms) < 2:
        return float("inf")
    distances = atoms.get_all_distances(mic=True)
    np.fill_diagonal(distances, np.inf)
    return float(np.min(distances))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structure", required=True, help="Source bulk POSCAR/CIF/extxyz path.")
    parser.add_argument("--output", required=True, help="JSON validation report path.")
    args = parser.parse_args()

    structure_path = Path(args.structure).expanduser().resolve()
    report = validate_bulk_structure(read(structure_path))
    report["structure"] = {
        "path": str(structure_path),
        "sha256": hashlib.sha256(structure_path.read_bytes()).hexdigest(),
    }
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(output_path)}, sort_keys=True))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
