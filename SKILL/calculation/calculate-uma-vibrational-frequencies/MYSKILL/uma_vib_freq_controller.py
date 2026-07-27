"""MESA calculate-uma-vibrational-frequencies controller."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_ID = "calculate-uma-vibrational-frequencies"
SKILL_NAME = "uma_vib_freq_controller"

FORBIDDEN_USER_SETTING_KEYS = {
    "model",
    "task_name",
    "task",
    "device",
    "indices",
    "atom_indices",
    "delta",
    "nfree",
    "vib_cache",
    "vib_cache_path",
    "output_freq",
    "frequency_output",
    "result_json",
    "log_file",
    "uma",
    "mlip_settings",
    "vibration",
    "vibration_settings",
}


def run(input_data: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve UMA vibration settings, execute the fixed runner, and return MESA output."""

    context = context or {}
    output = _mesa_output()
    workdir = _resolve_workdir(input_data, context)
    results_dir = workdir / "results"
    logs_dir = workdir / "logs"
    vib_cache_dir = workdir / "vib_cache"
    _ensure_dirs(results_dir, logs_dir, vib_cache_dir)

    forbidden = sorted(FORBIDDEN_USER_SETTING_KEYS.intersection(input_data))
    if forbidden:
        return _fail(
            output,
            "user_supplied_uma_vibration_settings",
            "The upstream input must provide only a POSCAR path; controller-owned settings were supplied: "
            + ", ".join(forbidden),
        )

    poscar_value = input_data.get("poscar_path") or input_data.get("input_poscar")
    if not poscar_value:
        return _fail(output, "missing_poscar_path", "Input must include poscar_path.")

    poscar_path = _resolve_path(poscar_value, workdir)
    output["provenance"]["inputs"].append(str(poscar_path))
    file_check = _check_poscar_file(poscar_path)
    if file_check["status"] != "pass":
        for error in file_check["errors"]:
            output["errors"].append(error)
        output["data"]["poscar_check"] = file_check
        output["next_action"] = {
            "recommendation": "stop",
            "reason": "The input POSCAR failed minimal file checks.",
        }
        return output

    execution_mode = _resolve_execution_mode(input_data, context)
    dry_run = _resolve_dry_run(input_data, context, execution_mode)
    task_dir = Path(__file__).resolve().parents[1]
    runner_path = task_dir / "EXTSKILL" / "uma_vib_freq_runner.py"
    qsub_script = task_dir / "EXTSKILL" / "scripts" / "run_uma_vib_freq.qsub.sh"
    config_path = results_dir / "resolved_uma_vib_config.json"
    result_path = results_dir / "uma_vib_freq.json"
    freq_path = workdir / "vib.freq"
    log_path = logs_dir / "uma_vib_freq.log"

    config = _resolve_uma_vib_config(
        poscar_path=poscar_path,
        workdir=workdir,
        execution_mode=execution_mode,
        dry_run=dry_run,
        file_check=file_check,
        qsub_script=qsub_script,
    )
    _write_json(config_path, config)

    runner_command = [
        sys.executable,
        str(runner_path),
    ]
    qsub_command = ["qsub", str(qsub_script)]

    output["data"].update(
        {
            "dry_run": dry_run,
            "execution_mode": "dry-run" if dry_run else execution_mode,
            "poscar_check": file_check,
            "frequency_output": {
                "format": "ASE vibration summary",
                "path": str(freq_path),
            },
            "result_json": str(result_path),
            "resolved_config": str(config_path),
            "vib_cache": str(vib_cache_dir),
            "settings": {
                "model": config["uma"]["model"],
                "task_name": config["uma"]["task_name"],
                "device": config["uma"]["device"],
                "indices": config["vibration"]["indices"],
                "delta": config["vibration"]["delta"],
                "nfree": config["vibration"]["nfree"],
            },
            "decision_basis": config["decision_basis"],
            "paths": {
                "workdir": str(workdir),
                "input_poscar": str(poscar_path),
                "vib_freq": str(freq_path),
                "result_json": str(result_path),
                "log": str(log_path),
                "vib_cache": str(vib_cache_dir),
                "qsub_script": str(qsub_script),
            },
            "runner_command": runner_command,
            "qsub_command": qsub_command,
        }
    )
    output["artifacts"].extend([str(config_path), str(qsub_script)])
    output["provenance"]["generated_files"].append(str(config_path))

    if not config["execution"]["launch_allowed"]:
        output["status"] = "failure"
        output["errors"].append(
            {
                "code": "structure_too_large_or_unresolved",
                "message": config["decision_basis"]["reason"],
            }
        )
        output["next_action"] = {
            "recommendation": "needs_human_review",
            "reason": config["decision_basis"]["reason"],
        }
        return output

    if dry_run:
        output["status"] = "success"
        output["messages"].append(
            "Dry-run completed: resolved UMA vibration settings and wrote results/resolved_uma_vib_config.json."
        )
        output["next_action"] = {
            "recommendation": "needs_execution",
            "reason": "Run in local/run or qsub/submit mode to generate vib.freq and results/uma_vib_freq.json.",
        }
        return output

    if execution_mode in {"qsub", "submit"}:
        return _submit_qsub(output, qsub_command, workdir, logs_dir)

    if execution_mode in {"local", "run"}:
        completed = _run_subprocess(runner_command, workdir)
        _write_process_log(log_path, runner_command, completed)
        output["artifacts"].append(str(log_path))
        output["provenance"]["generated_files"].append(str(log_path))
        output["provenance"]["external_calls"].append(
            {
                "tool": "fixed_runner",
                "command": runner_command,
                "timestamp_utc": _utc_now(),
                "returncode": completed.returncode,
            }
        )
        if completed.returncode != 0:
            runner_result = _read_json_if_exists(result_path)
            errors = _extract_errors(runner_result)
            output["status"] = "failure"
            output["errors"].extend(errors)
            if not errors:
                output["errors"].append(
                    {
                        "code": "runner_failed",
                        "message": completed.stderr.strip()
                        or completed.stdout.strip()
                        or "UMA vibration runner failed.",
                    }
                )
            output["next_action"] = {
                "recommendation": "retry",
                "reason": "The fixed UMA vibration runner returned a non-zero exit code.",
            }
            return output
        return _check_required_outputs(output, freq_path, result_path, vib_cache_dir, log_path)

    return _fail(
        output,
        "unsupported_execution_mode",
        f"Unsupported execution_mode: {execution_mode}. Use dry-run, local, run, qsub, or submit.",
    )


