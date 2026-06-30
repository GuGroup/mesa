#!/usr/bin/env python3
"""TASK2 external-skill placeholder."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


TASK_ID = "TASK2"
SKILL_NAME = "no_external_tools"


def run(input_data: dict, context: dict | None = None) -> dict:
    """Execute this mockable external-skill placeholder."""
    result = {
        "status": "skipped",
        "task_id": TASK_ID,
        "skill": SKILL_NAME,
        "data": {"external_tools_required": False},
        "artifacts": [],
        "messages": ["TASK2 does not require external tools for the current workflow."],
        "errors": [],
        "provenance": {
            "inputs": [],
            "external_calls": [],
            "generated_files": [],
        },
        "next_action": {
            "recommendation": "continue",
            "reason": "No external dependency is required.",
        },
    }
    if not isinstance(input_data, dict):
        result["status"] = "failure"
        result["errors"].append({"type": "ValidationError", "message": "input_data must be a dictionary."})
        result["next_action"] = {
            "recommendation": "needs_human_review",
            "reason": "Invalid EXTSKILL input.",
        }
    if context:
        result["provenance"]["inputs"].append({"type": "context", "keys": sorted(context.keys())})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TASK2 no-external-tools placeholder.")
    parser.add_argument("--input", required=True, type=Path, help="Path to input JSON file.")
    parser.add_argument("--output", required=True, type=Path, help="Path to output JSON file.")
    parser.add_argument("--workdir", type=Path, default=None, help="Optional working directory.")
    parser.add_argument("--dry-run", action="store_true", help="Do not perform real external execution.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed logs.")
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8") as handle:
        input_data = json.load(handle)
    result = run(input_data, {"workdir": str(args.workdir) if args.workdir else None, "dry_run": args.dry_run})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
    if args.verbose:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
