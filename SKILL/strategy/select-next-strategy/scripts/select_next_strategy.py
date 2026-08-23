#!/usr/bin/env python3
"""Select the next MESA strategy strictly from a recommended_order queue."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any


SKIP_STATUSES = {"active", "completed", "retired", "blocked", "superseded"}
POOL_FILE = "_strategy_pool.json"


class SelectionError(RuntimeError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select the next strategy from prioritization.recommended_order."
    )
    parser.add_argument("--strategy-artifact", required=True, help="Python or JSON strategy artifact.")
    parser.add_argument("--status-dir", required=True, help="Directory with optional per-strategy status JSON files.")
    parser.add_argument("--output", required=True, help="Path for the selected strategy JSON.")
    parser.add_argument(
        "--max-active-strategies",
        type=int,
        default=1,
        help="Maximum active strategy lineages. Defaults to 1.",
    )
    parser.add_argument("--continue-lineage", help="Active lineage ID for a bounded revision.")
    parser.add_argument("--strategy-id", help="Exact revised strategy ID to materialize.")
    args = parser.parse_args()

    artifact_path = Path(args.strategy_artifact)
    status_dir = Path(args.status_dir)
    output_path = Path(args.output)

    try:
        artifact = load_artifact(artifact_path)
        queue_key, recommended_order = resolve_queue(artifact)
        strategy_lookup = collect_strategies(artifact)
        if args.max_active_strategies < 1:
            raise SelectionError("--max-active-strategies must be at least 1.")
        statuses, records = load_statuses(status_dir)
        pool = load_pool(status_dir)
        active_count = sum(
            1 for record in records if str(record.get("status", "not_started")) == "active"
        )
        if bool(args.continue_lineage) != bool(args.strategy_id):
            raise SelectionError("--continue-lineage and --strategy-id must be supplied together.")
        if args.continue_lineage:
            selected = select_lineage_continuation(
                args.continue_lineage,
                args.strategy_id,
                strategy_lookup,
                statuses,
            )
            skipped, result_status = [], "success"
            selection_mode = "lineage_continuation"
        elif pool.get("launch_state") == "stopped":
            selected, skipped, result_status = None, [], "launch_stopped"
            selection_mode = "new_lineage"
        elif active_count >= args.max_active_strategies:
            selected, skipped, result_status = None, [], "at_capacity"
            selection_mode = "new_lineage"
        else:
            selected, skipped = select_strategy(recommended_order, strategy_lookup, statuses)
            result_status = "success" if selected else "no_selectable_strategy"
            selection_mode = "new_lineage"
    except SelectionError as exc:
        payload = failure_payload(artifact_path, str(exc))
        write_json(output_path, payload)
        print(str(exc), file=sys.stderr)
        return 2

    selected_strategy_id = selected["strategy_id"] if selected else None
    selected_strategy = selected["strategy"] if selected else None

    output = {
        "status": result_status,
        "source_strategy_artifact": str(artifact_path),
        "selected_queue_key": queue_key,
        "recommended_order": recommended_order,
        "skipped_strategies": skipped,
        "selected_strategy_id": selected_strategy_id,
        "selected_strategy_title": strategy_title(selected_strategy) if selected_strategy else None,
        "selected_strategy": selected_strategy,
        "selection_mode": selection_mode,
        "lineage_id": args.continue_lineage or selected_strategy_id,
        "max_active_strategies": args.max_active_strategies,
        "active_strategy_lineages": active_count,
        "available_strategy_slots": max(args.max_active_strategies - active_count, 0),
        "strategy_pool": pool,
        "selection_rule": (
            "Materialized the requested bounded revision for its active lineage."
            if selection_mode == "lineage_continuation"
            else "Selected the first strategy in the current recommended_order whose "
            "status is not active, completed, retired, blocked, or superseded."
        ),
        "can_prove": extract_claim_field(selected_strategy, "can_prove") if selected_strategy else None,
        "cannot_prove": extract_claim_field(selected_strategy, "cannot_prove") if selected_strategy else None,
        "status_dir": str(status_dir),
        "next_action": {
            "recommendation": (
                "generate_explicit_calculation_recipe"
                if selected_strategy_id
                else (
                    "continue_active_lineages"
                    if result_status == "at_capacity"
                    else "finish_active_lineages"
                    if result_status == "launch_stopped"
                    else "needs_strategy_update"
                )
            ),
            "reason": (
                (
                    f"Generate the revised explicit calculation recipe for active lineage {args.continue_lineage}."
                    if selection_mode == "lineage_continuation"
                    else f"Generate the explicit recipe and plan for strategy {selected_strategy_id}, then activate its lineage."
                )
                if selected_strategy_id
                else (
                    "The configured strategy-agent capacity is occupied."
                    if result_status == "at_capacity"
                    else "A manuscript-ready result stopped new strategy launches."
                    if result_status == "launch_stopped"
                    else "Every strategy in recommended_order is active or terminal."
                )
            ),
        },
    }
    write_json(output_path, output)
    return {
        "success": 0,
        "no_selectable_strategy": 3,
        "at_capacity": 0,
        "launch_stopped": 0,
    }[result_status]


def load_artifact(path: Path) -> Any:
    if not path.exists():
        raise SelectionError(f"Strategy artifact does not exist: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise SelectionError(f"Strategy artifact is empty: {path}")
    if path.suffix.lower() == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise SelectionError(f"Invalid JSON artifact {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        module = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        raise SelectionError(f"Artifact is neither JSON nor valid Python: {exc}") from exc

    assignments: dict[str, Any] = {}
    for node in module.body:
        if isinstance(node, ast.Assign):
            try:
                value = ast.literal_eval(node.value)
            except Exception:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            try:
                assignments[node.target.id] = ast.literal_eval(node.value)
            except Exception:
                continue
        elif isinstance(node, ast.Expr):
            try:
                return ast.literal_eval(node.value)
            except Exception:
                continue

    for name in ("updated_strategy_plan", "generated_strategies", "strategy_plan"):
        if name in assignments:
            return assignments[name]
    if assignments:
        return assignments
    raise SelectionError("No literal strategy dictionary assignment found in Python artifact.")


def resolve_queue(artifact: Any) -> tuple[str, list[str]]:
    candidates = [
        ("updated_prioritization.recommended_order", get_path(artifact, ["updated_prioritization", "recommended_order"])),
        ("prioritization.recommended_order", get_path(artifact, ["prioritization", "recommended_order"])),
    ]
    for key, queue in candidates:
        if queue is not None:
            order = normalize_order(queue)
            if not order:
                raise SelectionError(f"{key} is present but empty.")
            return key, order
    raise SelectionError(
        "No prioritization.recommended_order or updated_prioritization.recommended_order found."
    )


def normalize_order(queue: Any) -> list[str]:
    if not isinstance(queue, list):
        raise SelectionError("recommended_order must be a list.")
    order: list[str] = []
    for item in queue:
        if isinstance(item, str):
            order.append(item)
        elif isinstance(item, dict):
            sid = item.get("strategy_id") or item.get("id")
            if sid:
                order.append(str(sid))
            else:
                raise SelectionError(f"recommended_order item lacks strategy_id/id: {item!r}")
        else:
            raise SelectionError(f"Unsupported recommended_order item: {item!r}")
    if len(order) != len(set(order)):
        raise SelectionError("recommended_order contains duplicate strategy IDs.")
    return order


def get_path(data: Any, path: list[str]) -> Any:
    cur = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def collect_strategies(data: Any) -> dict[str, dict[str, Any]]:
    strategies: dict[str, dict[str, Any]] = {}

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            sid = obj.get("strategy_id") or obj.get("id")
            if isinstance(sid, str) and looks_like_strategy(obj):
                if sid in strategies and strategies[sid] is not obj:
                    raise SelectionError(f"Duplicate strategy_id in artifact: {sid}")
                strategies[sid] = obj
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    return strategies


def looks_like_strategy(obj: dict[str, Any]) -> bool:
    strategy_keys = {
        "title",
        "problem",
        "axioms",
        "hypothesis",
        "experiment",
        "results",
        "conclusion",
        "decision_trace",
        "expected_evidence",
        "success_criteria",
        "can_prove",
        "cannot_prove",
    }
    return bool(strategy_keys.intersection(obj))


def load_statuses(
    status_dir: Path,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    statuses: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    if not status_dir.exists():
        return statuses, records
    if not status_dir.is_dir():
        raise SelectionError(f"Status path is not a directory: {status_dir}")
    for path in sorted(status_dir.glob("*.json")):
        if path.name == POOL_FILE:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SelectionError(f"Invalid status JSON {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise SelectionError(f"Strategy status must be an object: {path}")
        records.append(data)
        identifiers = {
            data.get("lineage_id"),
            data.get("root_strategy_id"),
            data.get("current_strategy_id"),
            data.get("strategy_id"),
        }
        for raw_identifier in identifiers:
            if raw_identifier is None:
                continue
            identifier = str(raw_identifier)
            if identifier in statuses and statuses[identifier] is not data:
                raise SelectionError(f"Duplicate strategy status mapping: {identifier}")
            statuses[identifier] = data
    return statuses, records


def load_pool(status_dir: Path) -> dict[str, Any]:
    path = status_dir / POOL_FILE
    if not path.exists():
        return {"launch_state": "open", "manuscript_ready_candidates": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SelectionError(f"Invalid strategy pool JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SelectionError(f"Strategy pool must be an object: {path}")
    if data.get("launch_state", "open") not in {"open", "stopped"}:
        raise SelectionError(f"Invalid launch_state in {path}")
    return data


def select_strategy(
    recommended_order: list[str],
    strategy_lookup: dict[str, dict[str, Any]],
    statuses: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    skipped: list[dict[str, Any]] = []
    for sid in recommended_order:
        status_record = statuses.get(sid, {})
        status = str(status_record.get("status", "not_started"))
        if status in SKIP_STATUSES:
            skipped.append({"strategy_id": sid, "status": status, "reason": f"status is {status}"})
            continue
        strategy = strategy_lookup.get(sid)
        if strategy is None:
            raise SelectionError(f"recommended_order references unknown strategy: {sid}")
        return {"strategy_id": sid, "status": status, "strategy": strategy}, skipped
    return None, skipped


def select_lineage_continuation(
    lineage_id: str,
    strategy_id: str,
    strategy_lookup: dict[str, dict[str, Any]],
    statuses: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    status = statuses.get(lineage_id)
    if not status or status.get("status") != "active":
        raise SelectionError(f"Lineage is not active: {lineage_id}")
    strategy = strategy_lookup.get(strategy_id)
    if strategy is None:
        raise SelectionError(f"Revised strategy is absent from the current plan: {strategy_id}")
    current_id = str(status.get("current_strategy_id") or lineage_id)
    valid_sources = {lineage_id, current_id}
    if strategy.get("origin") == "new_direction":
        raise SelectionError(f"Strategy {strategy_id} starts a new lineage")
    if strategy_id not in valid_sources and str(strategy.get("supersedes")) not in valid_sources:
        raise SelectionError(
            f"Strategy {strategy_id} is not a declared continuation of lineage {lineage_id}"
        )
    return {"strategy_id": strategy_id, "status": "active", "strategy": strategy}


def strategy_title(strategy: dict[str, Any] | None) -> Any:
    if not strategy:
        return None
    for key in ("title", "name", "strategy_title"):
        if key in strategy:
            return strategy[key]
    problem = strategy.get("problem")
    if isinstance(problem, dict):
        return problem.get("title") or problem.get("statement")
    return None


def extract_claim_field(strategy: dict[str, Any] | None, field: str) -> Any:
    if not strategy:
        return None
    if field in strategy:
        return strategy[field]
    for container_key in ("claim_scope", "scope", "expected_claims", "claims"):
        container = strategy.get(container_key)
        if isinstance(container, dict) and field in container:
            return container[field]
    conclusion = strategy.get("conclusion")
    if isinstance(conclusion, dict):
        conclusion_fields = {
            "can_prove": ("causal_mechanism", "design_principle"),
            "cannot_prove": ("scope_or_limitations",),
        }
        values = [
            conclusion[key]
            for key in conclusion_fields.get(field, ())
            if conclusion.get(key) not in (None, "", [], {})
        ]
        if len(values) == 1:
            return values[0]
        if values:
            return values
    return None


def failure_payload(artifact_path: Path, message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "source_strategy_artifact": str(artifact_path),
        "errors": [{"message": message}],
        "next_action": {
            "recommendation": "repair_strategy_artifact",
            "reason": message,
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