def _resolve_uma_vib_config(
    poscar_path: Path,
    workdir: Path,
    execution_mode: str,
    dry_run: bool,
    file_check: dict[str, Any],
    qsub_script: Path,
) -> dict[str, Any]:
    hints = _inspect_poscar_lightly(poscar_path)
    device, device_reason = _decide_device(execution_mode)
    vibration_decision = _decide_vibration_indices(hints)
    warnings = list(vibration_decision.get("warnings") or [])

    lower_poscar = str(poscar_path).lower()
    if "relax" not in lower_poscar:
        warnings.append(
            "No obvious relaxation provenance in the POSCAR path; calculate-uma-vibrational-frequencies assumes the structure is already relaxed."
        )

    decision_reasons = [
        "Defaulted to UMA model uma-s-1p1 for broad MESA frequency coverage.",
        "Defaulted to UMA task_name omat for crystal and materials structures.",
        device_reason,
        "Selected finite-difference displacement delta=0.01 and nfree=2 for a minimal ASE Vibrations workflow.",
        vibration_decision["reason"],
    ]

    return {
        "schema_version": 1,
        "task_id": TASK_ID,
        "controller": SKILL_NAME,
        "created_at_utc": _utc_now(),
        "workdir": str(workdir),
        "input_poscar": str(poscar_path),
        "output_freq": "vib.freq",
        "result_json": "results/uma_vib_freq.json",
        "log_file": "logs/uma_vib_freq.log",
        "vib_cache": "vib_cache/vib",
        "uma": {
            "model": "uma-s-1p1",
            "task_name": "omat",
            "device": device,
        },
        "vibration": {
            "indices": vibration_decision["indices"],
            "delta": 0.01,
            "nfree": 2,
        },
        "execution": {
            "mode": "dry-run" if dry_run else execution_mode,
            "qsub_script": str(qsub_script),
            "launch_allowed": vibration_decision["launch_allowed"],
        },
        "input_file_check": file_check,
        "poscar_hints": hints,
        "decision_basis": {
            "n_atoms": hints.get("atom_count"),
            "elements": hints.get("elements") or [],
            "structure_type": vibration_decision["structure_type"],
            "n_displaced_atoms": vibration_decision["n_displaced_atoms"],
            "reason": "Controller decided settings from POSCAR and runtime environment. "
            + vibration_decision["reason"],
            "warnings": warnings,
            "max_all_atom_vibration_atoms": _env_int("MESA_UMA_VIB_MAX_ALL_ATOMS", 30),
            "max_selected_vibration_atoms": _env_int("MESA_UMA_VIB_MAX_SELECTED_ATOMS", 36),
        },
        "decision_reasons": decision_reasons,
    }


