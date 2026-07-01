#!/usr/bin/env python3
"""Record missing scientific evidence without proxy substitution."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


ALLOWED_STATUS = {"excluded", "blocked", "unresolved"}


def main() -> int:
    args = parse_args()
    spec = json.loads(args.input.expanduser().read_text(encoding="utf-8"))
    validate_spec(spec)
    root = args.project_root.expanduser().resolve() if args.project_root else Path.cwd().resolve()
    outdir = args.outdir.expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    records = flatten_records(spec)
    summary = {
        "schema_version": 1,
        "strategy_id": spec.get("strategy_id"),
        "procedure_id": spec.get("procedure_id"),
        "status": spec["status"],
        "reason": spec["reason"],
        "not_substituted_with_proxy": True,
        "required_future_artifacts": spec.get("required_future_artifacts", []),
        "record_count": len(records),
        "records": records,
    }

    summary_json = outdir / "missing_evidence_summary.json"
    summary_md = outdir / "missing_evidence_summary.md"
    records_json = outdir / "missing_evidence_records.json"
    records_csv = outdir / "missing_evidence_records.csv"
    manifest_json = outdir / "execution_manifest.json"

    write_json(summary_json, summary)
    summary_md.write_text(render_markdown(summary), encoding="utf-8")
    write_json(records_json, {"schema_version": 1, "records": records})
    write_csv(records_csv, records)
    write_json(manifest_json, {
        "schema_version": 1,
        "skill_or_script_used": "missing-evidence-recorder",
        "command": [
            "python",
            "scripts/record_missing_evidence.py",
            "--input",
            rel(args.input.expanduser().resolve(), root),
            "--outdir",
            rel(outdir, root),
        ],
        "input_artifacts": [rel(args.input.expanduser().resolve(), root)],
        "output_artifacts": [
            rel(summary_json, root),
            rel(summary_md, root),
            rel(records_json, root),
            rel(records_csv, root),
        ],
        "validation_status": "unsupported",
        "acceptance_state": spec["status"],
        "caveats": [spec["reason"], "No proxy evidence was substituted."],
    })

    print(json.dumps({
        "status": spec["status"],
        "record_count": len(records),
        "outputs": rel(outdir, root),
    }, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write explicit missing-evidence records for unsupported recipe requirements.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--project-root", type=Path, default=None)
    return parser.parse_args()


def validate_spec(spec: dict[str, Any]) -> None:
    if spec.get("status") not in ALLOWED_STATUS:
        raise SystemExit(f"status must be one of {sorted(ALLOWED_STATUS)}")
    if not spec.get("reason"):
        raise SystemExit("reason is required")
    if spec.get("not_substituted_with_proxy") is not True:
        raise SystemExit("not_substituted_with_proxy must be true")
    requirements = spec.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise SystemExit("requirements must be a non-empty list")
    for requirement in requirements:
        if requirement.get("status") not in ALLOWED_STATUS:
            raise SystemExit("each requirement status must be excluded, blocked, or unresolved")
        if not requirement.get("missing_artifacts"):
            raise SystemExit("each requirement must list missing_artifacts")


def flatten_records(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for requirement in spec["requirements"]:
        targets = requirement.get("targets") or [None]
        for target in targets:
            rows.append({
                "strategy_id": spec.get("strategy_id"),
                "procedure_id": spec.get("procedure_id"),
                "calculation_id": requirement.get("calculation_id"),
                "label": requirement.get("label"),
                "target": target,
                "status": requirement["status"],
                "missing_artifacts": "; ".join(str(x) for x in requirement.get("missing_artifacts", [])),
                "required_future_artifacts": "; ".join(str(x) for x in spec.get("required_future_artifacts", [])),
                "not_substituted_with_proxy": True,
                "reason": requirement.get("reason") or spec["reason"],
            })
    return rows


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Missing Evidence Summary",
        "",
        f"Strategy: `{summary.get('strategy_id')}`",
        f"Procedure: `{summary.get('procedure_id')}`",
        f"Status: `{summary['status']}`",
        "",
        summary["reason"],
        "",
        "No proxy evidence was substituted.",
        "",
        "Required future artifacts:",
    ]
    future = summary.get("required_future_artifacts") or []
    if future:
        lines.extend(f"- {item}" for item in future)
    else:
        lines.append("- Not specified")
    lines.extend(["", "Records:", ""])
    for record in summary["records"]:
        target = f" / {record['target']}" if record.get("target") else ""
        lines.append(
            f"- `{record.get('calculation_id')}{target}`: `{record['status']}`; "
            f"missing `{record['missing_artifacts']}`"
        )
    lines.append("")
    return "\n".join(lines)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "strategy_id",
        "procedure_id",
        "calculation_id",
        "label",
        "target",
        "status",
        "missing_artifacts",
        "required_future_artifacts",
        "not_substituted_with_proxy",
        "reason",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
