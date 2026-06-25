from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

from validate_claim_matrix import JsonValue, ValidationError, load_data, require_map


ISSUE_FIELDS: Final = (
    "id",
    "reviewer",
    "severity",
    "target_type",
    "target_id",
    "summary",
    "evidence_paths",
    "required_action",
    "status",
)
SEVERITIES: Final = {"BLOCKER", "MAJOR", "MINOR"}
STATUSES: Final = {"open", "accepted", "resolved", "deferred", "rejected-with-rationale"}
RESOLVED_STATUSES: Final = {"resolved", "deferred", "rejected-with-rationale"}


def validate_reviewer_issues(path: Path) -> None:
    data = require_map(load_data(path), str(path))
    issues = data.get("issues")
    errors: list[str] = []
    if not isinstance(issues, list):
        errors.append("issues: expected list")
    seen_ids: set[str] = set()
    if isinstance(issues, list):
        for index, issue in enumerate(issues, start=1):
            _validate_issue(issue, index, seen_ids, errors)
    if errors:
        raise ValidationError(tuple(errors))


def _validate_issue(raw_issue: JsonValue, index: int, seen_ids: set[str], errors: list[str]) -> None:
    label = f"issues[{index}]"
    if not isinstance(raw_issue, dict):
        errors.append(f"{label}: expected mapping")
        return
    for field in ISSUE_FIELDS:
        if field not in raw_issue:
            errors.append(f"{label}: missing required field {field}")
    issue_id = _read_str(raw_issue.get("id"), f"{label}.id", errors)
    if issue_id in seen_ids:
        errors.append(f"{label}: duplicate issue id {issue_id}")
    if issue_id:
        seen_ids.add(issue_id)
    severity = _read_str(raw_issue.get("severity"), f"{label}.severity", errors)
    status = _read_str(raw_issue.get("status"), f"{label}.status", errors)
    if severity and severity not in SEVERITIES:
        errors.append(f"{label}: invalid severity {severity}")
    if status and status not in STATUSES:
        errors.append(f"{label}: invalid status {status}")
    if severity == "BLOCKER" and status not in RESOLVED_STATUSES:
        errors.append(f"{label}: unresolved BLOCKER issue {issue_id}")
    evidence_paths = raw_issue.get("evidence_paths")
    if not isinstance(evidence_paths, list) or not evidence_paths:
        errors.append(f"{label}.evidence_paths: expected non-empty list")


def _read_str(value: JsonValue, label: str, errors: list[str]) -> str:
    if isinstance(value, str) and value.strip():
        return value
    errors.append(f"{label}: expected non-empty string")
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate reviewer issues and reject unresolved BLOCKER items.")
    parser.add_argument("reviewer_issues", type=Path)
    args = parser.parse_args(argv)
    try:
        validate_reviewer_issues(args.reviewer_issues)
    except ValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"reviewer-issues ok: {args.reviewer_issues}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
