#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
# --- How to run ---
# python3 build_typst.py --paper /path/to/paper --out /tmp/mesa_typeset --check-only

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from typeset_common import TypesetError, assemble_typst


@dataclass(frozen=True)  # noqa: SLOTS_OK -- verifier uses Python 3.9, where dataclass slots are unavailable.
class BuildArgs:
    paper: Path
    out: Path
    check_only: bool
    typst_bin: str


def parse_args(argv: tuple[str, ...]) -> BuildArgs:
    parser = argparse.ArgumentParser(description="Assemble and optionally compile Nature-family Typst artifacts.")
    parser.add_argument("--paper", required=True, type=Path, help="Path to canonical paper/ directory.")
    parser.add_argument("--out", type=Path, default=Path("typeset-build"), help="Output build directory.")
    parser.add_argument("--check-only", action="store_true", help="Validate and assemble without invoking Typst.")
    parser.add_argument("--typst-bin", default="typst", help="Typst executable name or path.")
    args = parser.parse_args(argv)
    return BuildArgs(args.paper, args.out, args.check_only, args.typst_bin)


def run_build(config: BuildArgs) -> int:
    result = assemble_typst(config.paper, config.out)
    if config.check_only:
        print(f"check-only passed: {result.manuscript_path}")
        print(f"qa: {result.qa_path}")
        return 0
    typst = shutil.which(config.typst_bin)
    if typst is None:
        raise TypesetError(
            "Typst executable not found. Install Typst, pass --typst-bin /path/to/typst, or rerun with --check-only."
        )
    pdf = result.manuscript_path.with_suffix(".pdf")
    completed = subprocess.run(
        [typst, "compile", str(result.manuscript_path), str(pdf)],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise TypesetError(f"typst compile failed with exit {completed.returncode}:\n{completed.stderr.strip()}")
    print(f"pdf: {pdf}")
    print(f"qa: {result.qa_path}")
    return 0


def main(argv: tuple[str, ...] | None = None) -> int:
    try:
        return run_build(parse_args(tuple(sys.argv[1:] if argv is None else argv)))
    except subprocess.TimeoutExpired as exc:
        print(f"typst compile timed out after {exc.timeout} seconds", file=sys.stderr)
        return 2
    except TypesetError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
