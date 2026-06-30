#!/usr/bin/env python3
"""No-op external tool wrapper for TASK1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


TASK_ID = "TASK1"
SKILL_NAME = "no_external_tools"


def _base_output(status: str = "skipped") -> dict[str, Any]:
    return {
        "status": status,
        "task_id": TASK_ID,
        "skill": SKILL_NAME,
        "data": {},
        "artifacts": [],
        "messages": [],
        "errors": [],
        "provenance": {
            "inputs": [],
            "external_calls": [],
            "generated_files": [],
        },
        "next_action": {
            "recommendation": "continue",
            "reason": "TASK1 does not require external tools.",
        },
    }


def run(input_data: dict, context: dict | None = None) -> dict:
    """
    Execute this skill.

    Parameters
    ----------
    input_data:
        JSON-serializable input dictionary.
    context:
        Optional runtime context.

    Returns
    -------
    dict
        Standard MESA skill output.
    """
    try:
        result = _base_output()
        result["messages"].append("No external tool call is required for TASK1.")
        result["provenance"]["inputs"].append(
            {"type": "input_data", "keys": sorted(input_data.keys()) if isinstance(input_data, dict) else []}
        )
        if context:
            result["provenance"]["inputs"].append({"type": "context", "keys": sorted(context.keys())})
        return result
    except Exception as exc:  # pragma: no cover - defensive standard output path
        result = _base_output("failure")
        result["errors"].append({"type": exc.__class__.__name__, "message": str(exc)})
        result["next_action"] = {
            "recommendation": "needs_human_review",
            "reason": "Unexpected failure in no-op external wrapper.",
        }
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="TASK1 no-op external tool wrapper.")
    parser.add_argument("--input", required=True, type=Path, help="Path to input JSON file.")
    parser.add_argument("--output", required=True, type=Path, help="Path to output JSON file.")
    parser.add_argument("--workdir", type=Path, default=None, help="Optional working directory.")
    parser.add_argument("--dry-run", action="store_true", help="Accepted for interface consistency.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed logs.")
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8") as handle:
        input_data = json.load(handle)
    context = {"workdir": str(args.workdir) if args.workdir else None, "dry_run": args.dry_run}
    result = run(input_data, context)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
    if args.verbose:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

