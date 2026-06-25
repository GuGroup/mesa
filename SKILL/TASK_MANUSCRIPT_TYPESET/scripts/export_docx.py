#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
# --- How to run ---
# python3 export_docx.py --paper /path/to/paper --out /tmp/mesa_docx --check-only

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from typeset_common import TypesetError, assemble_docx_markdown


@dataclass(frozen=True)  # noqa: SLOTS_OK -- verifier uses Python 3.9, where dataclass slots are unavailable.
class ExportArgs:
    paper: Path
    out: Path
    check_only: bool
    pandoc_bin: str
    reference_doc: Path | None


def parse_args(argv: tuple[str, ...]) -> ExportArgs:
    parser = argparse.ArgumentParser(description="Assemble and optionally export a Nature-family DOCX artifact.")
    parser.add_argument("--paper", required=True, type=Path, help="Path to canonical paper/ directory.")
    parser.add_argument("--out", type=Path, default=Path("docx-export"), help="Output export directory.")
    parser.add_argument("--check-only", action="store_true", help="Validate and assemble Markdown without invoking Pandoc.")
    parser.add_argument("--pandoc-bin", default="pandoc", help="Pandoc executable name or path.")
    parser.add_argument(
        "--reference-doc",
        type=Path,
        default=None,
        help="Optional Word .docx template that controls DOCX styles, fonts, spacing, and numbering.",
    )
    args = parser.parse_args(argv)
    return ExportArgs(args.paper, args.out, args.check_only, args.pandoc_bin, args.reference_doc)


def run_export(config: ExportArgs) -> int:
    result = assemble_docx_markdown(config.paper, config.out)
    if config.check_only:
        print(f"check-only passed: {result.manuscript_path}")
        print(f"qa: {result.qa_path}")
        return 0
    pandoc = shutil.which(config.pandoc_bin)
    if pandoc is None:
        raise TypesetError(
            "Pandoc executable not found. Install Pandoc, pass --pandoc-bin /path/to/pandoc, or rerun with --check-only."
        )
    docx = result.manuscript_path.with_suffix(".docx")
    bibliography = result.workspace.root / "manuscript" / "references.bib"
    command = [pandoc, str(result.manuscript_path), "--bibliography", str(bibliography), "-o", str(docx)]
    if config.reference_doc is not None:
        reference_doc = config.reference_doc.resolve()
        if not reference_doc.is_file():
            raise TypesetError(f"reference DOCX does not exist or is not a file: {config.reference_doc}")
        command.extend(("--reference-doc", str(reference_doc)))
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise TypesetError(f"pandoc export failed with exit {completed.returncode}:\n{completed.stderr.strip()}")
    print(f"docx: {docx}")
    print(f"qa: {result.qa_path}")
    return 0


def main(argv: tuple[str, ...] | None = None) -> int:
    try:
        return run_export(parse_args(tuple(sys.argv[1:] if argv is None else argv)))
    except subprocess.TimeoutExpired as exc:
        print(f"pandoc export timed out after {exc.timeout} seconds", file=sys.stderr)
        return 2
    except TypesetError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