def _decide_vibration_indices(hints: dict[str, Any]) -> dict[str, Any]:
    max_all_atoms = _env_int("MESA_UMA_VIB_MAX_ALL_ATOMS", 30)
    max_selected_atoms = _env_int("MESA_UMA_VIB_MAX_SELECTED_ATOMS", 36)
    n_atoms = hints.get("atom_count")
    movable_indices = [int(index) for index in hints.get("movable_indices") or []]
    has_vacuum = bool(hints.get("has_large_vacuum_axis"))
    warnings: list[str] = []

    if not isinstance(n_atoms, int) or n_atoms <= 0:
        return {
            "indices": [],
            "launch_allowed": False,
            "n_displaced_atoms": 0,
            "structure_type": "unknown",
            "reason": "Could not parse the POSCAR atom count, so the controller cannot estimate vibration cost.",
            "warnings": warnings,
        }

    if n_atoms <= max_all_atoms:
        structure_type = "molecule_or_small_cluster"
        if has_vacuum:
            structure_type = "surface_or_adsorbate_or_cluster"
        return {
            "indices": None,
            "launch_allowed": True,
            "n_displaced_atoms": n_atoms,
            "structure_type": structure_type,
            "reason": f"Selected all-atom vibration because n_atoms={n_atoms} is within the all-atom limit.",
            "warnings": warnings,
        }

    if movable_indices and len(movable_indices) <= max_selected_atoms:
        return {
            "indices": movable_indices,
            "launch_allowed": True,
            "n_displaced_atoms": len(movable_indices),
            "structure_type": "local_surface_or_adsorbate",
            "reason": "Selected POSCAR Selective Dynamics movable atoms for a local vibration calculation.",
            "warnings": warnings,
        }

    if n_atoms <= max_selected_atoms:
        warnings.append(
            "Atom count is above the all-atom comfort limit but below the selected-atom hard limit; using explicit all-index selection."
        )
        return {
            "indices": list(range(n_atoms)),
            "launch_allowed": True,
            "n_displaced_atoms": n_atoms,
            "structure_type": "medium_cluster_or_unknown",
            "reason": f"Selected all {n_atoms} atoms explicitly because the structure is still within the selected-atom limit.",
            "warnings": warnings,
        }

    if movable_indices:
        reason = (
            f"POSCAR has {len(movable_indices)} movable atoms, exceeding the selected-atom limit "
            f"of {max_selected_atoms}."
        )
    else:
        reason = (
            f"n_atoms={n_atoms} exceeds the selected-atom limit of {max_selected_atoms}, "
            "and no manageable Selective Dynamics movable subset was identified."
        )
    return {
        "indices": [],
        "launch_allowed": False,
        "n_displaced_atoms": 0,
        "structure_type": "bulk_or_slab_or_nanoparticle_or_large_unknown",
        "reason": reason,
        "warnings": warnings,
    }


