#!/usr/bin/env python3
"""Standalone wrapper for deterministic experimental information extraction."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from MYSKILL.experimental import run_extraction as run  # noqa: E402

__all__ = ["run", "main"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run experimental information extraction.")
    parser.add_argument("--input", required=True, type=Path, help="Path to input JSON file.")
    parser.add_argument("--output", required=True, type=Path, help="Path to output JSON file.")
    parser.add_argument("--workdir", type=Path, default=None, help="Optional working directory.")
    parser.add_argument("--dry-run", action="store_true", help="Do not perform external execution.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed logs.")
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8") as handle:
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
