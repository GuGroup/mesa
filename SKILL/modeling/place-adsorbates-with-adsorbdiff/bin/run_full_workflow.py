#!/usr/bin/env python3
"""Run the POSCAR-first AdsorbDiff placement workflow end to end.

This runner is intentionally thin: the controller still owns the scientific
decisions, while this file wires the generated commands together for a server.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
CONTROLLER = SKILL_DIR / "scripts" / "adsorbdiff_controller.py"
WORKFLOW = SKILL_DIR / "scripts" / "adsorbdiff_workflow.py"
SELECT_BEST = SKILL_DIR / "scripts" / "select_best_relaxed_poscar.py"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return data


def resolve_case_workdir(input_path: Path) -> Path:
    data = read_json(input_path)
    workdir = Path(str(data.get("workdir", "adsorbdiff_poscar_run"))).expanduser()
    if workdir.is_absolute():
        return workdir
    return (input_path.parent / workdir).resolve()


def run(cmd: list[str], cwd: Path | None = None) -> None:
    printable = " ".join(shlex.quote(part) for part in cmd)
    print(f"\n$ {printable}", flush=True)
    completed = subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Controller input JSON.")
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Generate controller/workflow plans without running sampling or relaxation.",
    )
    parser.add_argument(
        "--skip-placement",
        action="store_true",
        help="Skip candidate placement and only build/run the AdsorbDiff workflow.",
    )
    parser.add_argument(
        "--skip-adsorbdiff",
        action="store_true",
        help="Stop after controller and candidate placement.",
    )
    parser.add_argument(
        "--skip-select-best",
        action="store_true",
        help="Do not select and export the best relaxed POSCAR after relaxation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = args.input.expanduser().resolve()
    workdir = resolve_case_workdir(input_path)
    results_dir = workdir / "results"
    resolved_path = results_dir / "resolved_adsorbdiff_config.json"

    controller_cmd = [sys.executable, str(CONTROLLER), "--input", str(input_path)]
    run(controller_cmd)

    resolved = read_json(resolved_path)
    if resolved.get("errors"):
        print(f"\nController reported errors. Inspect: {resolved_path}", file=sys.stderr)
        return 1

    if not args.skip_placement and not args.plan_only:
        candidate_cmd = resolved.get("data", {}).get("candidate_command")
        if not isinstance(candidate_cmd, list) or not all(isinstance(item, str) for item in candidate_cmd):
            print(f"Missing candidate command in {resolved_path}", file=sys.stderr)
            return 1
        run(candidate_cmd)

    workflow_input = Path(str(resolved.get("data", {}).get("workflow_input", ""))).expanduser()
    if not workflow_input.is_absolute():
        workflow_input = (workdir / workflow_input).resolve()
    workflow_workdir = workdir / "adsorbdiff_sampling"

    workflow_cmd = [
        sys.executable,
        str(WORKFLOW),
        "--input",
        str(workflow_input),
        "--workdir",
        str(workflow_workdir),
    ]
    if not args.plan_only and not args.skip_adsorbdiff:
        workflow_cmd.append("--execute")
    run(workflow_cmd)

    if not args.plan_only and not args.skip_adsorbdiff and not args.skip_select_best:
        workflow_data = read_json(workflow_input)
        workflow_base = Path(str(workflow_data.get("workdir", workflow_workdir))).expanduser()
        if not workflow_base.is_absolute():
            workflow_base = (workflow_input.parent / workflow_base).resolve()
        relaxation = workflow_data.get("relaxation", {})
        relaxation = relaxation if isinstance(relaxation, dict) else {}
        relax_dir = Path(str(relaxation.get("traj_dir", "samples/site0/relaxations"))).expanduser()
        if not relax_dir.is_absolute():
            relax_dir = (workflow_base / relax_dir).resolve()

        best_poscar = workdir / "best_relaxed_POSCAR.vasp"
        best_summary = results_dir / "best_relaxed_summary.json"
        all_poscars = workdir / "final_poscars"
        select_cmd = [
            sys.executable,
            str(SELECT_BEST),
            "--relax-dir",
            str(relax_dir),
            "--output-poscar",
            str(best_poscar),
            "--summary",
            str(best_summary),
            "--all-poscars-dir",
            str(all_poscars),
        ]
        run(select_cmd)

        summary = read_json(best_summary)
        best = summary.get("best_by_energy", {})
        best = best if isinstance(best, dict) else {}
        print("\nBEST_RELAXED_POSCAR=" + str(best.get("best_poscar", best.get("final_poscar", best_poscar))))
        print("BEST_RELAXED_SUMMARY=" + str(best_summary))
        if best.get("energy_eV") is not None:
            print("BEST_ENERGY_EV=" + str(best["energy_eV"]))
        if best.get("fmax_eV_per_A") is not None:
            print("BEST_FMAX_EV_PER_A=" + str(best["fmax_eV_per_A"]))

    print(f"\nDone. Main report artifacts are under: {results_dir}")
    print(f"AdsorbDiff sampling workdir: {workflow_workdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
