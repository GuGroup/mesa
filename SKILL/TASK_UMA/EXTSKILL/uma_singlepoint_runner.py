"""Fixed UMA single-point runner for TASK_MLIP_DFT_HANDOFF."""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_ID = "TASK_MLIP_DFT_HANDOFF"
SKILL_NAME = "uma_singlepoint_runner"
DEFAULT_MODEL = "uma-s-1p2"
DEFAULT_TASK = "omat"
DEFAULT_DEVICE = "cuda"


def run(input_data: dict, context: dict | None = None) -> dict:
    """
    Execute this skill.

    Parameters
    ----------
    input_data:
        JSON-serializable input dictionary.

    context:
        Optional runtime context such as project root, working directory,
        dry-run flag, external service configuration, runtime metadata,
        or previous task information.

    Returns
    -------
    dict
        JSON-serializable output dictionary following the standard MESA
        skill output format.
    """

    context = context or {}
    output = _mesa_output()
    workdir = _resolve_workdir(input_data, context)
    results_dir = _resolve_path(input_data.get("results_dir") or "results", workdir)
    results_dir.mkdir(parents=True, exist_ok=True)
    result_path = results_dir / "uma_singlepoint.json"

    poscar_value = input_data.get("poscar_path") or input_data.get("input_poscar")
    if not poscar_value:
        return _fail(output, "missing_poscar_path", "Input must include poscar_path or input_poscar.")

    poscar_path = _resolve_path(poscar_value, workdir)
    mlip_settings = input_data.get("mlip_settings") or {}
    model = str(mlip_settings.get("model") or DEFAULT_MODEL)
    task = str(mlip_settings.get("task") or DEFAULT_TASK)
    device = str(mlip_settings.get("device") or DEFAULT_DEVICE)
    dry_run = _resolve_dry_run(input_data, context)

    output["provenance"]["inputs"].append(str(poscar_path))
    output["data"].update(
        {
            "dry_run": dry_run,
            "model": model,
            "task": task,
            "device": device,
            "input_poscar": str(poscar_path),
            "result_path": str(result_path),
        }
    )

    if dry_run:
        payload = {
            "status": "skipped",
            "reason": "dry_run",
            "model": model,
            "task": task,
            "device": device,
            "input_poscar": str(poscar_path),
            "completed": False,
        }
        _write_json(result_path, payload)
        output["status"] = "skipped"
        output["artifacts"].append(str(result_path))
        output["provenance"]["generated_files"].append(str(result_path))
        output["messages"].append("Dry-run: UMA single-point calculation was not executed.")
        output["next_action"] = {
            "recommendation": "continue",
            "reason": "Run without dry-run when UMA execution is intended.",
        }
        return output

    if not poscar_path.exists():
        return _fail(output, "poscar_not_found", f"POSCAR not found: {poscar_path}")

    try:
        from ase.io import read  # type: ignore
    except ImportError as exc:
        return _write_dependency_failure(output, result_path, "ase_missing", exc)

    try:
        atoms = read(str(poscar_path), format="vasp")
        atoms.calc = _build_uma_calculator(model=model, task=task, device=device)
        energy = float(atoms.get_potential_energy())
        forces = _to_builtin(atoms.get_forces())
        max_force = _max_force(forces)
        stress = None
        try:
            stress = _to_builtin(atoms.get_stress())
        except Exception:  # noqa: BLE001 - stress may be unsupported by the calculator.
            stress = None
        payload = {
            "status": "success",
            "model": model,
            "task": task,
            "device": device,
            "input_poscar": str(poscar_path),
            "energy_eV": energy,
            "forces_eV_per_A": forces,
            "max_force_eV_per_A": max_force,
            "stress": stress,
            "atom_count": len(atoms),
            "completed": True,
            "timestamp_utc": _utc_now(),
        }
        _write_json(result_path, payload)
        output["status"] = "success"
        output["data"].update(payload)
        output["artifacts"].append(str(result_path))
        output["provenance"]["generated_files"].append(str(result_path))
        output["provenance"]["external_calls"].append(
            {
                "tool": "FAIRChem/UMA",
                "model": model,
                "task": task,
                "device": device,
                "timestamp_utc": payload["timestamp_utc"],
            }
        )
        output["next_action"] = {
            "recommendation": "continue",
            "reason": "UMA single-point result is available.",
        }
        return output
    except Exception as exc:  # noqa: BLE001 - keep structured diagnostics.
        payload = {
            "status": "failure",
            "model": model,
            "task": task,
            "device": device,
            "input_poscar": str(poscar_path),
            "completed": False,
            "error": {"code": "uma_singlepoint_failed", "message": str(exc)},
            "timestamp_utc": _utc_now(),
        }
        _write_json(result_path, payload)
        output["status"] = "failure"
        output["errors"].append(payload["error"])
        output["artifacts"].append(str(result_path))
        output["provenance"]["generated_files"].append(str(result_path))
        output["next_action"] = {
            "recommendation": "retry",
            "reason": "UMA single-point execution failed.",
        }
        return output


