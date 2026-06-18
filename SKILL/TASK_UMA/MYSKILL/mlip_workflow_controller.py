"""MESA TASK_MLIP_DFT_HANDOFF workflow controller."""

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


TASK_ID = "TASK_MLIP_DFT_HANDOFF"
SKILL_NAME = "mlip_workflow_controller"

DEFAULT_SETTINGS: dict[str, Any] = {
    "model": "uma-s-1p2",
    "task": "omat",
    "device": "cuda",
    "relax_type": "geometry",
    "fmax": 0.05,
    "steps": 300,
}

VALID_ELEMENTS = {
    "H",
    "He",
    "Li",
    "Be",
    "B",
    "C",
    "N",
    "O",
    "F",
    "Ne",
    "Na",
    "Mg",
    "Al",
    "Si",
    "P",
    "S",
    "Cl",
    "Ar",
    "K",
    "Ca",
    "Sc",
    "Ti",
    "V",
    "Cr",
    "Mn",
    "Fe",
    "Co",
    "Ni",
    "Cu",
    "Zn",
    "Ga",
    "Ge",
    "As",
    "Se",
    "Br",
    "Kr",
    "Rb",
    "Sr",
    "Y",
    "Zr",
    "Nb",
    "Mo",
    "Tc",
    "Ru",
    "Rh",
    "Pd",
    "Ag",
    "Cd",
    "In",
    "Sn",
    "Sb",
    "Te",
    "I",
    "Xe",
    "Cs",
    "Ba",
    "La",
    "Ce",
    "Pr",
    "Nd",
    "Pm",
    "Sm",
    "Eu",
    "Gd",
    "Tb",
    "Dy",
    "Ho",
    "Er",
    "Tm",
    "Yb",
    "Lu",
    "Hf",
    "Ta",
    "W",
    "Re",
    "Os",
    "Ir",
    "Pt",
    "Au",
    "Hg",
    "Tl",
    "Pb",
    "Bi",
    "Po",
    "At",
    "Rn",
    "Fr",
    "Ra",
    "Ac",
    "Th",
    "Pa",
    "U",
    "Np",
    "Pu",
    "Am",
    "Cm",
    "Bk",
    "Cf",
    "Es",
    "Fm",
    "Md",
    "No",
    "Lr",
    "Rf",
    "Db",
    "Sg",
    "Bh",
    "Hs",
    "Mt",
    "Ds",
    "Rg",
    "Cn",
    "Nh",
    "Fl",
    "Mc",
    "Lv",
    "Ts",
    "Og",
}


