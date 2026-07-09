#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "matplotlib",
#     "numpy",
#     "pymatgen",
#     "scikit-image>=0.24,<0.26",
# ]
# ///
#
# --- How to run ---
# MESA primary runtime:
#   mamba run -n modeling python scripts/analyze_charge_flow.py difference --help
#   mamba run -n modeling python scripts/analyze_charge_flow.py example --outdir /tmp/charge_flow_example
# Direct script runtime, if uv is preferred outside MESA:
#   uv run --script scripts/analyze_charge_flow.py difference --help
# ------------------

from __future__ import annotations

import argparse

from charge_flow_core import ChargeFlowError, run_difference
from charge_flow_example import run_example


def main() -> int:
    args = parse_args()
    match args.command:
        case "difference":
            run_difference(args)
        case "example":
            run_example(args.outdir)
        case unreachable:
            raise ChargeFlowError(f"Unsupported command: {unreachable}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze weighted CHGCAR charge-density differences.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    diff = subparsers.add_parser("difference", help="Compute a weighted CHGCAR difference.")
    diff.add_argument("--term", action="append", required=True, help="label=coefficient:path/to/CHGCAR")
    diff.add_argument("--outdir", required=True, type=str)
    diff.add_argument(
        "--comparison",
        default="adsorption",
        choices=("adsorption", "substitutional-dopant", "modified-vs-pristine", "differential-adsorption"),
    )
    diff.add_argument("--title", default="Charge-flow analysis")
    diff.add_argument("--write-delta-chgcar", action="store_true")
    diff.add_argument("--lattice-atol", type=float, default=1e-5)

    example = subparsers.add_parser("example", help="Run a synthetic no-CHGCAR smoke test.")
    example.add_argument("--outdir", required=True, type=str)
    return parser.parse_args()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ChargeFlowError as exc:
        raise SystemExit(str(exc)) from exc