def _build_uma_calculator(model: str, task: str, device: str) -> Any:
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
        return FAIRChemCalculator(predictor, task_name=task)
    except TypeError:
        return FAIRChemCalculator(predictor, task=task)


def _write_dependency_failure(
    output: dict[str, Any],
    result_path: Path,
    code: str,
    exc: BaseException,
) -> dict[str, Any]:
    payload = {
        "status": "failure",
        "completed": False,
        "error": {
            "code": code,
            "message": f"Required dependency is unavailable: {exc}",
        },
        "timestamp_utc": _utc_now(),
    }
    _write_json(result_path, payload)
    output["status"] = "failure"
    output["errors"].append(payload["error"])
    output["artifacts"].append(str(result_path))
    output["provenance"]["generated_files"].append(str(result_path))
    output["next_action"] = {
        "recommendation": "retry",
        "reason": "Install the missing dependency in the UMA execution environment.",
    }
    return output


def _max_force(forces: Any) -> float:
    max_norm = 0.0
    for row in forces:
        norm = math.sqrt(sum(float(value) ** 2 for value in row[:3]))
        max_norm = max(max_norm, norm)
    return max_norm


def _to_builtin(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, tuple):
        return [_to_builtin(item) for item in value]
    if isinstance(value, list):
        return [_to_builtin(item) for item in value]
    try:
        if hasattr(value, "item"):
            return value.item()
    except Exception:  # noqa: BLE001 - best-effort conversion.
        pass
    return value


def _resolve_dry_run(input_data: dict[str, Any], context: dict[str, Any]) -> bool:
    if "dry_run" in context:
        return bool(context["dry_run"])
    if "dry_run" in input_data:
        return bool(input_data["dry_run"])
    return True


def _resolve_workdir(input_data: dict[str, Any], context: dict[str, Any]) -> Path:
    workdir = context.get("workdir") or input_data.get("workdir") or os.getcwd()
    return Path(workdir).expanduser().resolve()


def _resolve_path(path_value: str | os.PathLike[str], base: Path) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base / path).resolve()


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


def _fail(output: dict[str, Any], code: str, message: str) -> dict[str, Any]:
    output["status"] = "failure"
    output["errors"].append({"code": code, "message": message})
    output["next_action"] = {"recommendation": "needs_human_review", "reason": message}
    return output


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the fixed UMA single-point runner.")
    parser.add_argument("--input", required=True, help="Path to input JSON file.")
    parser.add_argument("--output", required=True, help="Path to output JSON file.")
    parser.add_argument("--workdir", help="Optional working directory.")
    parser.add_argument("--dry-run", action="store_true", help="Do not perform real external execution.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed logs.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    input_data = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
    context: dict[str, Any] = {}
    if args.workdir:
        context["workdir"] = args.workdir
    if args.dry_run:
        context["dry_run"] = True
    result = run(input_data, context)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.verbose:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"success", "partial", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