def run(input_data: dict, context: dict | None = None) -> dict:
    """
    Execute the MLIP-to-DFT handoff workflow.

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
    output = _mesa_output(SKILL_NAME)
    workdir = _resolve_workdir(input_data, context)
    results_dir = workdir / "results"
    optimized_dir = workdir / "optimized"
    logs_dir = workdir / "logs"
    _ensure_dirs(results_dir, optimized_dir, logs_dir)

    poscar_value = input_data.get("poscar_path") or input_data.get("input_poscar")
    if not poscar_value:
        return _fail(
            output,
            "missing_poscar_path",
            "Input must include poscar_path or input_poscar.",
        )

    poscar_path = _resolve_path(poscar_value, workdir)
    optimized_poscar = optimized_dir / "POSCAR"
    settings = _resolve_settings(input_data)
    execution_mode = _resolve_execution_mode(input_data)
    dry_run = _resolve_dry_run(input_data, context, execution_mode)
    task_dir = Path(__file__).resolve().parents[1]
    qsub_script = task_dir / "EXTSKILL" / "scripts" / "run_mlip_dft_handoff.qsub.sh"
    singlepoint_runner = task_dir / "EXTSKILL" / "uma_singlepoint_runner.py"
    relaxation_runner = task_dir / "EXTSKILL" / "uma_relaxation_runner.py"
    qsub_command = _build_qsub_command(
        qsub_script=qsub_script,
        input_poscar=poscar_path,
        output_poscar=optimized_poscar,
        settings=settings,
    )

    validation = validate_poscar(poscar_path)
    output["provenance"]["inputs"].append(str(poscar_path))
    output["data"].update(
        {
            "dry_run": dry_run,
            "execution_mode": "dry-run" if dry_run else execution_mode,
            "settings": settings,
            "paths": {
                "workdir": str(workdir),
                "input_poscar": str(poscar_path),
                "optimized_poscar": str(optimized_poscar),
                "results_dir": str(results_dir),
                "logs_dir": str(logs_dir),
                "qsub_script": str(qsub_script),
            },
            "workflow_steps": [
                "structure_validation",
                "uma_singlepoint",
                "uma_relaxation",
                "mlip_uncertainty_guard",
                "dft_handoff_builder",
            ],
            "qsub_command": qsub_command,
            "structure_validation": validation,
        }
    )

    if validation["status"] == "fail":
        uncertainty_report = _assess_reliability(
            validation=validation,
            singlepoint=None,
            relaxation=None,
            fmax=float(settings["fmax"]),
        )
        uncertainty_path = _write_json(
            results_dir / "mlip_uncertainty_report.json", uncertainty_report
        )
        handoff_path = _write_handoff_summary(
            results_dir / "dft_handoff_summary.json",
            settings=settings,
            optimized_poscar=optimized_poscar,
            reliability=uncertainty_report,
            singlepoint=None,
            relaxation=None,
        )
        output["artifacts"].extend([str(uncertainty_path), str(handoff_path)])
        output["provenance"]["generated_files"].extend(
            [str(uncertainty_path), str(handoff_path)]
        )
        for error in validation["errors"]:
            output["errors"].append(error)
        output["status"] = "failure"
        output["next_action"] = {
            "recommendation": "needs_human_review",
            "reason": "Input POSCAR failed the structure guard.",
        }
        return output

    if dry_run:
        uncertainty_report = _assess_reliability(
            validation=validation,
            singlepoint=None,
            relaxation=None,
            fmax=float(settings["fmax"]),
        )
        uncertainty_path = _write_json(
            results_dir / "mlip_uncertainty_report.json", uncertainty_report
        )
        handoff_path = _write_handoff_summary(
            results_dir / "dft_handoff_summary.json",
            settings=settings,
            optimized_poscar=optimized_poscar,
            reliability=uncertainty_report,
            singlepoint=None,
            relaxation=None,
        )
        output["status"] = "success"
        output["messages"].append(
            "Dry-run completed: validated the POSCAR and generated the qsub plan."
        )
        output["artifacts"].extend([str(uncertainty_path), str(handoff_path), str(qsub_script)])
        output["provenance"]["generated_files"].extend(
            [str(uncertainty_path), str(handoff_path)]
        )
        output["next_action"] = {
            "recommendation": "needs_human_review",
            "reason": "Submit the planned qsub command to generate optimized/POSCAR.",
        }
        return output

    if execution_mode in {"qsub", "submit"}:
        return _submit_qsub(output, qsub_command, workdir, logs_dir, results_dir, settings, optimized_poscar)

    if execution_mode in {"local", "run"}:
        return _run_local_fixed_runners(
            output=output,
            python_executable=sys.executable,
            singlepoint_runner=singlepoint_runner,
            relaxation_runner=relaxation_runner,
            poscar_path=poscar_path,
            optimized_poscar=optimized_poscar,
            workdir=workdir,
            results_dir=results_dir,
            logs_dir=logs_dir,
            settings=settings,
        )

    output["status"] = "failure"
    output["errors"].append(
        {
            "code": "unsupported_execution_mode",
            "message": f"Unsupported execution mode: {execution_mode}",
        }
    )
    output["next_action"] = {
        "recommendation": "needs_human_review",
        "reason": "Use dry-run, qsub, submit, local, or run.",
    }
    return output


def validate_poscar(poscar_path: Path) -> dict[str, Any]:
    """Run structure-guard checks without modifying the POSCAR."""

    result: dict[str, Any] = {
        "status": "pass",
        "safe_to_continue": True,
        "checks": [],
        "warnings": [],
        "errors": [],
        "metadata": {},
    }

    if not poscar_path.exists():
        return _validation_fail(result, "poscar_not_found", f"POSCAR not found: {poscar_path}")
    if not poscar_path.is_file():
        return _validation_fail(result, "poscar_not_file", f"POSCAR is not a file: {poscar_path}")

    try:
        text = poscar_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = poscar_path.read_text(encoding="latin-1")
    except OSError as exc:
        return _validation_fail(result, "poscar_unreadable", str(exc))

    if not text.strip():
        return _validation_fail(result, "poscar_empty", "POSCAR is empty.")
    result["checks"].append({"name": "file_readable_non_empty", "status": "pass"})

    fallback = _parse_poscar_basic(text)
    if fallback["status"] == "fail":
        for error in fallback["errors"]:
            result = _validation_fail(result, error["code"], error["message"])
        return result

    result["metadata"].update(fallback["metadata"])
    result["checks"].extend(fallback["checks"])
    result["warnings"].extend(fallback["warnings"])

    ase_result = _try_ase_parse(poscar_path)
    result["checks"].append(ase_result["check"])
    if ase_result.get("metadata"):
        result["metadata"].update(ase_result["metadata"])
    if ase_result["check"]["status"] == "fail":
        result = _validation_fail(
            result,
            "ase_parse_failed",
            ase_result["check"]["message"],
        )
    elif ase_result["check"]["status"] == "warning":
        result["warnings"].append(
            {
                "code": "ase_unavailable",
                "message": "ASE is not installed; POSCAR validation used the built-in parser only.",
            }
        )

    if result["errors"]:
        result["status"] = "fail"
        result["safe_to_continue"] = False
    elif result["warnings"]:
        result["status"] = "warning"
    return result


def _submit_qsub(
    output: dict[str, Any],
    qsub_command: list[str],
    workdir: Path,
    logs_dir: Path,
    results_dir: Path,
    settings: dict[str, Any],
    optimized_poscar: Path,
) -> dict[str, Any]:
    external_call = {
        "tool": "qsub",
        "command": qsub_command,
        "timestamp_utc": _utc_now(),
    }
    output["provenance"]["external_calls"].append(external_call)
    try:
        completed = subprocess.run(
            qsub_command,
            cwd=str(workdir),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        output["status"] = "failure"
        output["errors"].append({"code": "qsub_execution_failed", "message": str(exc)})
        output["next_action"] = {
            "recommendation": "retry",
            "reason": "qsub could not be executed in this environment.",
        }
        return output

    qsub_log = logs_dir / "qsub_submission.log"
    qsub_log.write_text(
        "COMMAND: "
        + " ".join(qsub_command)
        + "\nRETURN_CODE: "
        + str(completed.returncode)
        + "\nSTDOUT:\n"
        + completed.stdout
        + "\nSTDERR:\n"
        + completed.stderr,
        encoding="utf-8",
    )
    output["artifacts"].append(str(qsub_log))
    output["provenance"]["generated_files"].append(str(qsub_log))
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

    singlepoint = _read_json_if_exists(results_dir / "uma_singlepoint.json")
    relaxation = _read_json_if_exists(results_dir / "uma_relaxation.json")
    reliability = _assess_reliability(
        validation=output["data"]["structure_validation"],
        singlepoint=singlepoint,
        relaxation=relaxation,
        fmax=float(settings["fmax"]),
    )
    uncertainty_path = _write_json(results_dir / "mlip_uncertainty_report.json", reliability)
    handoff_path = _write_handoff_summary(
        results_dir / "dft_handoff_summary.json",
        settings=settings,
        optimized_poscar=optimized_poscar,
        reliability=reliability,
        singlepoint=singlepoint,
        relaxation=relaxation,
    )
    output["artifacts"].extend([str(uncertainty_path), str(handoff_path)])
    output["provenance"]["generated_files"].extend([str(uncertainty_path), str(handoff_path)])
    output["data"]["reliability"] = reliability
    output["status"] = "partial" if reliability["status"] == "unknown" else "success"
    output["messages"].append("qsub submission completed.")
    output["next_action"] = {
        "recommendation": "continue",
        "reason": "Monitor the qsub job and consume optimized/POSCAR after completion.",
    }
    return output


def _run_local_fixed_runners(
    output: dict[str, Any],
    python_executable: str,
    singlepoint_runner: Path,
    relaxation_runner: Path,
    poscar_path: Path,
    optimized_poscar: Path,
    workdir: Path,
    results_dir: Path,
    logs_dir: Path,
    settings: dict[str, Any],
) -> dict[str, Any]:
    sp_input = results_dir / "uma_singlepoint.input.json"
    sp_output = results_dir / "uma_singlepoint.mesa_output.json"
    relax_input = results_dir / "uma_relaxation.input.json"
    relax_output = results_dir / "uma_relaxation.mesa_output.json"
    _write_json(
        sp_input,
        {
            "poscar_path": str(poscar_path),
            "mlip_settings": {
                "model": settings["model"],
                "task": settings["task"],
                "device": settings["device"],
            },
            "results_dir": str(results_dir),
            "dry_run": False,
        },
    )
    _write_json(
        relax_input,
        {
            "poscar_path": str(poscar_path),
            "output_poscar": str(optimized_poscar),
            "mlip_settings": {
                "model": settings["model"],
                "task": settings["task"],
                "device": settings["device"],
            },
            "relaxation_settings": {
                "relax_type": settings["relax_type"],
                "fmax": settings["fmax"],
                "steps": settings["steps"],
            },
            "results_dir": str(results_dir),
            "logs_dir": str(logs_dir),
            "dry_run": False,
        },
    )

    commands = [
        [python_executable, str(singlepoint_runner), "--input", str(sp_input), "--output", str(sp_output), "--workdir", str(workdir)],
        [python_executable, str(relaxation_runner), "--input", str(relax_input), "--output", str(relax_output), "--workdir", str(workdir)],
    ]
    for command in commands:
        output["provenance"]["external_calls"].append(
            {"tool": "fixed_runner", "command": command, "timestamp_utc": _utc_now()}
        )
        completed = subprocess.run(
            command,
            cwd=str(workdir),
            check=False,
            capture_output=True,
            text=True,
        )
        runner_log = logs_dir / (Path(command[1]).stem + ".controller.log")
        runner_log.write_text(
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
        output["artifacts"].append(str(runner_log))
        output["provenance"]["generated_files"].append(str(runner_log))
        if completed.returncode != 0:
            runner_output = _read_json_if_exists(Path(command[5]))
            runner_errors = runner_output.get("errors", []) if runner_output else []
            runner_message = "; ".join(
                str(error.get("message", error)) for error in runner_errors
            )
            output["status"] = "failure"
            output["errors"].append(
                {
                    "code": "fixed_runner_failed",
                    "message": f"{Path(command[1]).name} failed: {runner_message or completed.stderr.strip()}",
                }
            )
            output["next_action"] = {
                "recommendation": "retry",
                "reason": "A fixed UMA runner failed during local execution.",
            }
            return output

    singlepoint = _read_json_if_exists(results_dir / "uma_singlepoint.json")
    relaxation = _read_json_if_exists(results_dir / "uma_relaxation.json")
    reliability = _assess_reliability(
        validation=output["data"]["structure_validation"],
        singlepoint=singlepoint,
        relaxation=relaxation,
        fmax=float(settings["fmax"]),
    )
    uncertainty_path = _write_json(results_dir / "mlip_uncertainty_report.json", reliability)
    handoff_path = _write_handoff_summary(
        results_dir / "dft_handoff_summary.json",
        settings=settings,
        optimized_poscar=optimized_poscar,
        reliability=reliability,
        singlepoint=singlepoint,
        relaxation=relaxation,
    )
    output["artifacts"].extend([str(uncertainty_path), str(handoff_path)])
    output["provenance"]["generated_files"].extend([str(uncertainty_path), str(handoff_path)])
    output["data"]["reliability"] = reliability
    output["status"] = "success" if reliability["status"] in {"pass", "warning"} else "partial"
    output["next_action"] = _next_action_for_reliability(reliability, optimized_poscar)
    return output


def _assess_reliability(
    validation: dict[str, Any],
    singlepoint: dict[str, Any] | None,
    relaxation: dict[str, Any] | None,
    fmax: float,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "status": "unknown",
        "checks": [],
        "warnings": [],
        "errors": [],
        "summary": "",
    }

    if validation.get("safe_to_continue") is False or validation.get("status") == "fail":
        report["status"] = "fail"
        report["errors"].append(
            {"code": "structure_guard_failed", "message": "Input structure is not safe for MLIP."}
        )
        report["summary"] = "Structure validation failed before MLIP execution."
        return report

    if singlepoint is None and relaxation is None:
        report["checks"].append({"name": "runner_outputs_present", "status": "unknown"})
        report["summary"] = "UMA runner outputs are not available yet."
        return report

    if singlepoint is None:
        report["warnings"].append(
            {"code": "singlepoint_missing", "message": "results/uma_singlepoint.json was not found."}
        )
    else:
        sp_status = singlepoint.get("status")
        report["checks"].append({"name": "singlepoint_completed", "status": sp_status})
        energy = singlepoint.get("energy_eV")
        max_force = singlepoint.get("max_force_eV_per_A")
        if sp_status != "success":
            report["errors"].append(
                {"code": "singlepoint_failed", "message": "UMA single-point did not complete successfully."}
            )
        if not _is_finite_number(energy):
            report["errors"].append(
                {"code": "invalid_singlepoint_energy", "message": "Single-point energy is missing or non-finite."}
            )
        if not _is_finite_number(max_force):
            report["errors"].append(
                {"code": "invalid_singlepoint_forces", "message": "Single-point max force is missing or non-finite."}
            )

    if relaxation is None:
        report["warnings"].append(
            {"code": "relaxation_missing", "message": "results/uma_relaxation.json was not found."}
        )
    else:
        relax_status = relaxation.get("status")
        report["checks"].append({"name": "relaxation_completed", "status": relax_status})
        final_force = relaxation.get("final_max_force_eV_per_A")
        converged = bool(relaxation.get("converged"))
        atom_count_preserved = relaxation.get("atom_count_preserved")
        collapsed = relaxation.get("structure_collapsed")
        if relax_status != "success":
            report["errors"].append(
                {"code": "relaxation_failed", "message": "UMA relaxation did not complete successfully."}
            )
        if not _is_finite_number(final_force):
            report["errors"].append(
                {"code": "invalid_relaxation_force", "message": "Final max force is missing or non-finite."}
            )
        elif float(final_force) > fmax:
            report["warnings"].append(
                {
                    "code": "relaxation_not_below_threshold",
                    "message": f"Final max force {final_force} exceeds fmax {fmax}.",
                }
            )
        if not converged:
            report["warnings"].append(
                {"code": "relaxation_not_converged", "message": "ASE optimizer did not report convergence."}
            )
        if atom_count_preserved is False:
            report["errors"].append(
                {"code": "atom_count_changed", "message": "Relaxation changed the atom count."}
            )
        if collapsed is True:
            report["errors"].append(
                {"code": "structure_collapsed", "message": "Relaxed structure appears collapsed."}
            )

    if report["errors"]:
        report["status"] = "fail"
        report["summary"] = "MLIP reliability checks failed."
    elif report["warnings"]:
        report["status"] = "warning"
        report["summary"] = "MLIP reliability checks completed with warnings."
    else:
        report["status"] = "pass"
        report["summary"] = "MLIP reliability checks passed."
    return report


def _write_handoff_summary(
    path: Path,
    settings: dict[str, Any],
    optimized_poscar: Path,
    reliability: dict[str, Any],
    singlepoint: dict[str, Any] | None,
    relaxation: dict[str, Any] | None,
) -> Path:
    ready = optimized_poscar.exists() and reliability.get("status") == "pass"
    summary = {
        "status": "ready" if ready else "not_ready",
        "task_id": TASK_ID,
        "downstream_artifact": str(optimized_poscar),
        "optimized_poscar_exists": optimized_poscar.exists(),
        "recommended_next_skill": "generate_vasp_inputs" if ready else None,
        "mlip": {
            "model": settings["model"],
            "task": settings["task"],
            "device": settings["device"],
            "relax_type": settings["relax_type"],
            "fmax": settings["fmax"],
            "steps": settings["steps"],
            "energy_eV": None if not singlepoint else singlepoint.get("energy_eV"),
            "singlepoint_max_force_eV_per_A": None
            if not singlepoint
            else singlepoint.get("max_force_eV_per_A"),
            "final_max_force_eV_per_A": None
            if not relaxation
            else relaxation.get("final_max_force_eV_per_A"),
            "converged": None if not relaxation else relaxation.get("converged"),
            "reliability_status": reliability.get("status"),
        },
        "reliability": reliability,
        "notes": [
            "This TASK does not generate INCAR, KPOINTS, POTCAR, or VASP job folders.",
            "The final downstream structure artifact is optimized/POSCAR.",
        ],
    }
    return _write_json(path, summary)


def _next_action_for_reliability(reliability: dict[str, Any], optimized_poscar: Path) -> dict[str, str]:
    if optimized_poscar.exists() and reliability.get("status") == "pass":
        return {
            "recommendation": "continue",
            "reason": "optimized/POSCAR is ready for downstream VASP input generation.",
        }
    if reliability.get("status") == "warning":
        return {
            "recommendation": "needs_human_review",
            "reason": "MLIP completed with reliability warnings before DFT handoff.",
        }
    if reliability.get("status") == "fail":
        return {
            "recommendation": "stop",
            "reason": "MLIP reliability checks failed.",
        }
    return {
        "recommendation": "needs_human_review",
        "reason": "Runner outputs are not available yet.",
    }


def _parse_poscar_basic(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "pass", "checks": [], "warnings": [], "errors": [], "metadata": {}}
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 8:
        result["status"] = "fail"
        result["errors"].append(
            {"code": "poscar_too_short", "message": "POSCAR has too few non-empty lines."}
        )
        return result

    try:
        scale = float(lines[1].split()[0])
        lattice = [[float(x) * scale for x in lines[i].split()[:3]] for i in range(2, 5)]
    except (ValueError, IndexError) as exc:
        result["status"] = "fail"
        result["errors"].append(
            {"code": "invalid_lattice", "message": f"Could not parse POSCAR lattice: {exc}"}
        )
        return result

    volume = abs(_determinant_3x3(lattice))
    result["metadata"]["cell_volume_A3"] = volume
    if volume <= 0.0 or not math.isfinite(volume):
        result["status"] = "fail"
        result["errors"].append(
            {"code": "invalid_cell_volume", "message": "Cell volume must be positive and finite."}
        )
        return result
    result["checks"].append({"name": "positive_cell_volume", "status": "pass", "value": volume})

    species_tokens = lines[5].split()
    if _tokens_are_ints(species_tokens):
        elements: list[str] = []
        counts_tokens = species_tokens
        counts_line_idx = 5
    else:
        elements = species_tokens
        counts_line_idx = 6
        if len(lines) <= counts_line_idx:
            result["status"] = "fail"
            result["errors"].append(
                {"code": "missing_atom_counts", "message": "POSCAR is missing atom counts."}
            )
            return result
        counts_tokens = lines[counts_line_idx].split()

    if elements and any(element not in VALID_ELEMENTS for element in elements):
        result["status"] = "fail"
        result["errors"].append(
            {"code": "invalid_element_symbol", "message": f"Invalid POSCAR element labels: {elements}"}
        )
        return result
    if elements:
        result["checks"].append({"name": "valid_elements", "status": "pass", "value": elements})
    else:
        result["warnings"].append(
            {
                "code": "unknown_element_labels",
                "message": "POSCAR appears to use VASP 4 format; element labels were not checked.",
            }
        )

    try:
        counts = [int(token) for token in counts_tokens]
    except ValueError as exc:
        result["status"] = "fail"
        result["errors"].append(
            {"code": "invalid_atom_counts", "message": f"Could not parse atom counts: {exc}"}
        )
        return result

    if any(count < 0 for count in counts):
        result["status"] = "fail"
        result["errors"].append(
            {"code": "negative_atom_count", "message": "POSCAR atom counts must be non-negative."}
        )
        return result

    atom_count = sum(counts)
    result["metadata"]["atom_count"] = atom_count
    result["metadata"]["elements"] = elements
    result["metadata"]["atom_counts"] = counts
    if atom_count <= 0:
        result["status"] = "fail"
        result["errors"].append(
            {"code": "zero_atom_count", "message": "POSCAR must contain at least one atom."}
        )
        return result
    result["checks"].append({"name": "positive_atom_count", "status": "pass", "value": atom_count})

    coord_mode_idx = counts_line_idx + 1
    if coord_mode_idx < len(lines) and lines[coord_mode_idx].lower().startswith("s"):
        coord_mode_idx += 1
    if coord_mode_idx >= len(lines):
        result["status"] = "fail"
        result["errors"].append(
            {"code": "missing_coordinate_mode", "message": "POSCAR is missing coordinate mode."}
        )
        return result

    coord_mode = lines[coord_mode_idx].lower()
    coord_start = coord_mode_idx + 1
    coord_lines = lines[coord_start : coord_start + atom_count]
    if len(coord_lines) < atom_count:
        result["status"] = "fail"
        result["errors"].append(
            {"code": "missing_coordinates", "message": "POSCAR has fewer coordinates than atom counts require."}
        )
        return result

    coords = _parse_positions(coord_lines, coord_mode, lattice, scale)
    if coords:
        min_distance = _minimum_pair_distance(coords)
        result["metadata"]["minimum_pair_distance_A"] = min_distance
        if min_distance is not None and min_distance < 0.35:
            result["status"] = "fail"
            result["errors"].append(
                {
                    "code": "impossible_interatomic_distance",
                    "message": f"Minimum pair distance {min_distance:.3f} A is below 0.35 A.",
                }
            )
            return result
        result["checks"].append(
            {"name": "minimum_pair_distance", "status": "pass", "value": min_distance}
        )
    else:
        result["warnings"].append(
            {
                "code": "coordinate_parse_skipped",
                "message": "Could not parse coordinates for distance sanity check.",
            }
        )
    return result


def _try_ase_parse(poscar_path: Path) -> dict[str, Any]:
    try:
        from ase.io import read  # type: ignore
    except ImportError:
        return {
            "check": {
                "name": "ase_parse",
                "status": "warning",
                "message": "ASE is not installed.",
            }
        }

    try:
        atoms = read(str(poscar_path), format="vasp")
        return {
            "check": {"name": "ase_parse", "status": "pass"},
            "metadata": {
                "ase_atom_count": len(atoms),
                "ase_cell_volume_A3": float(atoms.get_volume()),
            },
        }
    except Exception as exc:  # noqa: BLE001 - report parser diagnostics to caller.
        return {
            "check": {
                "name": "ase_parse",
                "status": "fail",
                "message": str(exc),
            }
        }


def _parse_positions(
    coord_lines: list[str],
    coord_mode: str,
    lattice: list[list[float]],
    scale: float,
) -> list[list[float]]:
    coords: list[list[float]] = []
    direct = coord_mode.startswith("d")
    cartesian = coord_mode.startswith("c") or coord_mode.startswith("k")
    if not direct and not cartesian:
        return coords

    try:
        for line in coord_lines:
            values = [float(value) for value in line.split()[:3]]
            if direct:
                coords.append(
                    [
                        values[0] * lattice[0][axis]
                        + values[1] * lattice[1][axis]
                        + values[2] * lattice[2][axis]
                        for axis in range(3)
                    ]
                )
            else:
                coords.append([value * scale for value in values])
    except (ValueError, IndexError):
        return []
    return coords


def _minimum_pair_distance(coords: list[list[float]]) -> float | None:
    if len(coords) < 2:
        return None
    min_distance = float("inf")
    max_pairs = 20000
    checked_pairs = 0
    for i, first in enumerate(coords[:-1]):
        for second in coords[i + 1 :]:
            checked_pairs += 1
            if checked_pairs > max_pairs:
                return min_distance if math.isfinite(min_distance) else None
            distance = math.sqrt(sum((first[axis] - second[axis]) ** 2 for axis in range(3)))
            if distance < min_distance:
                min_distance = distance
    return min_distance if math.isfinite(min_distance) else None


def _build_qsub_command(
    qsub_script: Path,
    input_poscar: Path,
    output_poscar: Path,
    settings: dict[str, Any],
) -> list[str]:
    return [
        "qsub",
        str(qsub_script),
        str(input_poscar),
        str(output_poscar),
        str(settings["model"]),
        str(settings["task"]),
        str(settings["device"]),
        str(settings["relax_type"]),
        str(settings["fmax"]),
        str(settings["steps"]),
    ]


def _resolve_settings(input_data: dict[str, Any]) -> dict[str, Any]:
    mlip_settings = input_data.get("mlip_settings") or {}
    relaxation_settings = input_data.get("relaxation_settings") or {}
    settings = dict(DEFAULT_SETTINGS)
    for key in ("model", "task", "device"):
        if key in mlip_settings:
            settings[key] = mlip_settings[key]
    for key in ("relax_type", "fmax", "steps"):
        if key in relaxation_settings:
            settings[key] = relaxation_settings[key]

    settings["relax_type"] = str(settings["relax_type"]).lower()
    if settings["relax_type"] not in {"geometry", "cell", "surface"}:
        settings["relax_type"] = DEFAULT_SETTINGS["relax_type"]
    settings["fmax"] = float(settings["fmax"])
    settings["steps"] = int(settings["steps"])
    return settings


def _resolve_execution_mode(input_data: dict[str, Any]) -> str:
    execution = input_data.get("execution") or {}
    mode = input_data.get("execution_mode") or input_data.get("mode") or execution.get("mode")
    return str(mode or "dry-run").lower()


def _resolve_dry_run(input_data: dict[str, Any], context: dict[str, Any], execution_mode: str) -> bool:
    if "dry_run" in context:
        return bool(context["dry_run"])
    if "dry-run" in context:
        return bool(context["dry-run"])
    if "dry_run" in input_data:
        return bool(input_data["dry_run"])
    if execution_mode in {"qsub", "submit", "local", "run"}:
        return False
    return True


def _resolve_workdir(input_data: dict[str, Any], context: dict[str, Any]) -> Path:
    workdir = context.get("workdir") or input_data.get("workdir") or os.getcwd()
    return Path(workdir).expanduser().resolve()


def _resolve_path(path_value: str | os.PathLike[str], base: Path) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base / path).resolve()


def _ensure_dirs(*dirs: Path) -> None:
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)


def _mesa_output(skill_name: str) -> dict[str, Any]:
    return {
        "status": "failure",
        "task_id": TASK_ID,
        "skill": skill_name,
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


def _validation_fail(result: dict[str, Any], code: str, message: str) -> dict[str, Any]:
    result["status"] = "fail"
    result["safe_to_continue"] = False
    result["errors"].append({"code": code, "message": message})
    return result


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


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


def _determinant_3x3(matrix: list[list[float]]) -> float:
    a, b, c = matrix
    return (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )


def _is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MESA MLIP-to-DFT handoff controller.")
    parser.add_argument("--input", required=True, help="Path to input JSON file.")
    parser.add_argument("--output", required=True, help="Path to output JSON file.")
    parser.add_argument("--workdir", help="Optional working directory.")
    parser.add_argument("--dry-run", action="store_true", help="Do not perform real external execution.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed logs.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    input_path = Path(args.input)
    output_path = Path(args.output)
    input_data = json.loads(input_path.read_text(encoding="utf-8-sig"))
    context: dict[str, Any] = {}
    if args.workdir:
        context["workdir"] = args.workdir
    if args.dry_run:
        context["dry_run"] = True

    result = run(input_data, context)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.verbose:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"success", "partial", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
