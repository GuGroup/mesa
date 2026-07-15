#!/usr/bin/env python3
"""Public entrypoint for evaluate-energy-diagram.

The implementation is intentionally modular.  This file keeps the stable public
`run(input_data, context)` API and CLI while delegating parsing, reaction
classification, evaluation, comparison, reporting, and LLM guidance to focused
modules.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    # Allow direct execution: python MYSKILL/reaction_energy_evaluation.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from MYSKILL.core import evaluate_energy_table, run  # noqa: E402

__all__ = ["evaluate_energy_table", "run", "main"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run integrated MESA reaction energy evaluation.")
    parser.add_argument("--input", required=True, type=Path, help="Path to input JSON file.")
    parser.add_argument("--output", required=True, type=Path, help="Path to output JSON file.")
    parser.add_argument("--workdir", type=Path, default=None, help="Optional working directory.")
    parser.add_argument("--dry-run", action="store_true", help="Do not perform real external execution.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed logs.")
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8-sig") as handle:
        input_data = json.load(handle)

    context = {
        "workdir": str(args.workdir) if args.workdir else None,
        "dry_run": args.dry_run,
    }
    result = run(input_data, context)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
    if args.verbose:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
