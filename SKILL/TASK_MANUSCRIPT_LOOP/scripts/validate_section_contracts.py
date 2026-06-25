from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

from validate_claim_matrix import claim_ids_from_matrix
from validator_common import (
    JsonMap,
    JsonValue,
    ValidationError,
    infer_paper_root,
    load_data,
    parse_document,
    require_map,
    resolve_paper_path,
    string_items,
)


SECTION_FIELDS: Final = (
    "id",
    "path",
    "status",
    "allowed_claims",
    "required_figures",
    "required_sources",
    "required_caveats",
    "blocked_by",
    "chunk_policy",
)
STATUSES: Final = {"not-ready", "ready-to-draft", "drafted", "locked", "blocked"}
REQUIRED_SOURCE_PREFIXES: Final = ("paper/inputs/", "paper/logic/", "paper/figures/")
SECTION_FILE_PREFIX: Final = "paper/manuscript/sections/"


def validate_section_contracts(path: Path, claims_path: Path | None) -> None:
    data = require_map(load_data(path), str(path))
    sections = data.get("sections")
    errors: list[str] = []
    if not isinstance(sections, list) or not sections:
        errors.append("sections: expected at least one section")
    known_claim_ids = claim_ids_from_matrix(claims_path) if claims_path is not None else _infer_claim_ids(path)
    paper_root = infer_paper_root(claims_path) if claims_path is not None else infer_paper_root(path)
    seen_ids: set[str] = set()
    if isinstance(sections, list):
        for index, section in enumerate(sections, start=1):
            _validate_section(section, index, known_claim_ids, paper_root, seen_ids, errors)
    if errors:
        raise ValidationError(tuple(errors))


def _infer_claim_ids(path: Path) -> set[str]:
    paper_root = infer_paper_root(path)
    if paper_root is None:
        return set()
    claim_path = paper_root / "logic" / "claim-matrix.yaml"
    return claim_ids_from_matrix(claim_path) if claim_path.exists() else set()


def _validate_section(
    raw_section: JsonValue,
    index: int,
    known_claim_ids: set[str],
    paper_root: Path | None,
    seen_ids: set[str],
    errors: list[str],
) -> None:
    label = f"sections[{index}]"
    if not isinstance(raw_section, dict):
        errors.append(f"{label}: expected mapping")
        return
    section: JsonMap = raw_section
    for field in SECTION_FIELDS:
        if field not in section:
            errors.append(f"{label}: missing required field {field}")
    section_id = _read_str(section, "id", label, errors)
    if section_id in seen_ids:
        errors.append(f"{label}: duplicate section id {section_id}")
    if section_id:
        seen_ids.add(section_id)
    status = _read_str(section, "status", label, errors)
    if status and status not in STATUSES:
        errors.append(f"{label}: invalid status {status}")
    allowed_claims = _read_string_list(section, "allowed_claims", label, errors)
    for claim_id in allowed_claims:
        if known_claim_ids and claim_id not in known_claim_ids:
            errors.append(f"{label}: disallowed or stale claim id {claim_id}")
    _validate_required_sources(section, paper_root, label, errors)
    _validate_section_file(section, allowed_claims, paper_root, label, errors)


def _validate_required_sources(section: JsonMap, paper_root: Path | None, label: str, errors: list[str]) -> None:
    for raw_path in _read_string_list(section, "required_sources", label, errors):
        if not raw_path.startswith(REQUIRED_SOURCE_PREFIXES):
            errors.append(f"{label}.required_sources: path outside paper source roots: {raw_path}")
            continue
        try:
            resolved = resolve_paper_path(paper_root, raw_path, REQUIRED_SOURCE_PREFIXES)
        except ValidationError as exc:
            errors.extend(exc.errors)
            continue
        if resolved is not None and not resolved.exists():
            errors.append(f"{label}.required_sources: missing source {raw_path}")


def _validate_section_file(
    section: JsonMap,
    allowed_claims: list[str],
    paper_root: Path | None,
    label: str,
    errors: list[str],
) -> None:
    raw_path = section.get("path")
    if not isinstance(raw_path, str):
        return
    if not raw_path.startswith(SECTION_FILE_PREFIX):
        errors.append(f"{label}.path: path outside {SECTION_FILE_PREFIX}: {raw_path}")
        return
    try:
        resolved = resolve_paper_path(paper_root, raw_path, (SECTION_FILE_PREFIX,))
    except ValidationError as exc:
        errors.extend(exc.errors)
        return
    if resolved is None or not resolved.exists():
        return
    front_matter = _front_matter(resolved)
    for key in ("claims", "claim_ids", "used_claims", "allowed_claims"):
        value = front_matter.get(key)
        if value is None:
            continue
        for claim_id in _strings_or_errors(value, f"{label}.{key}", errors):
            if claim_id not in allowed_claims:
                errors.append(f"{label}: section file uses disallowed claim id {claim_id}")


def _front_matter(path: Path) -> JsonMap:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    marker = text.find("\n---", 3)
    if marker == -1:
        return {}
    raw = text[3:marker].strip()
    if not raw:
        return {}
    value = parse_document(raw, path)
    return value if isinstance(value, dict) else {}


def _strings_or_errors(value: JsonValue, label: str, errors: list[str]) -> list[str]:
    try:
        return string_items(value, label)
    except ValidationError as exc:
        errors.extend(exc.errors)
        return []


def _read_str(data: JsonMap, field: str, label: str, errors: list[str]) -> str:
    value = data.get(field)
    if isinstance(value, str) and value.strip():
        return value
    if field in data:
        errors.append(f"{label}.{field}: expected non-empty string")
    return ""


def _read_string_list(data: JsonMap, field: str, label: str, errors: list[str]) -> list[str]:
    return _strings_or_errors(data.get(field), f"{label}.{field}", errors)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate section contracts against claim IDs and section front matter.")
    parser.add_argument("section_contracts", type=Path)
    parser.add_argument("--claims", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        validate_section_contracts(args.section_contracts, args.claims)
    except ValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"section-contracts ok: {args.section_contracts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
