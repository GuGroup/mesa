#!/usr/bin/env python3
"""Classify a finished/failed VASP job and recommend a recovery action.

Unattended workflows cannot eyeball OUTCAR. This reads a job's output files and
returns a single machine-readable JSON object: what went wrong and the concrete
next step (continue from CONTCAR, switch ALGO, reduce POTIM, ...). It never
edits files or resubmits — the agent acts on `recommended_action`.

Usage:
    python diagnose_vasp_failure.py --dir <remote_dir>
    python diagnose_vasp_failure.py --dir <remote_dir> --max-retries 3 --retry-count 1
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


# OUTCAR/stdout signatures of well-known VASP failure modes.
ERROR_SIGNATURES = {
    "ZBRENT": "ZBRENT: fatal error in bracketing (line-search/geometry step too large)",
    "ZPOTRF": "ZPOTRF: cell/overlap became singular (atoms too close or bad geometry)",
    "EDDDAV": "EDDDAV: Davidson electronic solver failed",
    "Inverse of cell": "cell inversion failed (degenerate cell)",
    "WARNING: Sub-Space-Matrix": "Sub-Space-Matrix not Hermitian (electronic instability)",
    "internal error in subroutine SGRCON": "symmetry/Bravais mismatch (try ISYM=0)",
}


def finite_int(value: str | None) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def read_text(path: Path) -> str:
    return path.read_text(errors="ignore") if path.exists() else ""


def find_param(text: str, name: str) -> str | None:
    match = re.search(rf"{name}\s*=\s*([-+0-9.Ee]+)", text)
    return match.group(1) if match else None


def parse_oszicar_steps(text: str) -> list[int]:
    """Return SCF iteration count per ionic step from an OSZICAR."""
    scf_line = re.compile(r"^\s*(DAV|RMM|CG|EDDAV|DMP|GES|QDM|JDA|PRJ)\s*:")
    ionic_line = re.compile(r"^\s*\d+\s+F=")
    steps: list[int] = []
    scf = 0
    for line in text.splitlines():
        if scf_line.match(line):
            scf += 1
        elif ionic_line.match(line):
            steps.append(scf)
            scf = 0
    return steps


def classify(directory: Path, max_retries: int, retry_count: int) -> dict[str, Any]:
    outcar = read_text(directory / "OUTCAR")
    oszicar = read_text(directory / "OSZICAR")
    incar = read_text(directory / "INCAR")

    nsw = finite_int(find_param(incar, "NSW") or find_param(outcar, "NSW"))
    nelm = finite_int(find_param(incar, "NELM") or find_param(outcar, "NELM"))

    ionic_scf = parse_oszicar_steps(oszicar)
    n_ionic = len(ionic_scf)
    last_scf = ionic_scf[-1] if ionic_scf else None

    contcar = directory / "CONTCAR"
    can_continue = contcar.is_file() and contcar.stat().st_size > 0

    reached_accuracy = "reached required accuracy" in outcar
    error_sig = next((msg for key, msg in ERROR_SIGNATURES.items() if key in outcar), None)

    electronic_stuck = nelm is not None and last_scf is not None and last_scf >= nelm
    nsw_reached = nsw is not None and n_ionic >= nsw

    retries_left = retry_count < max_retries

    if reached_accuracy:
        failure_class = "converged"
        action = "none"
        detail = "OUTCAR reports reached required accuracy; treat as converged."
    elif error_sig and "ZBRENT" in error_sig:
        failure_class = "geometry_step_error"
        action = "continue_from_contcar_reduce_potim" if can_continue else "restart_reduce_potim"
        detail = f"{error_sig}. Restart from CONTCAR with smaller POTIM (e.g. 0.05) and ALGO Normal."
    elif error_sig and "ZPOTRF" in error_sig:
        failure_class = "singular_cell_or_close_atoms"
        action = "inspect_structure"
        detail = f"{error_sig}. Do NOT blindly continue; inspect geometry/min-distance first."
    elif electronic_stuck:
        failure_class = "electronic_not_converged"
        action = "continue_from_contcar_algo_normal" if can_continue else "restart_algo_normal"
        detail = (
            f"Last ionic step hit NELM={nelm} SCF iterations. Switch ALGO to Normal/All, "
            "consider AMIX/BMIX tuning, and continue from CONTCAR if available."
        )
    elif error_sig:
        failure_class = "vasp_error"
        action = "inspect_structure"
        detail = error_sig
    elif nsw_reached:
        failure_class = "ionic_not_converged"
        action = "continue_from_contcar" if can_continue else "restart_clean"
        detail = (
            f"Reached NSW={nsw} ionic steps without convergence. Continue from CONTCAR "
            "(geometry was progressing); raising NSW is usually enough."
        )
    elif n_ionic == 0:
        failure_class = "no_progress"
        action = "inspect_structure"
        detail = "No ionic steps recorded; check POTCAR/INCAR/queue logs before retrying."
    else:
        failure_class = "unknown_incomplete"
        action = "continue_from_contcar" if can_continue else "inspect_structure"
        detail = "Run ended without a convergence marker or known error; inspect or continue."

    if action != "none" and not retries_left:
        action = "escalate_drop_candidate"
        detail += f" Retry budget exhausted ({retry_count}/{max_retries}); drop this candidate."

    return {
        "directory": str(directory),
        "failure_class": failure_class,
        "recommended_action": action,
        "detail": detail,
        "converged": reached_accuracy,
        "can_continue_from_contcar": can_continue,
        "n_ionic_steps": n_ionic,
        "last_ionic_scf_iterations": last_scf,
        "nsw": nsw,
        "nelm": nelm,
        "nsw_reached": nsw_reached,
        "electronic_not_converged": electronic_stuck,
        "error_signature": error_sig,
        "retry_count": retry_count,
        "max_retries": max_retries,
        "retries_left": retries_left,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify a VASP failure and recommend recovery.")
    parser.add_argument("--dir", required=True, help="Job remote_dir containing OUTCAR/OSZICAR/INCAR/CONTCAR.")
    parser.add_argument("--max-retries", type=int, default=3, help="Maximum automatic restarts allowed.")
    parser.add_argument("--retry-count", type=int, default=0, help="Restarts already attempted for this job.")
    args = parser.parse_args()

    directory = Path(args.dir).expanduser().resolve()
    if not directory.is_dir():
        raise SystemExit(f"--dir not found or not a directory: {directory}")
    result = classify(directory, args.max_retries, args.retry_count)
    print(json.dumps(result, indent=2))
    return 0 if result["converged"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
