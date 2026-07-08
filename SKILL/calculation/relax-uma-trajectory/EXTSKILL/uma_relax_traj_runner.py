"""Fixed UMA relaxation trajectory runner for TASK_UMA_RELAX_TRAJECTORY."""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_ID = "TASK_UMA_RELAX_TRAJECTORY"
SKILL_NAME = "uma_relax_traj_runner"


def run(config_path: Path | str = "results/resolved_uma_config.json", context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute controller-resolved UMA relaxation settings."""

    context = context or {}
    workdir = _resolve_workdir(context)
    config_file = _resolve_path(config_path, workdir)
    output = _mesa_output()
    output["provenance"]["inputs"].append(str(config_file))

    config = _read_config_or_write_failure(config_file, workdir, output)
    if config is None:
        return output

    result_path = _resolve_path(config["outputs"].get("result_json", "results/uma_relax_traj.json"), workdir)
    trajectory_path = _resolve_path(config["outputs"].get("trajectory", "relax.traj"), workdir)
    relaxed_poscar_path = _resolve_path(config["outputs"].get("relaxed_poscar", "relaxed/POSCAR"), workdir)
    log_path = _resolve_path(config["outputs"].get("log", "logs/uma_relax_traj.log"), workdir)
    poscar_path = _resolve_path(config.get("input_poscar", "POSCAR"), workdir)
    _ensure_dirs(result_path.parent, trajectory_path.parent, relaxed_poscar_path.parent, log_path.parent)

    model = str(config["uma"]["model"])
    task_name = str(config["uma"]["task_name"])
    device = str(config["uma"]["device"])
    relaxation = config["relaxation"]
    relax_type = str(relaxation["relax_type"]).lower()
    fmax = float(relaxation["fmax"])
    steps = int(relaxation["steps"])
    optimizer_name = str(relaxation.get("optimizer", "FIRE"))
    constraints = list(relaxation.get("constraints") or [])

    output["data"].update(
        {
            "config": str(config_file),
            "input": str(poscar_path),
            "output": str(relaxed_poscar_path),
            "trajectory": str(trajectory_path),
            "result_json": str(result_path),
            "log": str(log_path),
            "model": model,
            "task_name": task_name,
            "device": device,
            "relax_type": relax_type,
            "fmax": fmax,
            "steps": steps,
            "optimizer": optimizer_name,
            "constraints": constraints,
        }
    )

    try:
        from ase.io import read, write  # type: ignore
    except ImportError as exc:
        return _failure(
            output,
            result_path,
            config_file,
            poscar_path,
            relaxed_poscar_path,
            trajectory_path,
            "ImportError",
            f"ASE is not available in the execution environment: {exc}",
        )

    try:
        atoms = read(str(poscar_path), format="vasp")
        n_atoms_initial = len(atoms)
        atoms.calc = _build_uma_calculator(model=model, task_name=task_name, device=device)
        _apply_resolved_constraints(atoms, constraints)

        initial_energy = _safe_float(atoms.get_potential_energy())
        initial_forces = atoms.get_forces()
        initial_max_force = _max_force(initial_forces)

        target = _build_relaxation_target(atoms, relax_type)
        optimizer_class = _optimizer_class(optimizer_name)
        optimizer = optimizer_class(
            target,
            trajectory=str(trajectory_path),
            logfile=str(log_path),
        )
        converged = bool(optimizer.run(fmax=fmax, steps=steps))

        final_energy = _safe_float(atoms.get_potential_energy())
        final_forces = atoms.get_forces()
        final_max_force = _max_force(final_forces)
        n_steps = _optimizer_steps(optimizer)
        write(str(relaxed_poscar_path), atoms, format="vasp", direct=True, sort=False, vasp5=True)

        payload = {
            "status": "success",
            "runner": SKILL_NAME,
            "input": _display_path(poscar_path, workdir),
            "output": _display_path(relaxed_poscar_path, workdir),
            "trajectory": _display_path(trajectory_path, workdir),
            "config": _display_path(config_file, workdir),
            "results": {
                "converged": converged,
                "n_steps": n_steps,
                "initial_energy_ev": initial_energy,
                "final_energy_ev": final_energy,
                "initial_max_force_ev_per_a": initial_max_force,
                "final_max_force_ev_per_a": final_max_force,
                "n_atoms_initial": n_atoms_initial,
                "n_atoms_final": len(atoms),
            },
            "errors": [],
            "timestamp_utc": _utc_now(),
        }
        _write_json(result_path, payload)
        output["status"] = "success"
        output["data"].update(payload)
        output["artifacts"].extend(
            [str(trajectory_path), str(relaxed_poscar_path), str(result_path), str(log_path)]
        )
        output["provenance"]["generated_files"].extend(
            [str(trajectory_path), str(relaxed_poscar_path), str(result_path), str(log_path)]
        )
        output["provenance"]["external_calls"].append(
            {
                "tool": "FAIRChem/UMA",
                "model": model,
                "task_name": task_name,
                "device": device,
                "timestamp_utc": payload["timestamp_utc"],
            }
        )
        output["next_action"] = {
            "recommendation": "continue",
            "reason": "relax.traj and relaxed/POSCAR are available.",
        }
        return output
    except Exception as exc:  # noqa: BLE001 - write structured failure for MESA.
        return _failure(
            output,
            result_path,
            config_file,
            poscar_path,
            relaxed_poscar_path,
            trajectory_path,
            type(exc).__name__,
            str(exc),
        )


def _read_config_or_write_failure(
    config_file: Path,
    workdir: Path,
    output: dict[str, Any],
) -> dict[str, Any] | None:
    fallback_result_path = workdir / "results" / "uma_relax_traj.json"
    try:
        config = json.loads(config_file.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001 - write structured failure for missing/bad config.
        _failure(
            output,
            fallback_result_path,
            config_file,
            workdir / "POSCAR",
            workdir / "relaxed" / "POSCAR",
            workdir / "relax.traj",
            type(exc).__name__,
            f"Could not read results/resolved_uma_config.json: {exc}",
        )
        return None

    required_sections = ["outputs", "uma", "relaxation", "input_poscar"]
    missing = [section for section in required_sections if section not in config]
    if missing:
        _failure(
            output,
            fallback_result_path,
            config_file,
            workdir / "POSCAR",
            workdir / "relaxed" / "POSCAR",
            workdir / "relax.traj",
            "ValueError",
            "Resolved config is missing required sections: " + ", ".join(missing),
        )
        return None
    return config


def _build_uma_calculator(model: str, task_name: str, device: str) -> Any:
    try:
        from fairchem.core import FAIRChemCalculator, pretrained_mlip  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "FAIRChem/UMA is not installed. Install fairchem-core with UMA support "
            "in the execution environment."
        ) from exc

    try:
        predictor = pretrained_mlip.get_predict_unit(model, device=device)
    except TypeError:
        predictor = pretrained_mlip.get_predict_unit(model_name=model, device=device)

    try:
        return FAIRChemCalculator(predictor, task_name=task_name)
    except TypeError:
        return FAIRChemCalculator(predictor, task=task_name)


def _build_relaxation_target(atoms: Any, relax_type: str) -> Any:
    if relax_type == "geometry":
        return atoms
    if relax_type == "cell":
        try:
            from ase.filters import FrechetCellFilter  # type: ignore

            return FrechetCellFilter(atoms)
        except ImportError:
            from ase.filters import UnitCellFilter  # type: ignore

            return UnitCellFilter(atoms)
    raise ValueError("relax_type must be geometry or cell for TASK_UMA_RELAX_TRAJECTORY.")


def _optimizer_class(optimizer_name: str) -> Any:
    normalized = optimizer_name.strip().lower()
    if normalized == "fire":
        from ase.optimize import FIRE  # type: ignore

        return FIRE
    if normalized == "bfgs":
        from ase.optimize import BFGS  # type: ignore

        return BFGS
    if normalized == "lbfgs":
        from ase.optimize import LBFGS  # type: ignore

        return LBFGS
    raise ValueError(f"Unsupported controller-resolved optimizer: {optimizer_name}")


def _apply_resolved_constraints(atoms: Any, constraints: list[dict[str, Any]]) -> None:
    for constraint in constraints:
        constraint_type = constraint.get("type")
        if constraint_type == "fix_atoms_indices":
            indices = [int(index) for index in constraint.get("indices", [])]
            if indices:
                from ase.constraints import FixAtoms  # type: ignore

                atoms.set_constraint(FixAtoms(indices=indices))
        elif constraint_type == "poscar_selective_dynamics":
            continue
        elif constraint_type in {None, ""}:
            continue
        else:
            raise ValueError(f"Unsupported controller-resolved constraint type: {constraint_type}")


def _failure(
    output: dict[str, Any],
    result_path: Path,
    config_path: Path,
    input_poscar: Path,
    output_poscar: Path,
    trajectory_path: Path,
    error_type: str,
    message: str,
) -> dict[str, Any]:
    payload = {
        "status": "failure",
        "runner": SKILL_NAME,
        "input": str(input_poscar),
        "output": str(output_poscar),
        "trajectory": str(trajectory_path),
        "config": str(config_path),
        "errors": [{"type": error_type, "message": message}],
        "timestamp_utc": _utc_now(),
    }
    _write_json(result_path, payload)
    output["status"] = "failure"
    output["errors"].append({"code": error_type, "message": message})
    output["artifacts"].append(str(result_path))
    output["provenance"]["generated_files"].append(str(result_path))
    output["next_action"] = {
        "recommendation": "retry",
        "reason": "UMA relaxation trajectory runner failed.",
    }
    return output


def _max_force(forces: Any) -> float | None:
    if forces is None:
        return None
    max_norm = 0.0
    for row in forces:
        norm = math.sqrt(sum(float(value) ** 2 for value in row[:3]))
        max_norm = max(max_norm, norm)
    return max_norm


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _optimizer_steps(optimizer: Any) -> int | None:
    for attr in ("nsteps", "n_steps"):
        value = getattr(optimizer, attr, None)
        if isinstance(value, int):
            return value
    return None


def _display_path(path: Path, workdir: Path) -> str:
    try:
        return path.resolve().relative_to(workdir.resolve()).as_posix()
    except ValueError:
        return str(path)


def _resolve_workdir(context: dict[str, Any]) -> Path:
    return Path(context.get("workdir") or os.getcwd()).expanduser().resolve()


def _resolve_path(path_value: str | os.PathLike[str], base: Path) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base / path).resolve()


def _ensure_dirs(*dirs: Path) -> None:
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _mesa_output() -> dict[str, Any]:
    return {
        "status": "failure",
        "task_id": TASK_ID,
        "skill": SKILL_NAME,
        "data": {},
        "artifacts": [],
        "messages": [],
        "errors": [],
        "provenance": {"inputs": [], "external_calls": [], "generated_files": []},
        "next_action": {"recommendation": "needs_human_review", "reason": ""},
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the fixed UMA relaxation trajectory runner.")
    parser.add_argument("--config", default="results/resolved_uma_config.json", help="Resolved controller config JSON.")
    parser.add_argument("--output", help="Optional MESA output envelope path.")
    parser.add_argument("--workdir", help="Working directory for task artifacts.")
    parser.add_argument("--verbose", action="store_true", help="Print output JSON to stdout.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    context: dict[str, Any] = {}
    if args.workdir:
        context["workdir"] = args.workdir
    result = run(args.config, context)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.verbose:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
