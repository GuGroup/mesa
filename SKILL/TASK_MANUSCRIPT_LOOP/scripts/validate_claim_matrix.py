from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

from validator_common import (
    JsonMap,
    JsonValue,
    ValidationError,
    infer_paper_root,
    load_data,
    require_list,
    require_map,
    require_str,
    resolve_paper_path,
)

ALLOWED_LEVELS: Final = {"main", "supporting", "method", "context"}
ALLOWED_STATUSES: Final = {"supported", "qualified", "blocked", "excluded", "draft"}
ALLOWED_RELATIONS: Final = {"direct", "derived", "context", "negative"}
EVIDENCE_PREFIXES: Final = ("paper/inputs/", "paper/figures/", "paper/logic/")
CLAIM_FIELDS: Final = (
    "id",
    "level",
    "statement",
    "status",
    "evidence",
    "figures",
    "assumptions",
    "caveats",
    "risks",
    "allowed_sections",
)
EVIDENCE_FIELDS: Final = ("id", "source_id", "path", "relation", "summary")


def claim_ids_from_matrix(path: Path) -> set[str]:
    data = require_map(load_data(path), str(path))
    claims = require_list(data.get("claims"), "claims")
    return {require_str(require_map(claim, "claim").get("id"), "claim.id") for claim in claims}


def validate_claim_matrix(path: Path) -> None:
    data = require_map(load_data(path), str(path))
    errors: list[str] = []
    claims_value = data.get("claims")
    if not isinstance(claims_value, list) or not claims_value:
        errors.append("claims: expected at least one claim")
    paper_root = infer_paper_root(path)
    seen_ids: set[str] = set()
    if isinstance(claims_value, list):
        for index, raw_claim in enumerate(claims_value, start=1):
            _validate_claim(raw_claim, index, paper_root, seen_ids, errors)
    if errors:
        raise ValidationError(tuple(errors))


def _validate_claim(
    raw_claim: JsonValue,
    index: int,
    paper_root: Path | None,
    seen_ids: set[str],
    errors: list[str],
) -> None:
    claim_label = f"claims[{index}]"
    if not isinstance(raw_claim, dict):
        errors.append(f"{claim_label}: expected mapping")
        return
    for field in CLAIM_FIELDS:
        if field not in raw_claim:
            errors.append(f"{claim_label}: missing required field {field}")
    claim_id = _field_str(raw_claim, "id", claim_label, errors)
    if claim_id in seen_ids:
        errors.append(f"{claim_label}: duplicate claim id {claim_id}")
    if claim_id:
        seen_ids.add(claim_id)
    level = _field_str(raw_claim, "level", claim_label, errors)
    status = _field_str(raw_claim, "status", claim_label, errors)
    if level and level not in ALLOWED_LEVELS:
        errors.append(f"{claim_label}: invalid level {level}")
    if status and status not in ALLOWED_STATUSES:
        errors.append(f"{claim_label}: invalid status {status}; unsupported claims must be blocked, excluded, or rewritten")
    evidence = raw_claim.get("evidence")
    has_evidence = isinstance(evidence, list) and bool(evidence)
    direct_evidence = _validate_evidence(evidence, claim_label, paper_root, errors)
    if status in {"supported", "qualified"} and not has_evidence:
        errors.append(f"{claim_label}: status {status} requires evidence")
    if level == "main" and status not in {"blocked", "excluded"} and not direct_evidence:
        errors.append(f"{claim_label}: main claim requires direct evidence unless blocked or excluded")
    caveats = raw_claim.get("caveats")
    if status == "qualified" and (not isinstance(caveats, list) or not caveats):
        errors.append(f"{claim_label}: qualified claim requires caveats")
    for field in ("figures", "assumptions", "caveats", "risks", "allowed_sections"):
        if field in raw_claim and not isinstance(raw_claim[field], list):
            errors.append(f"{claim_label}.{field}: expected list")


def _validate_evidence(
    evidence: JsonValue,
    claim_label: str,
    paper_root: Path | None,
    errors: list[str],
) -> bool:
    if not isinstance(evidence, list):
        errors.append(f"{claim_label}.evidence: expected list")
        return False
    direct_evidence = False
    for index, raw_record in enumerate(evidence, start=1):
        record_label = f"{claim_label}.evidence[{index}]"
        if not isinstance(raw_record, dict):
            errors.append(f"{record_label}: expected mapping")
            continue
        for field in EVIDENCE_FIELDS:
            if field not in raw_record:
                errors.append(f"{record_label}: missing required field {field}")
        relation = _field_str(raw_record, "relation", record_label, errors)
        if relation == "direct":
            direct_evidence = True
        if relation and relation not in ALLOWED_RELATIONS:
            errors.append(f"{record_label}: invalid relation {relation}")
        raw_path = _field_str(raw_record, "path", record_label, errors)
        if raw_path:
            if not raw_path.startswith(EVIDENCE_PREFIXES):
                errors.append(f"{record_label}: evidence path outside paper inputs/figures/logic: {raw_path}")
                continue
            try:
                resolved = resolve_paper_path(paper_root, raw_path, EVIDENCE_PREFIXES)
            except ValidationError as exc:
                errors.extend(exc.errors)
                continue
            if resolved is not None and not resolved.exists():
                errors.append(f"{record_label}: missing evidence path {raw_path}")
    return direct_evidence


def _field_str(data: JsonMap, field: str, label: str, errors: list[str]) -> str:
    value = data.get(field)
    if isinstance(value, str) and value.strip():
        return value
    if field in data:
        errors.append(f"{label}.{field}: expected non-empty string")
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a claim matrix. YAML support is a simple JSON-compatible subset: mappings, lists, scalars, and inline lists.",
    )
    parser.add_argument("claim_matrix", type=Path)
    args = parser.parse_args(argv)
    try:
        validate_claim_matrix(args.claim_matrix)
    except ValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"claim-matrix ok: {args.claim_matrix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