def _check_required_outputs(
    output: dict[str, Any],
    freq_path: Path,
    result_path: Path,
    vib_cache_dir: Path,
    log_path: Path,
) -> dict[str, Any]:
    result = _read_json_if_exists(result_path)
    required = [freq_path, result_path, vib_cache_dir]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        output["status"] = "failure"
        output["errors"].append(
            {
                "code": "missing_required_outputs",
                "message": "Required UMA vibration outputs were not created: " + ", ".join(missing),
            }
        )
        output["next_action"] = {
            "recommendation": "retry",
            "reason": "Inspect logs/uma_vib_freq.log and rerun the fixed runner.",
        }
        return output

    if vib_cache_dir.is_dir() and not any(vib_cache_dir.iterdir()):
        output["status"] = "failure"
        output["errors"].append(
            {
                "code": "vib_cache_empty",
                "message": f"Vibration cache directory is empty: {vib_cache_dir}",
            }
        )
        output["next_action"] = {
            "recommendation": "retry",
            "reason": "ASE Vibrations did not leave finite-displacement cache files.",
        }
        return output

    if not result or result.get("status") != "success":
        output["status"] = "failure"
        output["errors"].extend(_extract_errors(result))
        if not output["errors"]:
            output["errors"].append(
                {
                    "code": "runner_result_not_success",
                    "message": "results/uma_vib_freq.json did not report success.",
                }
            )
        output["next_action"] = {
            "recommendation": "retry",
            "reason": "The fixed runner completed without a success result.",
        }
        return output

    output["status"] = "success"
    output["data"]["runner_result"] = result
    output["artifacts"].extend([str(freq_path), str(result_path), str(vib_cache_dir)])
    if log_path.exists():
        output["artifacts"].append(str(log_path))
    output["provenance"]["generated_files"].extend([str(freq_path), str(result_path), str(vib_cache_dir)])
    if log_path.exists():
        output["provenance"]["generated_files"].append(str(log_path))
    output["messages"].append("UMA vibrational frequency workflow completed.")
    output["next_action"] = {
        "recommendation": "continue",
        "reason": "vib.freq and results/uma_vib_freq.json are available.",
    }
    return output


def _submit_qsub(
    output: dict[str, Any],
    qsub_command: list[str],
    workdir: Path,
    logs_dir: Path,
) -> dict[str, Any]:
    try:
        completed = _run_subprocess(qsub_command, workdir)
    except OSError as exc:
        return _fail(output, "qsub_execution_failed", str(exc))

    qsub_log = logs_dir / "qsub_uma_vib_freq_submission.log"
    _write_process_log(qsub_log, qsub_command, completed)
    output["artifacts"].append(str(qsub_log))
    output["provenance"]["generated_files"].append(str(qsub_log))
    output["provenance"]["external_calls"].append(
        {
            "tool": "qsub",
            "command": qsub_command,
            "timestamp_utc": _utc_now(),
            "returncode": completed.returncode,
        }
    )
    output["data"]["qsub_returncode"] = completed.returncode
    output["data"]["qsub_stdout"] = completed.stdout.strip()
    output["data"]["qsub_stderr"] = completed.stderr.strip()
    output["data"]["qsub_job_id"] = _parse_qsub_job_id(completed.stdout)

    if completed.returncode != 0:
        output["status"] = "failure"
        output["errors"].append(
            {
                "code": "qsub_nonzero_return",
                "message": completed.stderr.strip() or "qsub returned a non-zero exit code.",
            }
        )
        output["next_action"] = {
            "recommendation": "retry",
            "reason": "qsub submission failed.",
        }
        return output

    output["status"] = "partial"
    output["messages"].append("qsub submission completed.")
    output["next_action"] = {
        "recommendation": "monitor",
        "reason": "Monitor the qsub job, then consume vib.freq and results/uma_vib_freq.json after completion.",
    }
    return output


