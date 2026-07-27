#!/usr/bin/env python3
"""Aggregate calculation-result analyzer outputs into an evidence gate.

This script does not analyze trajectories. Run analyze_relaxation_result.py
first, complete any requested visual reviews, then use this script to turn many
analysis_summary.json files into project-level endpoint acceptance records.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


ACCEPTED = "accepted"
ACCEPTED_WITH_CAVEAT = "accepted-with-caveat"
FAILED = "failed"
EXCLUDED = "excluded"

STRICT_VISUAL_PROBLEM_STATUSES = {"pending", "unavailable", "invalid"}
SEVERITY = {"pass": 0, "warn": 1, "fail": 2}


def main() -> int:
    args = parse_args()
    outdir = args.outdir.expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    root = args.project_root.expanduser().resolve() if args.project_root else Path.cwd().resolve()

    batch = read_json(args.batch_summary) if args.batch_summary else None
    registry = read_json(args.registry) if args.registry else None
    summary_items = collect_summary_items(args.analysis_root, batch, registry, root)

    records = []
    for item in summary_items:
        records.append(gate_item(item, root, strict_visual=not args.allow_incomplete_visual))

    counts = count_by(records, "acceptance_state")
    verdict_counts = count_by(records, "verdict")
    visual_counts = count_by(records, "visual_status")
    warning_class_counts = count_list_values(records, "warning_classes")
    warning_class_examples = example_ids_by_list_value(records, "warning_classes", limit=5)
    summary = {
        "schema_version": 1,
        "stage": args.stage,
        "source_analysis_root": rel(args.analysis_root.resolve(), root) if args.analysis_root else None,
        "source_analysis_batch": rel(args.batch_summary.resolve(), root) if args.batch_summary else None,
        "source_registry": rel(args.registry.resolve(), root) if args.registry else None,
        "record_count": len(records),
        "accepted_count": counts.get(ACCEPTED, 0),
        "accepted_with_caveat_count": counts.get(ACCEPTED_WITH_CAVEAT, 0),
        "failed_count": counts.get(FAILED, 0),
        "excluded_count": counts.get(EXCLUDED, 0),
        "verdict_counts": verdict_counts,
        "visual_status_counts": visual_counts,
        "warning_class_counts": warning_class_counts,
        "warning_class_examples": warning_class_examples,
        "policy": (
            "Use accepted and accepted-with-caveat endpoints downstream; carry "
            "caveats into result/manuscript claims. Failed or excluded endpoints "
            "must not be silently substituted."
        ),
        "strict_visual_gate": not args.allow_incomplete_visual,
        "records": records,
    }

    write_json(outdir / "evidence_readiness_summary.json", summary)
    write_json(outdir / "endpoint_triage.json", {"schema_version": 1, "records": records})
    write_csv(outdir / "endpoint_triage.csv", records)
    write_visual_queue(outdir / "visual_review_queue.md", records)

    print(json.dumps({
        "record_count": summary["record_count"],
        "accepted_count": summary["accepted_count"],
        "accepted_with_caveat_count": summary["accepted_with_caveat_count"],
        "failed_count": summary["failed_count"],
        "excluded_count": summary["excluded_count"],
        "outputs": {
            "evidence_readiness_summary": str(outdir / "evidence_readiness_summary.json"),
            "endpoint_triage_csv": str(outdir / "endpoint_triage.csv"),
            "visual_review_queue": str(outdir / "visual_review_queue.md"),
        },
    }, indent=2))

    return 2 if summary["failed_count"] or summary["excluded_count"] else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate many analysis_summary.json files into project-level evidence readiness.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--analysis-root", type=Path, help="Directory containing per-run analysis_summary.json files.")
    parser.add_argument("--batch-summary", type=Path, help="Optional analysis_batch_summary.json from a batch runner.")
    parser.add_argument("--registry", type=Path, help="Optional relaxation/job registry with endpoint metadata.")
    parser.add_argument("--outdir", required=True, type=Path, help="Output directory for evidence gate artifacts.")
    parser.add_argument("--project-root", type=Path, default=None, help="Root used to relativize output paths.")
    parser.add_argument("--stage", default="calculation evidence readiness", help="Human-readable stage label.")
    parser.add_argument(
        "--allow-incomplete-visual",
        action="store_true",
        help="Do not fail endpoints whose visual validation is pending/unavailable/invalid.",
    )
    args = parser.parse_args()
    if not args.analysis_root and not args.batch_summary:
        parser.error("provide --analysis-root and/or --batch-summary")
    return args


def collect_summary_items(
    analysis_root: Path | None,
    batch: dict[str, Any] | None,
    registry: dict[str, Any] | None,
    root: Path,
) -> list[dict[str, Any]]:
    registry_by_id, registry_by_traj = index_registry(registry, root)

    items: list[dict[str, Any]] = []
    if batch:
        for row in batch.get("results", []):
            summary_path = resolve_path(row.get("summary_path"), root)
            if not summary_path or not summary_path.exists():
                items.append({"batch_row": row, "registry_record": match_registry(row, registry_by_id, registry_by_traj, root), "summary": None, "summary_path": summary_path})
                continue
            summary = read_json(summary_path)
            items.append({"batch_row": row, "registry_record": match_registry(row, registry_by_id, registry_by_traj, root), "summary": summary, "summary_path": summary_path})

    if not items and analysis_root:
        for summary_path in sorted(analysis_root.expanduser().resolve().glob("*/analysis_summary.json")):
            summary = read_json(summary_path)
            row = {
                "id": summary_path.parent.name,
                "summary_path": str(summary_path),
                "trajectory": (summary or {}).get("trajectory_input") or (summary or {}).get("input"),
            }
            items.append({"batch_row": row, "registry_record": match_registry(row, registry_by_id, registry_by_traj, root), "summary": summary, "summary_path": summary_path})

    return items


def index_registry(registry: dict[str, Any] | None, root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_traj: dict[str, dict[str, Any]] = {}
    if not registry:
        return by_id, by_traj
    for record in registry.get("records", []):
        if not isinstance(record, dict):
            continue
        record_id = record.get("id")
        if record_id:
            by_id[str(record_id)] = record
        traj = resolve_path(record.get("trajectory"), root)
        if traj:
            by_traj[str(traj.resolve())] = record
    return by_id, by_traj


def match_registry(
    row: dict[str, Any],
    registry_by_id: dict[str, dict[str, Any]],
    registry_by_traj: dict[str, dict[str, Any]],
    root: Path,
) -> dict[str, Any] | None:
    row_id = row.get("id")
    if row_id and str(row_id) in registry_by_id:
        return registry_by_id[str(row_id)]
    traj = resolve_path(row.get("trajectory"), root)
    if traj and str(traj.resolve()) in registry_by_traj:
        return registry_by_traj[str(traj.resolve())]
    return None


def gate_item(item: dict[str, Any], root: Path, *, strict_visual: bool) -> dict[str, Any]:
    row = item.get("batch_row") or {}
    reg = item.get("registry_record") or {}
    summary = item.get("summary") or {}
    summary_path = item.get("summary_path")

    visual = summary.get("visual_validation") if isinstance(summary, dict) else {}
    if not isinstance(visual, dict):
        visual = {}
    convergence = summary.get("convergence") if isinstance(summary, dict) else {}
    if not isinstance(convergence, dict):
        convergence = {}
    diagnosis = summary.get("diagnosis") if isinstance(summary, dict) else {}
    if not isinstance(diagnosis, dict):
        diagnosis = {}

    verdict = str(summary.get("verdict") or row.get("verdict") or "missing")
    deterministic = str(summary.get("deterministic_verdict") or row.get("deterministic_verdict") or "missing")
    visual_status = str(visual.get("status") or row.get("visual_status") or "missing")

    caveats: list[str] = []
    caveats.extend(str(x) for x in convergence.get("warn_reasons", []) if x)
    caveats.extend(str(x) for x in convergence.get("fail_reasons", []) if x)
    caveats.extend(str(x) for x in diagnosis.get("warnings", []) if x)
    caveats = unique(caveats)

    acceptance_state = ACCEPTED
    if not summary:
        acceptance_state = FAILED
        caveats.append("analysis_summary.json missing or unreadable")
    elif reg.get("acceptance_state") == EXCLUDED:
        acceptance_state = EXCLUDED
        caveats.extend(str(x) for x in reg.get("caveats", []) if x)
    elif verdict == "fail" or deterministic == "fail":
        acceptance_state = FAILED
    elif strict_visual and visual_status in STRICT_VISUAL_PROBLEM_STATUSES:
        acceptance_state = FAILED
        caveats.append(f"visual validation status is {visual_status}")
    elif verdict == "warn" or deterministic == "warn" or caveats:
        acceptance_state = ACCEPTED_WITH_CAVEAT

    if visual_status == "completed":
        review = visual.get("review")
        review_verdict = review.get("verdict") if isinstance(review, dict) else None
        if review_verdict and review_verdict != "pass":
            caveats.append(f"visual review verdict: {review_verdict}")
    elif visual_status in STRICT_VISUAL_PROBLEM_STATUSES:
        caveats.append(f"visual review incomplete: {visual_status}")

    warning_classes = classify_warning_classes(caveats, visual_status, verdict, deterministic, acceptance_state)
    record = {
        "id": first_nonempty(reg.get("id"), row.get("id"), parent_name(summary_path)),
        "kind": first_nonempty(reg.get("kind"), row.get("kind")),
        "motif": first_nonempty(reg.get("motif"), row.get("motif")),
        "state": first_nonempty(reg.get("state"), row.get("state")),
        "species": first_nonempty(reg.get("species"), row.get("species")),
        "analysis_summary": rel(summary_path, root) if isinstance(summary_path, Path) else None,
        "trajectory": rel(resolve_path(first_nonempty(reg.get("trajectory"), row.get("trajectory"), summary.get("trajectory_input"), summary.get("input")), root), root),
        "verdict": verdict,
        "deterministic_verdict": deterministic,
        "visual_status": visual_status,
        "visual_review_request": rel(resolve_path(visual.get("request_path") or row.get("visual_review_request"), root), root),
        "acceptance_state": acceptance_state,
        "warning_classes": warning_classes,
        "caveats": unique(caveats),
        "final_energy_ev": first_nonempty(diagnosis.get("final_energy"), reg.get("final_energy_ev")),
        "final_fmax_ev_per_a": first_nonempty(diagnosis.get("final_fmax"), reg.get("final_max_force_ev_per_a")),
    }
    return record


def read_json(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    try:
        return json.loads(path.expanduser().read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fields = [
        "id",
        "kind",
        "motif",
        "state",
        "species",
        "acceptance_state",
        "verdict",
        "deterministic_verdict",
        "visual_status",
        "final_energy_ev",
        "final_fmax_ev_per_a",
        "analysis_summary",
        "trajectory",
        "caveats",
        "warning_classes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = {field: record.get(field) for field in fields}
            row["caveats"] = "; ".join(record.get("caveats") or [])
            row["warning_classes"] = "; ".join(record.get("warning_classes") or [])
            writer.writerow(row)


def write_visual_queue(path: Path, records: list[dict[str, Any]]) -> None:
    queue = [
        record for record in records
        if record.get("visual_status") in STRICT_VISUAL_PROBLEM_STATUSES or record.get("acceptance_state") == FAILED
    ]
    lines = [
        "# Visual Review / Evidence Queue",
        "",
        "Use this queue before downstream energetics or manuscript claims.",
        "",
    ]
    if not queue:
        lines.append("No endpoints require additional visual/evidence review.")
    else:
        for record in queue:
            lines.extend([
                f"## {record.get('id')}",
                "",
                f"- acceptance_state: `{record.get('acceptance_state')}`",
                f"- verdict: `{record.get('verdict')}`",
                f"- visual_status: `{record.get('visual_status')}`",
                f"- warning_classes: {'; '.join(record.get('warning_classes') or []) or 'none'}",
                f"- analysis_summary: `{record.get('analysis_summary')}`",
                f"- visual_review_request: `{record.get('visual_review_request')}`",
                f"- caveats: {'; '.join(record.get('caveats') or []) or 'none'}",
                "",
            ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for record in records:
        value = str(record.get(key))
        out[value] = out.get(value, 0) + 1
    return out


def count_list_values(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for record in records:
        values = record.get(key) or []
        if not isinstance(values, list):
            values = [values]
        for value in values:
            label = str(value)
            out[label] = out.get(label, 0) + 1
    return out


def example_ids_by_list_value(records: list[dict[str, Any]], key: str, *, limit: int) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for record in records:
        record_id = str(record.get("id") or "")
        values = record.get(key) or []
        if not isinstance(values, list):
            values = [values]
        for value in values:
            label = str(value)
            bucket = out.setdefault(label, [])
            if record_id and len(bucket) < limit:
                bucket.append(record_id)
    return out


def classify_warning_classes(
    caveats: list[str],
    visual_status: str,
    verdict: str,
    deterministic: str,
    acceptance_state: str,
) -> list[str]:
    classes: list[str] = []
    lowered = " | ".join(caveats).lower()
    if visual_status in STRICT_VISUAL_PROBLEM_STATUSES:
        classes.append("visual_review_incomplete")
    if "bond" in lowered and ("broke" in lowered or "new bond" in lowered):
        classes.append("bond_change")
    if "dissociation" in lowered:
        classes.append("possible_dissociation")
    if "desorption" in lowered:
        classes.append("possible_desorption")
    if "site" in lowered and ("migration" in lowered or "wrong" in lowered):
        classes.append("site_migration")
    if "reconstruction" in lowered or "distortion" in lowered:
        classes.append("slab_or_endpoint_distortion")
    if "energy" in lowered:
        classes.append("energy_trend")
    if "fmax" in lowered or "force" in lowered:
        classes.append("force_trend")
    if "rmsd" in lowered:
        classes.append("rmsd_trend")
    if "max ionic" in lowered or "max-step" in lowered or "nsw" in lowered or "not force-converged" in lowered:
        classes.append("nonconverged_or_max_steps")
    if verdict == "fail" or deterministic == "fail" or acceptance_state == FAILED:
        classes.append("failed_gate")
    if not classes and (verdict == "warn" or deterministic == "warn" or caveats):
        classes.append("other_warning")
    return unique(classes)


def resolve_path(value: Any, root: Path) -> Path | None:
    if value is None or value == "":
        return None
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return (root / path).resolve()


def rel(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)


def first_nonempty(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def parent_name(path: Any) -> str | None:
    if isinstance(path, Path):
        return path.parent.name
    return None


def unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            out.append(value)
            seen.add(value)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
