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
    require_list,
    require_map,
    require_str,
    resolve_paper_path,
    string_items,
)


FIGURE_FIELDS: Final = (
    "id",
    "label",
    "role",
    "title",
    "claim_ids",
    "source_files",
    "exported_files",
    "qa_files",
    "status",
    "blockers",
)
ALLOWED_ROLES: Final = {"main", "extended-data", "si", "candidate"}
ALLOWED_STATUSES: Final = {"planned", "needs-source", "generated", "qa-passed", "blocked", "excluded"}
FILE_PREFIXES: Final = {
    "source_files": "paper/figures/source/",
    "exported_files": "paper/figures/exported/",
    "qa_files": "paper/figures/qa/",
}


def validate_figure_map(path: Path, claims_path: Path | None) -> None:
    data = require_map(load_data(path), str(path))
    errors: list[str] = []
    claim_ids = claim_ids_from_matrix(claims_path) if claims_path is not None else _infer_claim_ids(path)
    paper_root = infer_paper_root(claims_path) if claims_path is not None else infer_paper_root(path)
    figures = data.get("figures")
    if not isinstance(figures, list) or not figures:
        errors.append("figures: expected at least one figure")
    seen_ids: set[str] = set()
    if isinstance(figures, list):
        for index, figure in enumerate(figures, start=1):
            _validate_figure(figure, index, claim_ids, paper_root, seen_ids, errors)
    if errors:
        raise ValidationError(tuple(errors))


def _infer_claim_ids(path: Path) -> set[str]:
    paper_root = infer_paper_root(path)
    if paper_root is None:
        return set()
    claim_path = paper_root / "logic" / "claim-matrix.yaml"
    return claim_ids_from_matrix(claim_path) if claim_path.exists() else set()


def _validate_figure(
    raw_figure: JsonValue,
    index: int,
    known_claim_ids: set[str],
    paper_root: Path | None,
    seen_ids: set[str],
    errors: list[str],
) -> None:
    label = f"figures[{index}]"
    if not isinstance(raw_figure, dict):
        errors.append(f"{label}: expected mapping")
        return
    figure: JsonMap = raw_figure
    for field in FIGURE_FIELDS:
        if field not in figure:
            errors.append(f"{label}: missing required field {field}")
    figure_id = _read_str(figure, "id", label, errors)
    if figure_id in seen_ids:
        errors.append(f"{label}: duplicate figure id {figure_id}")
    if figure_id:
        seen_ids.add(figure_id)
    role = _read_str(figure, "role", label, errors)
    status = _read_str(figure, "status", label, errors)
    if role and role not in ALLOWED_ROLES:
        errors.append(f"{label}: invalid role {role}")
    if status and status not in ALLOWED_STATUSES:
        errors.append(f"{label}: invalid status {status}")
    figure_claim_ids = _read_string_list(figure, "claim_ids", label, errors)
    if role == "main" and not figure_claim_ids:
        errors.append(f"{label}: main figure requires at least one claim_id")
    for claim_id in figure_claim_ids:
        if known_claim_ids and claim_id not in known_claim_ids:
            errors.append(f"{label}: stale claim reference {claim_id}")
    for field, prefix in FILE_PREFIXES.items():
        _validate_paths(figure, field, prefix, label, paper_root, errors)
    panels = figure.get("panels")
    if panels is not None:
        _validate_panels(panels, figure_claim_ids, known_claim_ids, paper_root, label, errors)


def _validate_panels(
    raw_panels: JsonValue,
    figure_claim_ids: list[str],
    known_claim_ids: set[str],
    paper_root: Path | None,
    figure_label: str,
    errors: list[str],
) -> None:
    if not isinstance(raw_panels, list):
        errors.append(f"{figure_label}.panels: expected list")
        return
    seen_panel_ids: set[str] = set()
    for index, raw_panel in enumerate(raw_panels, start=1):
        panel_label = f"{figure_label}.panels[{index}]"
        if not isinstance(raw_panel, dict):
            errors.append(f"{panel_label}: expected mapping")
            continue
        panel_id = _read_str(raw_panel, "id", panel_label, errors)
        if panel_id in seen_panel_ids:
            errors.append(f"{panel_label}: duplicate panel id {panel_id}")
        if panel_id:
            seen_panel_ids.add(panel_id)
        panel_claims = _read_string_list(raw_panel, "claim_ids", panel_label, errors)
        for claim_id in panel_claims:
            if claim_id not in figure_claim_ids:
                errors.append(f"{panel_label}: panel claim {claim_id} is not mapped by parent figure")
            if known_claim_ids and claim_id not in known_claim_ids:
                errors.append(f"{panel_label}: stale panel claim reference {claim_id}")
        if "source_files" in raw_panel:
            _validate_paths(raw_panel, "source_files", "paper/figures/source/", panel_label, paper_root, errors)


def _validate_paths(
    data: JsonMap,
    field: str,
    prefix: str,
    label: str,
    paper_root: Path | None,
    errors: list[str],
) -> None:
    paths = _read_string_list(data, field, label, errors)
    for raw_path in paths:
        if not raw_path.startswith(prefix):
            errors.append(f"{label}.{field}: path outside {prefix}: {raw_path}")
            continue
        try:
            resolved = resolve_paper_path(paper_root, raw_path, (prefix,))
        except ValidationError as exc:
            errors.extend(exc.errors)
            continue
        if resolved is not None and not resolved.exists():
            errors.append(f"{label}.{field}: missing referenced file {raw_path}")


def _read_str(data: JsonMap, field: str, label: str, errors: list[str]) -> str:
    value = data.get(field)
    if isinstance(value, str) and value.strip():
        return value
    if field in data:
        errors.append(f"{label}.{field}: expected non-empty string")
    return ""


def _read_string_list(data: JsonMap, field: str, label: str, errors: list[str]) -> list[str]:
    try:
        return string_items(data.get(field), f"{label}.{field}")
    except ValidationError as exc:
        errors.extend(exc.errors)
        return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a figure map against known claim IDs and figure file references.",
    )
    parser.add_argument("figure_map", type=Path)
    parser.add_argument("--claims", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        validate_figure_map(args.figure_map, args.claims)
    except ValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"figure-map ok: {args.figure_map}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
