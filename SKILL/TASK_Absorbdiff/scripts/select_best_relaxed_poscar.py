#!/usr/bin/env python3
"""Select the best relaxed AdsorbDiff/GemNet trajectory and write a POSCAR."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from ase import Atoms
from ase.io import read, write


TASK_ID = "TASK_ADSORBDIFF_SELECT_BEST_RELAXED"


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(json_safe(payload), handle, indent=2, sort_keys=True)
        handle.write("\n")


def read_final_atoms(path: Path) -> Atoms:
    atoms = read(str(path), index=-1)
    if not isinstance(atoms, Atoms):
        raise ValueError(f"final frame is not an ASE Atoms object: {path}")
    return atoms


def scalar_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, np.ndarray):
        if value.size == 0:
            return None
        value = value.reshape(-1)[0]
    elif isinstance(value, (list, tuple)):
        if not value:
            return None
        value = value[0]
    return float(value)


def final_energy(atoms: Atoms) -> float | None:
    try:
        return float(atoms.get_potential_energy())
    except Exception:  # noqa: BLE001 - trajectory metadata varies by writer.
        calc_results = getattr(getattr(atoms, "calc", None), "results", None)
        if isinstance(calc_results, dict):
            value = scalar_float(calc_results.get("energy"))
            if value is not None:
                return value
        value = atoms.info.get("energy")
        if value is None:
            value = atoms.info.get("relaxed_energy")
        return scalar_float(value)


def final_fmax(atoms: Atoms) -> float | None:
    try:
        forces = np.asarray(atoms.get_forces(), dtype=float)
    except Exception:  # noqa: BLE001 - missing forces is a reportable condition.
        return None
    if forces.size == 0:
        return None
    return float(np.linalg.norm(forces, axis=1).max())


def tag_counts(atoms: Atoms) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tag in atoms.get_tags():
        key = str(int(tag))
        counts[key] = counts.get(key, 0) + 1
    return counts


def summarize_traj(path: Path) -> tuple[dict[str, Any], Atoms]:
    atoms = read_final_atoms(path)
    energy = final_energy(atoms)
    fmax = final_fmax(atoms)
    warnings: list[str] = []
    if energy is None:
        warnings.append("missing final energy")
    if fmax is None:
        warnings.append("missing final forces/fmax")
    return (
        {
            "sid": path.stem,
            "traj": str(path),
            "num_atoms": len(atoms),
            "formula": atoms.get_chemical_formula(),
            "energy_eV": energy,
            "fmax_eV_per_A": fmax,
            "tag_counts": tag_counts(atoms),
            "warnings": warnings,
        },
        atoms,
    )


def sort_key(item: dict[str, Any]) -> tuple[float, float, str]:
    energy = item.get("energy_eV")
    fmax = item.get("fmax_eV_per_A")
    return (
        float("inf") if energy is None else float(energy),
        float("inf") if fmax is None else float(fmax),
        str(item.get("sid", "")),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relax-dir", required=True, type=Path, help="Directory containing relaxed .traj files.")
    parser.add_argument("--output-poscar", required=True, type=Path, help="POSCAR path for the selected best structure.")
    parser.add_argument("--summary", required=True, type=Path, help="JSON summary/ranking output path.")
    parser.add_argument("--all-poscars-dir", type=Path, help="Optional directory for all final-frame POSCARs.")
    parser.add_argument(
        "--fmax-warning",
        type=float,
        default=0.011,
        help="Warn when the selected structure's final fmax is above this value.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    relax_dir = args.relax_dir.expanduser().resolve()
    traj_paths = sorted(relax_dir.glob("*.traj"))
    errors: list[dict[str, str]] = []
    ranked: list[dict[str, Any]] = []
    atoms_by_sid: dict[str, Atoms] = {}

    if not traj_paths:
        errors.append({"type": "MissingTrajectories", "message": f"no .traj files found in {relax_dir}"})
    for path in traj_paths:
        try:
            item, atoms = summarize_traj(path)
            ranked.append(item)
            atoms_by_sid[str(item["sid"])] = atoms
        except Exception as exc:  # noqa: BLE001 - continue reporting all readable trajectories.
            errors.append({"type": type(exc).__name__, "message": f"{path}: {exc}"})

    ranked = sorted(ranked, key=sort_key)
    best = ranked[0] if ranked and ranked[0].get("energy_eV") is not None else None
    artifacts: list[dict[str, str]] = []

    if best is None:
        errors.append({"type": "NoRankableTrajectory", "message": "no trajectory had a usable final energy"})
    else:
        best_atoms = atoms_by_sid[str(best["sid"])]
        if best.get("fmax_eV_per_A") is not None and float(best["fmax_eV_per_A"]) > args.fmax_warning:
            best.setdefault("warnings", []).append(
                f"fmax above {args.fmax_warning:.3f} eV/A: {float(best['fmax_eV_per_A']):.5f}"
            )
        args.output_poscar.parent.mkdir(parents=True, exist_ok=True)
        write(str(args.output_poscar), best_atoms, format="vasp", vasp5=True, direct=True, sort=False)
        best["best_poscar"] = str(args.output_poscar)
        artifacts.append({"kind": "best_relaxed_poscar", "path": str(args.output_poscar)})

        if args.all_poscars_dir:
            args.all_poscars_dir.mkdir(parents=True, exist_ok=True)
            for item in ranked:
                sid = str(item["sid"])
                atoms = atoms_by_sid.get(sid)
                if atoms is None:
                    continue
                out = args.all_poscars_dir / f"{sid}.vasp"
                write(str(out), atoms, format="vasp", vasp5=True, direct=True, sort=False)
                item["final_poscar"] = str(out)
            artifacts.append({"kind": "all_final_poscars_dir", "path": str(args.all_poscars_dir)})

    payload = {
        "status": "failure" if errors else "success",
        "task_id": TASK_ID,
        "skill": "adsorbdiff_select_best_relaxed",
        "selection_metric": "lowest_final_energy_eV_then_fmax",
        "relax_dir": str(relax_dir),
        "best_by_energy": best,
        "ranked": ranked,
        "artifacts": artifacts,
        "errors": errors,
        "provenance": {
            "inputs": [str(path) for path in traj_paths],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    write_json(args.summary, payload)
    print(json.dumps(json_safe(payload), indent=2, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
