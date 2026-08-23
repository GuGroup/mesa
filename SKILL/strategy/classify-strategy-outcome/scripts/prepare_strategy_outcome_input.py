#!/usr/bin/env python3
"""Assemble a bounded JSON input for strategy-outcome classification."""

from __future__ import annotations

import argparse
import ast
import copy
import json
from pathlib import Path
from typing import Any


class AssemblyError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--strategy-artifact", required=True, type=Path)
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--recipe-root", required=True, type=Path)
    parser.add_argument("--missing-evidence", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AssemblyError(f"File does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AssemblyError(f"Invalid JSON in {path}: {exc}") from exc


def load_strategy_literal(path: Path) -> tuple[str, dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AssemblyError(f"Strategy artifact does not exist: {path}") from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        try:
            module = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            raise AssemblyError(f"Invalid strategy artifact {path}: {exc}") from exc
        assignments: dict[str, Any] = {}
        for node in module.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            try:
                literal = ast.literal_eval(node.value)
            except (TypeError, ValueError, SyntaxError) as exc:
                named_targets = [target.id for target in targets if isinstance(target, ast.Name)]
                if set(named_targets).intersection({"generated_strategies", "updated_strategy_plan"}):
                    raise AssemblyError("Strategy assignment must be a literal dictionary") from exc
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = literal
        for name in ("updated_strategy_plan", "generated_strategies", "strategy_plan"):
            if name in assignments:
                value = assignments[name]
                break
        else:
            raise AssemblyError(f"No supported strategy assignment in {path}")
    if not isinstance(value, dict):
        raise AssemblyError("Strategy artifact must be a dictionary")

    if "updated_strategies" in value or "updated_prioritization" in value:
        return "updated_strategy_plan", value
    if "strategies" in value or "prioritization" in value:
        return "generated_strategies", value
    if len(value) == 1:
        for name in ("updated_strategy_plan", "generated_strategies", "strategy_plan"):
            nested = value.get(name)
            if isinstance(nested, dict):
                resolved_name = "updated_strategy_plan" if name == "updated_strategy_plan" else "generated_strategies"
                return resolved_name, nested
    raise AssemblyError(f"Unsupported strategy artifact schema: {path}")


def load_generated_strategies(path: Path) -> dict[str, Any]:
    kind, value = load_strategy_literal(path)
    if kind != "generated_strategies":
        raise AssemblyError(f"Expected generated strategies: {path}")
    return value


def resolve_original_strategy_path(
    raw_path: str,
    updated_path: Path,
    project_root: Path,
) -> Path:
    raw = Path(raw_path)
    candidates = [raw] if raw.is_absolute() else [project_root / raw, updated_path.parent / raw]
    for candidate in candidates:
        try:
            resolved = bounded_path(candidate, project_root)
        except AssemblyError:
            continue
        if resolved.is_file():
            return resolved
    raise AssemblyError(f"Original strategy artifact is unavailable: {raw_path}")


def normalized_order(value: Any, label: str) -> list[str]:
    order = []
    for index, item in enumerate(require_list(value, label)):
        if isinstance(item, str):
            order.append(require_string(item, f"{label}[{index}]"))
            continue
        entry = require_dict(item, f"{label}[{index}]")
        order.append(
            require_string(
                entry.get("strategy_id") or entry.get("id"),
                f"{label}[{index}].strategy_id",
            )
        )
    return order


def overlay_updated_plan(
    updated: dict[str, Any],
    original: dict[str, Any],
    strategy_id: str,
) -> dict[str, Any]:
    original_items = require_list(original.get("strategies"), "original strategies")
    original_by_id: dict[str, dict[str, Any]] = {}
    for index, raw_item in enumerate(original_items):
        item = require_dict(raw_item, f"original strategies[{index}]")
        item_id = require_string(item.get("strategy_id"), f"original strategies[{index}].strategy_id")
        if item_id in original_by_id:
            raise AssemblyError(f"Duplicate original strategy_id: {item_id}")
        original_by_id[item_id] = item

    merged_by_id: dict[str, dict[str, Any]] = {}
    for index, raw_item in enumerate(
        require_list(updated.get("updated_strategies"), "updated_strategies")
    ):
        item = copy.deepcopy(require_dict(raw_item, f"updated_strategies[{index}]"))
        item_id = require_string(item.get("strategy_id"), f"updated_strategies[{index}].strategy_id")
        if item_id in merged_by_id:
            raise AssemblyError(f"Duplicate updated strategy_id: {item_id}")
        source_id = item_id if item_id in original_by_id else item.get("supersedes")
        source = original_by_id.get(str(source_id)) if source_id else None
        inherited_fields = ("decision_target", "author_claim_support_if_successful")
        missing_fields = [field for field in inherited_fields if item.get(field) in (None, "", [], {})]
        if missing_fields:
            if item.get("origin") == "new_direction" or source is None:
                raise AssemblyError(
                    f"Updated strategy {item_id} needs a complete generated-strategy contract "
                    f"before classification; missing {missing_fields}"
                )
            for field in missing_fields:
                item[field] = copy.deepcopy(source.get(field))
        merged_by_id[item_id] = item

    updated_prioritization = require_dict(
        updated.get("updated_prioritization"), "updated_prioritization"
    )
    order = normalized_order(
        updated_prioritization.get("recommended_order"),
        "updated_prioritization.recommended_order",
    )
    for item_id in [*order, strategy_id]:
        if item_id in merged_by_id:
            continue
        if item_id in original_by_id:
            merged_by_id[item_id] = copy.deepcopy(original_by_id[item_id])
            continue
        raise AssemblyError(f"Updated strategy plan references unknown strategy: {item_id}")

    original_prioritization = require_dict(original.get("prioritization"), "prioritization")
    rationale = updated_prioritization.get("rationale")
    if rationale is None:
        rationale = original_prioritization.get("rationale")
    return {
        "target_task": copy.deepcopy(original.get("target_task")),
        "strategies": list(merged_by_id.values()),
        "prioritization": {
            "recommended_order": order,
            "rationale": copy.deepcopy(rationale),
        },
    }


def load_strategy_context_data(
    path: Path,
    project_root: Path,
    strategy_id: str,
) -> tuple[dict[str, Any], Path | None]:
    kind, value = load_strategy_literal(path)
    if kind == "generated_strategies":
        return value, None
    revision = require_dict(value.get("revision_context"), "revision_context")
    original_text = require_string(
        revision.get("original_strategies_artifact"),
        "revision_context.original_strategies_artifact",
    )
    original_path = resolve_original_strategy_path(original_text, path, project_root)
    original = load_generated_strategies(original_path)
    return overlay_updated_plan(value, original, strategy_id), original_path


def require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AssemblyError(f"{label} must be an object")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise AssemblyError(f"{label} must be a list")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssemblyError(f"{label} must be a non-empty string")
    return value


def statements(value: Any, label: str) -> list[dict[str, str]]:
    items = require_list(value, label)
    return [
        {
            "statement": require_string(
                require_dict(item, f"{label}[{index}]").get("statement"),
                f"{label}[{index}].statement",
            )
        }
        for index, item in enumerate(items)
    ]


def extract_strategy_context(data: dict[str, Any], strategy_id: str) -> dict[str, Any]:
    target = require_dict(data.get("target_task"), "target_task")
    claim = require_dict(
        target.get("author_reported_claim"),
        "target_task.author_reported_claim",
    )
    author_statement = require_string(
        claim.get("statement"),
        "target_task.author_reported_claim.statement",
    )

    extracted_strategies = []
    seen_ids: set[str] = set()
    for index, raw_strategy in enumerate(
        require_list(data.get("strategies"), "strategies")
    ):
        strategy = require_dict(raw_strategy, f"strategies[{index}]")
        item_id = require_string(
            strategy.get("strategy_id"), f"strategies[{index}].strategy_id"
        )
        if item_id in seen_ids:
            raise AssemblyError(f"Duplicate strategy_id: {item_id}")
        seen_ids.add(item_id)
        hypothesis = require_dict(
            strategy.get("hypothesis"), f"strategies[{index}].hypothesis"
        )
        results = require_dict(
            strategy.get("results"), f"strategies[{index}].results"
        )
        support_label = f"strategies[{index}].author_claim_support_if_successful"
        author_claim_support = require_dict(
            strategy.get("author_claim_support_if_successful"),
            support_label,
        )
        out_of_scope = [
            require_string(item, f"{support_label}.out_of_scope[{item_index}]")
            for item_index, item in enumerate(
                require_list(
                    author_claim_support.get("out_of_scope"),
                    f"{support_label}.out_of_scope",
                )
            )
        ]
        extracted_strategies.append(
            {
                "strategy_id": item_id,
                "title": require_string(
                    strategy.get("title"), f"strategies[{index}].title"
                ),
                "decision_target": require_string(
                    strategy.get("decision_target"),
                    f"strategies[{index}].decision_target",
                ),
                "hypothesis": {
                    "statement": require_string(
                        hypothesis.get("statement"),
                        f"strategies[{index}].hypothesis.statement",
                    )
                },
                "results": {
                    "expected_computational_results": statements(
                        results.get("expected_computational_results"),
                        f"strategies[{index}].results.expected_computational_results",
                    ),
                    "computational_benchmark_comparisons": statements(
                        results.get("computational_benchmark_comparisons"),
                        f"strategies[{index}].results.computational_benchmark_comparisons",
                    ),
                },
                "author_claim_support_if_successful": {
                    "expected_strength": require_string(
                        author_claim_support.get("expected_strength"),
                        f"{support_label}.expected_strength",
                    ),
                    "maximum_supported_conclusion": require_string(
                        author_claim_support.get("maximum_supported_conclusion"),
                        f"{support_label}.maximum_supported_conclusion",
                    ),
                    "out_of_scope": out_of_scope,
                },
            }
        )
    if strategy_id not in seen_ids:
        raise AssemblyError(f"Unknown current strategy: {strategy_id}")

    prioritization = require_dict(data.get("prioritization"), "prioritization")
    recommended_order = [
        require_string(item, f"prioritization.recommended_order[{index}]")
        for index, item in enumerate(
            require_list(
                prioritization.get("recommended_order"),
                "prioritization.recommended_order",
            )
        )
    ]
    unknown = sorted(set(recommended_order) - seen_ids)
    if unknown:
        raise AssemblyError(
            f"prioritization.recommended_order contains unknown strategies: {unknown}"
        )

    return {
        "target_task": {
            "author_reported_claim": {"statement": author_statement}
        },
        "strategies": extracted_strategies,
        "prioritization": {
            "recommended_order": recommended_order,
            "rationale": statements(
                prioritization.get("rationale"), "prioritization.rationale"
            ),
        },
    }


def bounded_path(path: Path, project_root: Path) -> Path:
    candidate = path if path.is_absolute() else project_root / path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError as exc:
        raise AssemblyError(f"Path escapes project root: {path}") from exc
    return resolved


def display_path(path: Path, project_root: Path) -> str:
    return str(path.relative_to(project_root))


def procedure_repair_chain(base: Path, procedure_id: str) -> Path:
    current = base / "procedure_diagnosis.json"
    if not current.is_file():
        raise AssemblyError(f"No procedure diagnosis exists for {procedure_id}")

    for attempt in (1, 2):
        suffix = f"-R{attempt}"
        decision_suffix = "" if attempt == 1 else f"-R{attempt - 1}"
        decision_path = base / f"repair_decision{decision_suffix}.json"
        diagnosis_path = base / f"procedure_diagnosis{suffix}.json"
        outcome_path = base / f"repair_outcome{suffix}.json"
        attempt_decision_path = base / f"repair_decision{suffix}.json"
        artifacts_exist = any(
            path.is_file()
            for path in (diagnosis_path, outcome_path, attempt_decision_path)
        )
        decision = (
            require_dict(load_json(decision_path), str(decision_path)).get("decision")
            if decision_path.is_file()
            else None
        )

        if decision == "repair_once":
            if not diagnosis_path.is_file() or not outcome_path.is_file():
                raise AssemblyError(
                    f"Incomplete procedure repair {suffix}: require "
                    f"{diagnosis_path.name} and {outcome_path.name}"
                )
            current = diagnosis_path
            continue
        if artifacts_exist:
            raise AssemblyError(f"Procedure repair {suffix} is not authorized")
        break

    return current


def terminal_diagnoses(
    recipe_root: Path,
    recipe_index: dict[str, Any],
    project_root: Path,
) -> list[tuple[str, Path, dict[str, Any]]]:
    procedures = require_list(recipe_index.get("procedures"), "recipe_index.procedures")
    if not procedures:
        raise AssemblyError("recipe_index.procedures must not be empty")
    result = []
    seen: set[str] = set()
    for index, raw_procedure in enumerate(procedures):
        procedure = require_dict(raw_procedure, f"recipe_index.procedures[{index}]")
        procedure_id = require_string(
            procedure.get("procedure_id"),
            f"recipe_index.procedures[{index}].procedure_id",
        )
        if procedure_id in seen:
            raise AssemblyError(f"Duplicate procedure_id: {procedure_id}")
        seen.add(procedure_id)
        base = recipe_root / procedure_id
        path = procedure_repair_chain(base, procedure_id)
        path = bounded_path(path, project_root)
        diagnosis = require_dict(load_json(path), str(path))
        if diagnosis.get("procedure_id") != procedure_id:
            raise AssemblyError(f"Procedure ID mismatch in {path}")
        verdict = diagnosis.get("verdict")
        if verdict not in {"pass", "warn", "fail", "unknown"}:
            raise AssemblyError(f"Invalid verdict in {path}: {verdict!r}")
        require_dict(diagnosis.get("coverage"), f"{path}: coverage")
        require_list(
            diagnosis.get("outputs_for_strategy_diagnosis"),
            f"{path}: outputs_for_strategy_diagnosis",
        )
        require_list(diagnosis.get("execution_gaps"), f"{path}: execution_gaps")
        result.append((procedure_id, path, diagnosis))
    return result


def referenced_path(item: Any, label: str) -> Path:
    if isinstance(item, str):
        return Path(require_string(item, label))
    if isinstance(item, dict) and set(item) == {"path"}:
        return Path(require_string(item.get("path"), f"{label}.path"))
    raise AssemblyError(f"{label} must be a path string or an object containing only path")


def load_bounded_json(path: Path, project_root: Path, label: str) -> tuple[Path, Any]:
    resolved = bounded_path(path, project_root)
    if resolved.suffix.lower() != ".json":
        raise AssemblyError(f"{label} is not JSON: {path}")
    return resolved, load_json(resolved)


def assemble(args: argparse.Namespace) -> dict[str, Any]:
    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        raise AssemblyError(f"Project root is not a directory: {args.project_root}")
    strategy_path = bounded_path(args.strategy_artifact, project_root)
    recipe_root = bounded_path(args.recipe_root, project_root)
    recipe_index_path = bounded_path(recipe_root / "recipe_index.json", project_root)

    generated, original_strategy_path = load_strategy_context_data(
        strategy_path, project_root, args.strategy_id
    )
    context = extract_strategy_context(generated, args.strategy_id)
    recipe_index = require_dict(load_json(recipe_index_path), str(recipe_index_path))
    indexed_strategy = recipe_index.get("strategy_id")
    if indexed_strategy and indexed_strategy != args.strategy_id:
        raise AssemblyError(
            f"recipe_index strategy_id is {indexed_strategy}, not {args.strategy_id}"
        )

    diagnoses = terminal_diagnoses(recipe_root, recipe_index, project_root)
    diagnosis_output = []
    evidence: dict[Path, dict[str, Any]] = {}
    missing: dict[Path, dict[str, Any]] = {}
    for procedure_id, path, diagnosis in diagnoses:
        diagnosis_output.append(
            {
                "source": display_path(path.resolve(), project_root),
                "procedure_id": procedure_id,
                "verdict": diagnosis["verdict"],
                "coverage": diagnosis["coverage"],
                "outputs_for_strategy_diagnosis": diagnosis[
                    "outputs_for_strategy_diagnosis"
                ],
                "execution_gaps": diagnosis["execution_gaps"],
            }
        )
        for index, item in enumerate(diagnosis["outputs_for_strategy_diagnosis"]):
            raw_path = referenced_path(
                item,
                f"{path}: outputs_for_strategy_diagnosis[{index}]",
            )
            resolved, data = load_bounded_json(
                raw_path, project_root, "Strategy-diagnosis output"
            )
            bucket = (
                missing
                if resolved.name == "missing_evidence.json"
                else evidence
            )
            record = bucket.setdefault(
                resolved,
                {
                    "source": display_path(resolved, project_root),
                    "referenced_by": [],
                    "data": data,
                },
            )
            if procedure_id not in record["referenced_by"]:
                record["referenced_by"].append(procedure_id)

    for raw_path in args.missing_evidence:
        resolved, data = load_bounded_json(
            raw_path, project_root, "Missing-evidence input"
        )
        if resolved.name != "missing_evidence.json":
            raise AssemblyError(
                f"Missing-evidence input must be missing_evidence.json: {raw_path}"
            )
        missing.setdefault(
            resolved,
            {
                "source": display_path(resolved, project_root),
                "referenced_by": [],
                "data": data,
            },
        )

    return {
        "schema_version": "1.0",
        "current_strategy_id": args.strategy_id,
        "sources": {
            "strategy_artifact": display_path(strategy_path, project_root),
            **(
                {"original_strategy_artifact": display_path(original_strategy_path, project_root)}
                if original_strategy_path
                else {}
            ),
            "recipe_index": display_path(recipe_index_path, project_root),
        },
        "strategy_context": context,
        "procedure_diagnoses": diagnosis_output,
        "scientific_outputs": list(evidence.values()),
        "missing_evidence": list(missing.values()),
    }


def main() -> int:
    args = parse_args()
    try:
        payload = assemble(args)
        output = bounded_path(args.output, args.project_root.resolve())
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except AssemblyError as exc:
        raise SystemExit(str(exc)) from exc
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
