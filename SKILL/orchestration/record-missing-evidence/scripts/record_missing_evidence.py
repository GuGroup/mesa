#!/usr/bin/env python3
"""Record missing scientific evidence without proxy substitution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ALLOWED_STATUS = {"excluded", "blocked", "unresolved"}
TERMINAL_REPAIR_DECISIONS = {"no_repair", "escalate"}


def main() -> int:
    args = parse_args()
    spec = json.loads(args.input.expanduser().read_text(encoding="utf-8"))
    root = args.project_root.expanduser().resolve() if args.project_root else Path.cwd().resolve()
    diagnosis_path, repair_decision_path = validate_spec(spec, root)
    output = args.output.expanduser().resolve()
    if output.name != "missing_evidence.json":
        raise SystemExit("output filename must be missing_evidence.json")
    if output.parent != diagnosis_path.parent:
        raise SystemExit(
            "missing_evidence.json must be beside the terminal diagnosis and repair decision"
        )

    record = {
        "schema_version": 1,
        "strategy_id": spec.get("strategy_id"),
        "procedure_id": spec.get("procedure_id"),
        "execution_unit_id": spec["execution_unit_id"],
        "source_recipe": spec["source_recipe"],
        "source_diagnosis": rel(diagnosis_path, root),
        "source_repair_decision": rel(repair_decision_path, root),
        "status": spec["status"],
        "reason": spec["reason"],
        "not_substituted_with_proxy": True,
        "required_future_artifacts": spec.get("required_future_artifacts", []),
        "requirements": spec["requirements"],
    }

    write_json(output, record)

    print(json.dumps({
        "status": spec["status"],
        "requirement_count": len(spec["requirements"]),
        "output": rel(output, root),
    }, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write one canonical missing-evidence JSON after terminal E handling.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--project-root", type=Path, default=None)
    return parser.parse_args()


def validate_spec(spec: dict[str, Any], root: Path) -> tuple[Path, Path]:
    if not isinstance(spec, dict):
        raise SystemExit("input must be a JSON object")
    if spec.get("status") not in ALLOWED_STATUS:
        raise SystemExit(f"status must be one of {sorted(ALLOWED_STATUS)}")
    if not spec.get("reason"):
        raise SystemExit("reason is required")
    if not spec.get("procedure_id"):
        raise SystemExit("procedure_id is required")
    if not spec.get("execution_unit_id"):
        raise SystemExit("execution_unit_id is required")
    if not spec.get("source_recipe"):
        raise SystemExit("source_recipe is required")
    if spec.get("not_substituted_with_proxy") is not True:
        raise SystemExit("not_substituted_with_proxy must be true")
    requirements = spec.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise SystemExit("requirements must be a non-empty list")
    for requirement in requirements:
        if not isinstance(requirement, dict):
            raise SystemExit("each requirement must be an object")
        if requirement.get("status") not in ALLOWED_STATUS:
            raise SystemExit("each requirement status must be excluded, blocked, or unresolved")
        if not requirement.get("missing_artifacts"):
            raise SystemExit("each requirement must list missing_artifacts")

    diagnosis_path = required_artifact_path(spec, "source_diagnosis", root)
    repair_decision_path = required_artifact_path(spec, "source_repair_decision", root)
    diagnosis = read_json_object(diagnosis_path, "source_diagnosis")
    repair_decision = read_json_object(repair_decision_path, "source_repair_decision")
    execution_unit_id = spec["execution_unit_id"]

    if diagnosis_path.parent != repair_decision_path.parent:
        raise SystemExit("source_diagnosis and source_repair_decision must be in the same E attempt")
    if diagnosis.get("execution_unit_id") != execution_unit_id:
        raise SystemExit("source_diagnosis execution_unit_id does not match the spec")
    if diagnosis.get("diagnosis_status") not in {"complete", "insufficient_evidence"}:
        raise SystemExit(
            "source_diagnosis diagnosis_status must be complete or insufficient_evidence"
        )
    if diagnosis.get("verdict") == "pass":
        raise SystemExit("source_diagnosis verdict pass cannot support a missing-evidence record")
    if diagnosis.get("verdict") not in {"warn", "fail", "unknown"}:
        raise SystemExit("source_diagnosis verdict must be warn, fail, or unknown")

    if repair_decision.get("execution_unit_id") != execution_unit_id:
        raise SystemExit("source_repair_decision execution_unit_id does not match the spec")
    if repair_decision.get("decision") not in TERMINAL_REPAIR_DECISIONS:
        raise SystemExit(
            "source_repair_decision must be terminal: no_repair or escalate"
        )
    linked_diagnosis = repair_decision.get("source_diagnosis")
    if not linked_diagnosis:
        raise SystemExit("source_repair_decision must identify source_diagnosis")
    if not reference_matches(linked_diagnosis, diagnosis_path, root, repair_decision_path.parent):
        raise SystemExit("source_repair_decision does not reference source_diagnosis")

    return diagnosis_path, repair_decision_path


def required_artifact_path(spec: dict[str, Any], key: str, root: Path) -> Path:
    value = spec.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"{key} is required")
    path = Path(value).expanduser()
    path = path if path.is_absolute() else root / path
    path = path.resolve()
    if not path.is_file():
        raise SystemExit(f"{key} does not exist: {path}")
    return path


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{label} must contain a JSON object")
    return payload


def reference_matches(value: Any, expected: Path, root: Path, local_dir: Path) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    path = Path(value).expanduser()
    candidates = [path] if path.is_absolute() else [root / path, local_dir / path]
    return any(candidate.resolve() == expected.resolve() for candidate in candidates)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
