#!/usr/bin/env python3
"""Select the next MESA strategy strictly from a recommended_order queue."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any


SKIP_STATUSES = {"completed", "retired", "blocked", "superseded"}


class SelectionError(RuntimeError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select the next strategy from prioritization.recommended_order."
    )
    parser.add_argument("--strategy-artifact", required=True, help="Python or JSON strategy artifact.")
    parser.add_argument("--status-dir", required=True, help="Directory with optional per-strategy status JSON files.")
    parser.add_argument("--output", required=True, help="Path for selected_strategy.json.")
    args = parser.parse_args()

    artifact_path = Path(args.strategy_artifact)
    status_dir = Path(args.status_dir)
    output_path = Path(args.output)

    try:
        artifact = load_artifact(artifact_path)
        queue_key, recommended_order = resolve_queue(artifact)
        strategy_lookup = collect_strategies(artifact)
        statuses = load_statuses(status_dir)
        selected, skipped = select_strategy(recommended_order, strategy_lookup, statuses)
    except SelectionError as exc:
        payload = failure_payload(artifact_path, str(exc))
        write_json(output_path, payload)
        print(str(exc), file=sys.stderr)
        return 2

    selected_strategy_id = selected["strategy_id"] if selected else None
    selected_strategy = selected["strategy"] if selected else None

    output = {
        "status": "success" if selected_strategy_id else "no_selectable_strategy",
        "source_strategy_artifact": str(artifact_path),
        "selected_queue_key": queue_key,
        "recommended_order": recommended_order,
        "skipped_strategies": skipped,
        "selected_strategy_id": selected_strategy_id,
        "selected_strategy_title": strategy_title(selected_strategy) if selected_strategy else None,
        "selected_strategy": selected_strategy,
        "selection_rule": (
            "Selected the first strategy in the current recommended_order whose "
            "status is not completed, retired, blocked, or superseded."
        ),
        "can_prove": extract_claim_field(selected_strategy, "can_prove") if selected_strategy else None,
        "cannot_prove": extract_claim_field(selected_strategy, "cannot_prove") if selected_strategy else None,
        "status_dir": str(status_dir),
        "next_action": {
            "recommendation": "start_modeling" if selected_strategy_id else "needs_strategy_update",
            "reason": (
                f"Run only strategy {selected_strategy_id} next."
                if selected_strategy_id
                else "Every strategy in recommended_order is completed, retired, blocked, or superseded."
            ),
        },
    }
    write_json(output_path, output)
    return 0 if selected_strategy_id else 3


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
                strategies.setdefault(sid, obj)
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


def load_statuses(status_dir: Path) -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {}
    if not status_dir.exists():
        return statuses
    if not status_dir.is_dir():
        raise SelectionError(f"Status path is not a directory: {status_dir}")
    for path in sorted(status_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SelectionError(f"Invalid status JSON {path}: {exc}") from exc
        sid = str(data.get("strategy_id") or path.stem)
        statuses[sid] = data
    return statuses


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
        strategy = strategy_lookup.get(sid, {"strategy_id": sid})
        return {"strategy_id": sid, "status": status, "strategy": strategy}, skipped
    return None, skipped


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
