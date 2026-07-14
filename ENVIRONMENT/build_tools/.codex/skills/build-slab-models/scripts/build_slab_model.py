#!/usr/bin/env python3
from __future__ import annotations

import argparse

DIRECT_MP_DISABLED_MESSAGE = (
    "Direct Materials Project/formula slab generation is disabled. "
    "Use import-bulk-structure to import the source bulk, optimize it under "
    "the root calculation policy, then run SKILL/modeling/build-slab-models/"
    "scripts/build_slab_model.py with --bulk-file <optimized-bulk>."
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Legacy slabuilder skill wrapper. Direct MP slab generation is disabled.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--formula", help="Disabled direct Materials Project/formula input.")
    parser.add_argument("--bulk-file", help="Optimized bulk file. Use the active SKILL/modeling/build-slab-models script for this path.")
    parser.add_argument("--miller", nargs=3, type=int, metavar=("H", "K", "L"), help="Surface Miller index.")
    parser.parse_known_args()
    raise SystemExit(DIRECT_MP_DISABLED_MESSAGE)


if __name__ == "__main__":
    raise SystemExit(main())
