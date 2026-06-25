#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import re
import sys
from typing import Optional, Union


class Severity(str, Enum):
    BLOCKER = "BLOCKER"; MAJOR = "MAJOR"; MINOR = "MINOR"


class Status(str, Enum):
    OPEN = "open"; ACCEPTED = "accepted"; RESOLVED = "resolved"
    DEFERRED = "deferred"; REJECTED = "rejected-with-rationale"


@dataclass(frozen=True)  # noqa: SLOTS_OK -- verifier uses Python 3.9, where dataclass slots are unavailable.
class MergeInputError(Exception):
    path: Path
    detail: str

    def __str__(self) -> str:
        return f"{self.path}: {self.detail}"


@dataclass(frozen=True)  # noqa: SLOTS_OK -- verifier uses Python 3.9, where dataclass slots are unavailable.
class Issue:
    source_path: Path
    source_id: str
    reviewer: str
    severity: Severity
    target_type: str
    target_id: str
    summary: str
    evidence_paths: tuple[str, ...]
    required_action: str
    status: Status

    def merge_key(self) -> tuple[str, str, str, str]:
        return (self.target_type, self.target_id, normalized_text(self.summary), normalized_text(self.required_action))


@dataclass(frozen=True)  # noqa: SLOTS_OK -- verifier uses Python 3.9, where dataclass slots are unavailable.
class MergedIssue:
    stable_id: str
    reviewers: tuple[str, ...]
    source_issue_ids: tuple[str, ...]
    severity: Severity
    target_type: str
    target_id: str
    summary: str
    evidence_paths: tuple[str, ...]
    required_action: str
    status: Status


@dataclass(frozen=True)  # noqa: SLOTS_OK -- verifier uses Python 3.9, where dataclass slots are unavailable.
class MergeResult:
    issues: tuple[MergedIssue, ...]
    warnings: tuple[str, ...]


RawValue = Union[str, list[str]]
RawIssue = dict[str, RawValue]

SEVERITY_RANK = {Severity.BLOCKER: 0, Severity.MAJOR: 1, Severity.MINOR: 2}
STATUS_RANK = {Status.OPEN: 0, Status.ACCEPTED: 1, Status.DEFERRED: 2, Status.RESOLVED: 3, Status.REJECTED: 4}
SCALAR_RE = re.compile(r"^[A-Za-z0-9_./:@+-]+$")


def normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


