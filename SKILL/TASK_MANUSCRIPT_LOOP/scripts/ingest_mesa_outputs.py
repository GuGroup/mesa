#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ingest_gate_files import write_minimum_gate_files
from ingest_io import (
    analyzer_items,
    inventory_markdown,
    manifest_yaml,
    note_items,
    safe_append,
    result_items,
    safe_write,
    write_result_files,
)
from ingest_records import IngestOptions, IngestResult, IntakeError, WriteContext, fail, parse_result


def ingest(options: IngestOptions) -> IngestResult:
    paper = options.paper
    input_root = options.input_root
    if not input_root.exists():
        fail(f"input path does not exist: {input_root}")
    if not paper.exists():
        fail(f"paper path does not exist: {paper}")
    envelopes = sorted((input_root / "task_envelopes").glob("*.json"))
    if not envelopes:
        fail(f"no task envelopes found under {input_root / 'task_envelopes'}")

    records = [parse_result(path, input_root) for path in envelopes]
    context = WriteContext(paper, options.force, [])
    for record in records:
        write_result_files(paper, record, context)

    items = result_items(records) + analyzer_items(input_root, paper, context) + note_items(paper)
    manifest_path = options.out if options.out is not None else paper / "inputs/manifest.yaml"
    safe_write(manifest_path, manifest_yaml(items), context)
    safe_write(paper / "logic/result-inventory.md", inventory_markdown(records), context)
    write_minimum_gate_files(paper, records, context)
    safe_write(
        paper / "state/current-stage.yaml",
        "version: 1\nstage: results_inventory\nstatus: ready\nblockers: []\nnext_action: Build or validate the claim matrix.\n",
        context,
    )
    safe_append(
        paper / "state/ledger.jsonl",
        json.dumps(
            {
                "artifacts": ["paper/inputs/manifest.yaml", "paper/logic/result-inventory.md"],
                "event": "mesa_outputs_ingested",
                "stage": "intake",
                "status": "complete",
            },
            sort_keys=True,
        )
        + "\n",
        context,
    )
    return IngestResult(tuple(sorted(set(context.preserved))))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize completed MESA outputs into a manuscript paper/ workspace.")
    parser.add_argument("--paper", required=True, type=Path, help="Existing paper/ workspace.")
    parser.add_argument("--input", required=True, type=Path, help="MESA output directory to ingest.")
    parser.add_argument("--out", type=Path, help="Manifest output path. Defaults to paper/inputs/manifest.yaml.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing non-empty generated files.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = ingest(IngestOptions(args.paper, args.input, args.out, args.force))
    except IntakeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"ingested {args.input} into {args.paper}")
    for preserved in result.preserved:
        print(f"preserved={preserved}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