def _check_poscar_file(poscar_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "pass",
        "checks": [],
        "errors": [],
        "metadata": {},
    }
    if not poscar_path.exists():
        return _file_check_fail(result, "poscar_not_found", f"POSCAR not found: {poscar_path}")
    if not poscar_path.is_file():
        return _file_check_fail(result, "poscar_not_file", f"POSCAR is not a file: {poscar_path}")
    try:
        size = poscar_path.stat().st_size
    except OSError as exc:
        return _file_check_fail(result, "poscar_stat_failed", str(exc))
    if size <= 0:
        return _file_check_fail(result, "poscar_empty", "POSCAR is empty.")
    try:
        with poscar_path.open("r", encoding="utf-8") as handle:
            sample = handle.read(4096)
    except UnicodeDecodeError:
        try:
            with poscar_path.open("r", encoding="latin-1") as handle:
                sample = handle.read(4096)
        except OSError as exc:
            return _file_check_fail(result, "poscar_unreadable", str(exc))
    except OSError as exc:
        return _file_check_fail(result, "poscar_unreadable", str(exc))
    if not sample.strip():
        return _file_check_fail(result, "poscar_empty", "POSCAR contains no non-whitespace text.")
    result["checks"].append({"name": "exists_non_empty_openable", "status": "pass"})
    result["metadata"]["size_bytes"] = size
    return result


def _inspect_poscar_lightly(poscar_path: Path) -> dict[str, Any]:
    hints: dict[str, Any] = {
        "selective_dynamics": False,
        "movable_indices": [],
        "atom_count": None,
        "elements": [],
        "counts": [],
        "comment": None,
        "lattice_lengths": [],
        "has_large_vacuum_axis": False,
    }
    try:
        text = poscar_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = poscar_path.read_text(encoding="latin-1")
    except OSError:
        return hints

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        hints["comment"] = lines[0]
    if len(lines) < 7:
        return hints

    scale = _parse_float(lines[1].split()[0]) if len(lines) > 1 and lines[1].split() else 1.0
    scale = abs(scale or 1.0)
    lattice_vectors = [_parse_vector(line) for line in lines[2:5]]
    lattice_lengths = [_vector_length(vector, scale) for vector in lattice_vectors if vector is not None]
    hints["lattice_lengths"] = lattice_lengths
    if lattice_lengths:
        shortest = min(length for length in lattice_lengths if length > 0) if any(length > 0 for length in lattice_lengths) else 0
        longest = max(lattice_lengths)
        hints["has_large_vacuum_axis"] = bool(longest >= 18.0 and shortest > 0 and longest / shortest >= 2.0)

    species_line_tokens = lines[5].split()
    if _tokens_are_ints(species_line_tokens):
        elements = [f"type_{index + 1}" for index in range(len(species_line_tokens))]
        counts_line_index = 5
    else:
        elements = species_line_tokens
        counts_line_index = 6
    try:
        counts = [int(token) for token in lines[counts_line_index].split()]
    except (ValueError, IndexError):
        return hints

    n_atoms = sum(counts)
    hints["elements"] = elements
    hints["counts"] = counts
    hints["atom_count"] = n_atoms

    coord_mode_index = counts_line_index + 1
    if coord_mode_index < len(lines) and lines[coord_mode_index].lower().startswith("s"):
        hints["selective_dynamics"] = True
        coord_mode_index += 1

    positions_start = coord_mode_index + 1
    movable_indices: list[int] = []
    if hints["selective_dynamics"]:
        for atom_index in range(n_atoms):
            line_index = positions_start + atom_index
            if line_index >= len(lines):
                break
            tokens = lines[line_index].split()
            flags = tokens[3:6]
            if flags and any(flag.upper().startswith("T") for flag in flags):
                movable_indices.append(atom_index)
    hints["movable_indices"] = movable_indices
    return hints


def _decide_device(execution_mode: str) -> tuple[str, str]:
    explicit = os.environ.get("MESA_UMA_DEVICE")
    if explicit:
        return explicit, "Selected device from MESA_UMA_DEVICE."

    cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if cuda_visible and cuda_visible.strip() not in {"", "-1", "none", "None"}:
        return "cuda", "Selected cuda because CUDA_VISIBLE_DEVICES is set."

    if execution_mode in {"qsub", "submit"}:
        return "cuda", "Selected cuda for qsub execution so the compute environment can provide the GPU."

    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            return "cuda", "Selected cuda because torch reports an available CUDA device."
    except Exception:  # noqa: BLE001 - device selection must remain best effort.
        pass

    return "cpu", "Selected cpu because no CUDA runtime was visible to the controller."