def parse_scalar(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def parse_issue_file(path: Path) -> tuple[Issue, ...]:
    issues = parse_raw_issues(path)
    return tuple(parse_issue(path, raw) for raw in issues)


def parse_raw_issues(path: Path) -> tuple[RawIssue, ...]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MergeInputError(path=path, detail=str(exc)) from exc
    lines = text.splitlines()
    issues: list[RawIssue] = []
    current: Optional[RawIssue] = None
    list_key: Optional[str] = None
    in_issues = False
    for raw_line in lines:
        stripped = raw_line.strip()
        if stripped == "" or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if stripped == "issues:":
            in_issues = True
            continue
        if not in_issues:
            continue
        if stripped.startswith("- ") and indent == 2:
            if current is not None:
                issues.append(current)
            current = {}
            list_key = None
            body = stripped[2:]
            if ":" not in body:
                raise MergeInputError(path=path, detail=f"cannot parse issue item: {body}")
            key, value = body.split(":", 1)
            current[key.strip()] = parse_scalar(value)
            continue
        if current is None:
            raise MergeInputError(path=path, detail="issue entry found before list item")
        if stripped.startswith("- "):
            if list_key is None:
                raise MergeInputError(path=path, detail="list value without list key")
            current_list = current[list_key]
            if isinstance(current_list, list):
                current_list.append(parse_scalar(stripped[2:]))
                continue
            raise MergeInputError(path=path, detail=f"{list_key} is not a list")
        if ":" not in stripped:
            raise MergeInputError(path=path, detail=f"cannot parse line: {stripped}")
        key, value = stripped.split(":", 1)
        if value.strip() == "":
            current[key.strip()] = []
            list_key = key.strip()
        else:
            current[key.strip()] = parse_scalar(value)
            list_key = None
    if current is not None:
        issues.append(current)
    if not issues:
        raise MergeInputError(path=path, detail="missing issues list")
    return tuple(issues)


def parse_issue(path: Path, raw: RawIssue) -> Issue:
    missing = [
        field
        for field in ("id", "severity", "target_type", "target_id", "summary", "evidence_paths", "required_action", "status")
        if field not in raw
    ]
    reviewer_field = "reviewer" if "reviewer" in raw else "reviewer_role"
    if reviewer_field not in raw:
        missing.append("reviewer")
    if missing:
        raise MergeInputError(path=path, detail=f"missing required fields: {', '.join(sorted(missing))}")
    evidence = raw["evidence_paths"]
    if not isinstance(evidence, list) or not evidence:
        raise MergeInputError(path=path, detail="evidence_paths must be a non-empty list")
    try:
        return Issue(
            path, string_field(raw, "id"), string_field(raw, reviewer_field), Severity(string_field(raw, "severity")),
            string_field(raw, "target_type"), string_field(raw, "target_id"), string_field(raw, "summary"),
            tuple(evidence), string_field(raw, "required_action"), Status(string_field(raw, "status"))
        )
    except ValueError as exc:
        raise MergeInputError(path=path, detail=str(exc)) from exc


def string_field(raw: RawIssue, field: str) -> str:
    value = raw[field]
    if isinstance(value, str):
        return value
    raise MergeInputError(path=Path("<memory>"), detail=f"{field} must be a scalar")


def merge_issues(issues: tuple[Issue, ...]) -> MergeResult:
    warnings: list[str] = []
    seen: dict[str, tuple[str, str, str, str]] = {}
    grouped: dict[tuple[str, str, str, str], list[Issue]] = {}
    for issue in sorted_issues(issues):
        if issue.source_id in seen:
            warnings.append(f"duplicate source issue id {issue.source_id}")
        seen[issue.source_id] = issue.merge_key()
        grouped.setdefault(issue.merge_key(), []).append(issue)
    merged: list[MergedIssue] = []
    for stable_index, key in enumerate(sorted(grouped), start=1):
        group = grouped[key]
        if len(group) > 1:
            warnings.append(f"merged duplicate target {key[0]}:{key[1]}")
        merged.append(merge_group(stable_index, group))
    return MergeResult(issues=tuple(merged), warnings=tuple(warnings))


def sorted_issues(issues: tuple[Issue, ...]) -> tuple[Issue, ...]:
    return tuple(
        sorted(
            issues,
            key=lambda issue: (
                issue.target_type, issue.target_id, normalized_text(issue.summary),
                normalized_text(issue.required_action), issue.reviewer, issue.source_id, str(issue.source_path),
            ),
        )
    )


def merge_group(stable_index: int, group: list[Issue]) -> MergedIssue:
    sorted_group = sorted_issues(tuple(group))
    primary = sorted_group[0]
    return MergedIssue(
        f"M{stable_index:03d}", tuple(unique_sorted(issue.reviewer for issue in sorted_group)),
        tuple(unique_sorted(issue.source_id for issue in sorted_group)),
        min((issue.severity for issue in sorted_group), key=lambda severity: SEVERITY_RANK[severity]),
        primary.target_type, primary.target_id, primary.summary,
        tuple(unique_sorted(path for issue in sorted_group for path in issue.evidence_paths)),
        primary.required_action, min((issue.status for issue in sorted_group), key=lambda status: STATUS_RANK[status]),
    )


def unique_sorted(values: Iterable[str]) -> list[str]:
    return sorted(set(values))


def render_yaml(result: MergeResult) -> str:
    lines = ["version: 1", "issues:"]
    for issue in result.issues:
        lines.extend(render_issue(issue))
    return "\n".join(lines) + "\n"


def render_issue(issue: MergedIssue) -> list[str]:
    lines = [
        f"  - id: {issue.stable_id}",
        f"    reviewer: {format_scalar(issue.reviewers[0])}",
        "    reviewer_sources:",
    ]
    lines.extend(f"      - {format_scalar(reviewer)}" for reviewer in issue.reviewers)
    lines.extend(
        [
            "    source_issue_ids:",
            *(f"      - {format_scalar(source_id)}" for source_id in issue.source_issue_ids),
            f"    severity: {issue.severity.value}",
            f"    target_type: {format_scalar(issue.target_type)}",
            f"    target_id: {format_scalar(issue.target_id)}",
            f"    summary: {format_scalar(issue.summary)}",
            "    evidence_paths:",
            *(f"      - {format_scalar(path)}" for path in issue.evidence_paths),
            f"    required_action: {format_scalar(issue.required_action)}",
            f"    status: {issue.status.value}",
        ]
    )
    return lines


def format_scalar(value: str) -> str:
    if SCALAR_RE.fullmatch(value):
        return value
    return json.dumps(value, ensure_ascii=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge reviewer issue YAML files into a deterministic reviewer-issues.yaml."
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="Reviewer issue YAML files to merge.")
    parser.add_argument("--output", "-o", required=True, type=Path, help="Merged reviewer-issues.yaml path.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        issues = tuple(issue for path in args.inputs for issue in parse_issue_file(path))
        result = merge_issues(issues)
        args.output.write_text(render_yaml(result), encoding="utf-8")
        for warning in result.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        return 0
    except MergeInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
