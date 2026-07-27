#!/usr/bin/env python3
"""Decide one UMA relaxation continuation after a clean max-step failure."""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
from pathlib import Path
from typing import Any


STRUCTURAL_FLAGS = (
    "connectivity_changed",
    "dissociation_suspected",
    "new_bond_suspected",
    "desorption_suspected",
)
REQUIRED_VIEWS = {"top", "side_a", "side_b"}
RUNNER = (
    Path(__file__).resolve().parents[2]
    / "relax-uma-trajectory"
    / "EXTSKILL"
    / "uma_relax_traj_runner.py"
)


def decide(summary: dict[str, Any], config: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    convergence = _mapping(summary.get("convergence"))
    visual = _mapping(summary.get("visual_validation"))
    review = _mapping(visual.get("review"))
    anomalies = _mapping(summary.get("anomalies"))
    revision = _mapping(config.get("diagnosis_revision"))
    relaxation = _mapping(config.get("relaxation"))
    views = review.get("views_reviewed")
    reviewed_views = set(views) if isinstance(views, list) else set()

    if summary.get("verdict") != "fail":
        reasons.append("overall verdict is not fail")
    if convergence.get("converged") is not False:
        reasons.append("force nonconvergence is not confirmed")
    if convergence.get("nsw_reached") is not True:
        reasons.append("max-step termination is not confirmed")
    if convergence.get("warn_reasons"):
        reasons.append("additional diagnostic warnings are present")
    if visual.get("status") != "completed" or review.get("verdict") != "pass":
        reasons.append("visual review is not completed with pass")
    if not REQUIRED_VIEWS.issubset(reviewed_views):
        reasons.append("visual review does not cover all required views")
    if any(anomalies.get(flag) for flag in STRUCTURAL_FLAGS):
        reasons.append("a structural anomaly is present")
    if revision.get("continuations_used", 0) >= 1:
        reasons.append("the single automatic continuation was already used")

    steps = relaxation.get("steps")
    if not isinstance(steps, int) or isinstance(steps, bool) or steps <= 0:
        reasons.append("relaxation.steps is not a positive integer")
    return not reasons, reasons


def make_retry_config(
    config: dict[str, Any],
    *,
    restart_poscar: Path,
    retry_dir: Path,
    summary_path: Path,
    config_path: Path,
) -> dict[str, Any]:
    retry = copy.deepcopy(config)
    old_steps = retry["relaxation"]["steps"]
    retry["input_poscar"] = str(restart_poscar.resolve())
    retry["workdir"] = str(retry_dir.resolve())
    retry["relaxation"]["steps"] = old_steps * 2
    retry.setdefault("execution", {})["mode"] = "run"
    retry["diagnosis_revision"] = {
        "policy": "double_steps_once",
        "continuations_used": 1,
        "source_analysis_summary": str(summary_path.resolve()),
        "source_config": str(config_path.resolve()),
        "original_steps": old_steps,
        "retry_steps": old_steps * 2,
    }
    return retry


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Decide and optionally run one 2x-step UMA continuation."
    )
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--restart-poscar", type=Path, required=True)
    parser.add_argument("--retry-dir", type=Path, required=True)
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run the fixed UMA runner after writing the retry config.",
    )
    args = parser.parse_args()

    summary = _read_json(args.summary)
    config = _read_json(args.config)
    eligible, reasons = decide(summary, config)
    decision: dict[str, Any] = {"eligible": eligible, "reasons": reasons}

    if not eligible:
        print(json.dumps(decision, indent=2))
        return 2
    if not args.restart_poscar.is_file():
        raise FileNotFoundError(args.restart_poscar)
    if args.retry_dir.exists():
        raise FileExistsError(args.retry_dir)

    args.retry_dir.mkdir(parents=True)
    retry_config = make_retry_config(
        config,
        restart_poscar=args.restart_poscar,
        retry_dir=args.retry_dir,
        summary_path=args.summary,
        config_path=args.config,
    )
    retry_config_path = args.retry_dir / "resolved_uma_config.json"
    retry_config_path.write_text(
        json.dumps(retry_config, indent=2) + "\n", encoding="utf-8"
    )
    decision.update(
        {
            "action": "rerun_with_double_steps",
            "retry_config": str(retry_config_path),
            "original_steps": config["relaxation"]["steps"],
            "retry_steps": retry_config["relaxation"]["steps"],
        }
    )

    if args.run:
        subprocess.run(
            [
                "mamba",
                "run",
                "-n",
                "fairchem",
                "python",
                str(RUNNER),
                "--config",
                str(retry_config_path),
                "--workdir",
                str(args.retry_dir),
            ],
            check=True,
        )
        decision["executed"] = True
    else:
        decision["executed"] = False

    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