def _resolve_execution_mode(input_data: dict[str, Any], context: dict[str, Any]) -> str:
    execution = input_data.get("execution") or {}
    mode = (
        context.get("execution_mode")
        or context.get("mode")
        or input_data.get("execution_mode")
        or input_data.get("mode")
        or execution.get("mode")
        or "local"
    )
    return str(mode).lower()


def _resolve_dry_run(input_data: dict[str, Any], context: dict[str, Any], execution_mode: str) -> bool:
    if "dry_run" in context:
        return bool(context["dry_run"])
    if "dry-run" in context:
        return bool(context["dry-run"])
    if "dry_run" in input_data:
        return bool(input_data["dry_run"])
    if "dry-run" in input_data:
        return bool(input_data["dry-run"])
    return execution_mode == "dry-run"


def _resolve_workdir(input_data: dict[str, Any], context: dict[str, Any]) -> Path:
    workdir = context.get("workdir") or input_data.get("workdir") or os.getcwd()
    return Path(workdir).expanduser().resolve()


def _resolve_path(path_value: str | os.PathLike[str], base: Path) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base / path).resolve()


def _run_subprocess(command: list[str], workdir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(workdir),
        check=False,
        capture_output=True,
        text=True,
    )


def _write_process_log(path: Path, command: list[str], completed: subprocess.CompletedProcess[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "COMMAND: "
        + " ".join(command)
        + "\nRETURN_CODE: "
        + str(completed.returncode)
        + "\nSTDOUT:\n"
        + completed.stdout
        + "\nSTDERR:\n"
        + completed.stderr,
        encoding="utf-8",
    )


def _extract_errors(payload: dict[str, Any] | None) -> list[dict[str, str]]:
    if not payload:
        return []
    raw_errors = payload.get("errors") or []
    errors: list[dict[str, str]] = []
    for raw_error in raw_errors:
        if isinstance(raw_error, dict):
            code = str(raw_error.get("code") or raw_error.get("type") or "runner_error")
            message = str(raw_error.get("message") or raw_error)
            errors.append({"code": code, "message": message})
        else:
            errors.append({"code": "runner_error", "message": str(raw_error)})
    return errors


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _parse_qsub_job_id(stdout: str) -> str | None:
    stripped = stdout.strip()
    if not stripped:
        return None
    return stripped.split()[0]


def _tokens_are_ints(tokens: list[str]) -> bool:
    if not tokens:
        return False
    try:
        for token in tokens:
            int(token)
    except ValueError:
        return False
    return True


def _parse_float(token: str) -> float | None:
    try:
        return float(token)
    except ValueError:
        return None


def _parse_vector(line: str) -> tuple[float, float, float] | None:
    tokens = line.split()
    if len(tokens) < 3:
        return None
    values = [_parse_float(token) for token in tokens[:3]]
    if any(value is None for value in values):
        return None
    return values[0], values[1], values[2]  # type: ignore[return-value]


def _vector_length(vector: tuple[float, float, float], scale: float) -> float:
    return math.sqrt(sum((scale * value) ** 2 for value in vector))


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _file_check_fail(result: dict[str, Any], code: str, message: str) -> dict[str, Any]:
    result["status"] = "fail"
    result["errors"].append({"code": code, "message": message})
    return result


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


def _fail(output: dict[str, Any], code: str, message: str) -> dict[str, Any]:
    output["status"] = "failure"
    output["errors"].append({"code": code, "message": message})
    output["next_action"] = {"recommendation": "needs_human_review", "reason": message}
    return output


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MESA UMA vibrational frequency controller.")
    parser.add_argument("--input", required=True, help="Path to controller input JSON.")
    parser.add_argument("--output", required=True, help="Path to controller output JSON.")
    parser.add_argument("--workdir", help="Working directory for task artifacts.")
    parser.add_argument("--execution-mode", choices=["dry-run", "local", "run", "qsub", "submit"])
    parser.add_argument("--dry-run", action="store_true", help="Resolve settings without running UMA.")
    parser.add_argument("--verbose", action="store_true", help="Print output JSON to stdout.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    input_data = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
    context: dict[str, Any] = {}
    if args.workdir:
        context["workdir"] = args.workdir
    if args.execution_mode:
        context["execution_mode"] = args.execution_mode
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
