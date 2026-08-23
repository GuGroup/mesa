#!/usr/bin/env python3
"""Manage active strategy lineages, early stop, and winner selection."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


POOL_FILE = "_strategy_pool.json"
OUTCOMES = {"manuscript_ready", "extend_strategy", "prerequisite", "replace_strategy", "blocked"}
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class StatusError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StatusError(f"Status file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StatusError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StatusError(f"Status file must contain an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def require_identifier(value: str, label: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise StatusError(f"{label} contains unsupported characters: {value!r}")
    return value


def status_path(status_dir: Path, lineage_id: str) -> Path:
    return status_dir / f"{require_identifier(lineage_id, 'lineage_id')}.json"


def load_records(status_dir: Path) -> list[dict[str, Any]]:
    if not status_dir.exists():
        return []
    return [
        read_json(path)
        for path in sorted(status_dir.glob("*.json"))
        if path.name != POOL_FILE
    ]


def load_pool(status_dir: Path) -> dict[str, Any]:
    path = status_dir / POOL_FILE
    if not path.exists():
        return {
            "schema_version": "1.0",
            "launch_state": "open",
            "manuscript_ready_candidates": [],
        }
    return read_json(path)


def require_existing(path_text: str, label: str, directory: bool = False) -> str:
    path = Path(path_text)
    valid = path.is_dir() if directory else path.is_file()
    if not valid:
        kind = "directory" if directory else "file"
        raise StatusError(f"{label} must reference an existing {kind}: {path_text}")
    return path_text


def require_recipe_root(path_text: str, label: str = "recipe_root") -> str:
    value = require_existing(path_text, label, directory=True)
    root = Path(value)
    for filename in ("recipe_index.json", "execution_plan.json"):
        require_existing(str(root / filename), f"{label}/{filename}")
    return value


def append_history(record: dict[str, Any], event: str, **fields: Any) -> None:
    record.setdefault("history", []).append({"event": event, "at": now(), **fields})
    record["updated_at"] = record["history"][-1]["at"]


def activate(args: argparse.Namespace) -> dict[str, Any]:
    if args.max_active < 1:
        raise StatusError("--max-active must be at least 1")
    lineage_id = require_identifier(args.lineage_id, "lineage_id")
    strategy_id = require_identifier(args.strategy_id, "strategy_id")
    run_id = require_identifier(args.run_id or strategy_id, "run_id")
    strategy_artifact = require_existing(args.strategy_artifact, "strategy_artifact")
    recipe_root = require_recipe_root(args.recipe_root)
    path = status_path(args.status_dir, lineage_id)
    existing = read_json(path) if path.exists() else None
    records = load_records(args.status_dir)
    active_records = [record for record in records if record.get("status") == "active"]
    pool = load_pool(args.status_dir)

    if existing is None:
        if pool.get("launch_state") == "stopped":
            raise StatusError("Strategy launch is stopped")
        if len(active_records) >= args.max_active:
            raise StatusError("Active strategy capacity is occupied")
        if args.gpu_index is not None and any(
            (record.get("gpu_assignment") or {}).get("lease_active")
            and (record.get("gpu_assignment") or {}).get("physical_index") == args.gpu_index
            for record in active_records
        ):
            raise StatusError(f"GPU {args.gpu_index} already has an active strategy lease")
        timestamp = now()
        record: dict[str, Any] = {
            "schema_version": "1.0",
            "lineage_id": lineage_id,
            "root_strategy_id": lineage_id,
            "current_strategy_id": strategy_id,
            "current_run_id": run_id,
            "status": "active",
            "classification": None,
            "agent_id": args.agent_id,
            "strategy_artifact": strategy_artifact,
            "recipe_root": recipe_root,
            "strategy_result_report": None,
            "gpu_assignment": (
                {"physical_index": args.gpu_index, "lease_active": True}
                if args.gpu_index is not None
                else None
            ),
            "created_at": timestamp,
            "updated_at": timestamp,
            "history": [
                {"event": "activated", "at": timestamp, "strategy_id": strategy_id, "run_id": run_id}
            ],
        }
    else:
        record = existing
        if record.get("status") != "active":
            raise StatusError(f"Lineage {lineage_id} is terminal")
        current_gpu = (record.get("gpu_assignment") or {}).get("physical_index")
        if args.gpu_index is not None and current_gpu not in {None, args.gpu_index}:
            raise StatusError(
                f"Active lineage {lineage_id} already leases GPU {current_gpu}"
            )
        if args.gpu_index is not None and current_gpu is None:
            if any(
                (item.get("gpu_assignment") or {}).get("lease_active")
                and (item.get("gpu_assignment") or {}).get("physical_index") == args.gpu_index
                for item in active_records
                if item.get("lineage_id") != lineage_id
            ):
                raise StatusError(f"GPU {args.gpu_index} already has an active strategy lease")
            record["gpu_assignment"] = {
                "physical_index": args.gpu_index,
                "lease_active": True,
            }
        if record.get("agent_id") != args.agent_id:
            if not args.agent_replacement_reason:
                raise StatusError("Active lineage is owned by another agent")
            previous_agent = record.get("agent_id")
            record["agent_id"] = args.agent_id
            append_history(
                record,
                "agent_replaced",
                previous_agent_id=previous_agent,
                reason=args.agent_replacement_reason,
            )
        record["current_strategy_id"] = strategy_id
        record["current_run_id"] = run_id
        record["strategy_artifact"] = strategy_artifact
        record["recipe_root"] = recipe_root
        record["classification"] = None
        record["strategy_result_report"] = None
        append_history(record, "continued", strategy_id=strategy_id, run_id=run_id)

    write_json(path, record)
    return record


def record_outcome(args: argparse.Namespace) -> dict[str, Any]:
    lineage_id = require_identifier(args.lineage_id, "lineage_id")
    strategy_id = require_identifier(args.strategy_id, "strategy_id")
    path = status_path(args.status_dir, lineage_id)
    record = read_json(path)
    if record.get("status") != "active":
        raise StatusError(f"Lineage {lineage_id} is not active")
    if args.agent_id and record.get("agent_id") != args.agent_id:
        raise StatusError("Outcome agent does not own this lineage")
    if record.get("current_strategy_id") != strategy_id:
        raise StatusError(f"Outcome strategy is not current for lineage {lineage_id}")
    run_id = require_identifier(
        args.run_id or str(record.get("current_run_id") or strategy_id), "run_id"
    )
    if record.get("current_run_id") not in {None, run_id}:
        raise StatusError(f"Outcome run is not current for lineage {lineage_id}")
    report = require_existing(args.report, "report")
    record["current_strategy_id"] = strategy_id
    record["current_run_id"] = run_id
    record["classification"] = args.classification
    record["strategy_result_report"] = report

    if args.classification == "extend_strategy":
        if args.next_strategy_id:
            record["current_strategy_id"] = require_identifier(
                args.next_strategy_id, "next_strategy_id"
            )
        if args.next_strategy_artifact:
            record["strategy_artifact"] = require_existing(
                args.next_strategy_artifact, "next_strategy_artifact"
            )
        if args.next_recipe_root:
            record["recipe_root"] = require_recipe_root(
                args.next_recipe_root, "next_recipe_root"
            )
        if args.next_run_id:
            record["current_run_id"] = require_identifier(args.next_run_id, "next_run_id")
        append_history(
            record,
            "extended",
            classification=args.classification,
            completed_strategy_id=strategy_id,
            completed_run_id=run_id,
            strategy_result_report=report,
            next_strategy_id=record.get("current_strategy_id"),
            next_run_id=record.get("current_run_id"),
        )
    else:
        record["status"] = "blocked" if args.classification == "blocked" else "completed"
        if isinstance(record.get("gpu_assignment"), dict):
            record["gpu_assignment"]["lease_active"] = False
        append_history(
            record,
            "terminal",
            classification=args.classification,
            strategy_id=strategy_id,
            run_id=run_id,
            strategy_result_report=report,
        )

    write_json(path, record)

    if args.classification == "manuscript_ready":
        pool = load_pool(args.status_dir)
        pool["launch_state"] = "stopped"
        pool["stop_reason"] = "manuscript_ready"
        pool.setdefault("launch_stopped_at", now())
        candidates = pool.setdefault("manuscript_ready_candidates", [])
        candidate = {
            "lineage_id": lineage_id,
            "strategy_id": strategy_id,
            "run_id": run_id,
            "strategy_result_report": report,
        }
        candidates[:] = [item for item in candidates if item.get("lineage_id") != lineage_id]
        candidates.append(candidate)
        write_json(args.status_dir / POOL_FILE, pool)
    return record


def record_winner(args: argparse.Namespace) -> dict[str, Any]:
    lineage_id = require_identifier(args.lineage_id, "lineage_id")
    record = read_json(status_path(args.status_dir, lineage_id))
    if record.get("classification") != "manuscript_ready":
        raise StatusError(f"Lineage {lineage_id} is not manuscript-ready")
    if not args.reason.strip():
        raise StatusError("Winner selection requires a concise reason")
    active_lineages = [
        item.get("lineage_id")
        for item in load_records(args.status_dir)
        if item.get("status") == "active"
    ]
    if active_lineages:
        raise StatusError(f"Active lineages must finish before winner selection: {active_lineages}")
    if not args.evidence_source:
        raise StatusError("Provide at least one --evidence-source")
    for source in args.evidence_source:
        require_existing(source, "evidence_source")
    pool = load_pool(args.status_dir)
    candidates = pool.get("manuscript_ready_candidates", [])
    candidate_lineages = {item.get("lineage_id") for item in candidates}
    if lineage_id not in candidate_lineages:
        raise StatusError(f"Lineage {lineage_id} is absent from manuscript-ready candidates")
    provided_sources = {str(Path(source).resolve()) for source in args.evidence_source}
    missing_reports = [
        item.get("strategy_result_report")
        for item in candidates
        if str(Path(str(item.get("strategy_result_report"))).resolve()) not in provided_sources
    ]
    if missing_reports:
        raise StatusError(f"Candidate reports are missing from evidence sources: {missing_reports}")
    payload = {
        "schema_version": "1.0",
        "winning_lineage_id": lineage_id,
        "winning_strategy_id": record.get("current_strategy_id"),
        "winning_run_id": record.get("current_run_id"),
        "strategy_artifact": record.get("strategy_artifact"),
        "strategy_result_report": record.get("strategy_result_report"),
        "selection_reason": args.reason,
        "evidence_sources": args.evidence_source,
        "selected_at": now(),
    }
    if args.output.exists():
        existing = read_json(args.output)
        comparable = {key: value for key, value in existing.items() if key != "selected_at"}
        expected = {key: value for key, value in payload.items() if key != "selected_at"}
        if comparable != expected:
            raise StatusError(f"Winning strategy already recorded at {args.output}")
        return existing
    write_json(args.output, payload)
    pool["winning_lineage_id"] = lineage_id
    pool["winning_strategy_path"] = str(args.output)
    write_json(args.status_dir / POOL_FILE, pool)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    activate_parser = subparsers.add_parser("activate")
    activate_parser.add_argument("--status-dir", required=True, type=Path)
    activate_parser.add_argument("--lineage-id", required=True)
    activate_parser.add_argument("--strategy-id", required=True)
    activate_parser.add_argument("--run-id")
    activate_parser.add_argument("--strategy-artifact", required=True)
    activate_parser.add_argument("--recipe-root", required=True)
    activate_parser.add_argument("--agent-id", required=True)
    activate_parser.add_argument("--max-active", required=True, type=int)
    activate_parser.add_argument("--gpu-index", type=int)
    activate_parser.add_argument("--agent-replacement-reason")
    activate_parser.set_defaults(handler=activate)

    outcome_parser = subparsers.add_parser("record-outcome")
    outcome_parser.add_argument("--status-dir", required=True, type=Path)
    outcome_parser.add_argument("--lineage-id", required=True)
    outcome_parser.add_argument("--strategy-id", required=True)
    outcome_parser.add_argument("--run-id")
    outcome_parser.add_argument("--classification", required=True, choices=sorted(OUTCOMES))
    outcome_parser.add_argument("--report", required=True)
    outcome_parser.add_argument("--agent-id")
    outcome_parser.add_argument("--next-strategy-id")
    outcome_parser.add_argument("--next-run-id")
    outcome_parser.add_argument("--next-strategy-artifact")
    outcome_parser.add_argument("--next-recipe-root")
    outcome_parser.set_defaults(handler=record_outcome)

    winner_parser = subparsers.add_parser("record-winner")
    winner_parser.add_argument("--status-dir", required=True, type=Path)
    winner_parser.add_argument("--lineage-id", required=True)
    winner_parser.add_argument("--reason", required=True)
    winner_parser.add_argument("--evidence-source", action="append", default=[])
    winner_parser.add_argument("--output", required=True, type=Path)
    winner_parser.set_defaults(handler=record_winner)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = args.handler(args)
    except StatusError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
