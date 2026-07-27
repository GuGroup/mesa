#!/usr/bin/env python3
"""Project a saved experimental extraction into an immutable claim-only JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SECTION = "author_reported_claim"
REQUIRED_FIELDS = ("statement", "abstract", "conclusion")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract exactly one author_reported_claim without other context."
    )
    parser.add_argument("extraction", type=Path, help="Saved extraction artifact.")
    parser.add_argument("--output", type=Path, help="Optional claim-only JSON path.")
    return parser.parse_args()


def normalize_heading(line: str) -> str:
    heading = line.strip().lstrip("#").strip()
    if heading.startswith("- "):
        heading = heading[2:].strip()
    return heading.rstrip(":").strip()


def response_output_text(value: dict[str, Any]) -> str | None:
    direct = value.get("output_text")
    if isinstance(direct, str) and direct:
        return direct

    chunks: list[str] = []
    output = value.get("output")
    if not isinstance(output, list):
        return None
    for item in output:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks) if chunks else None


def find_claim_objects(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        claim = value.get(SECTION)
        if isinstance(claim, dict):
            found.append(claim)
        for child in value.values():
            found.extend(find_claim_objects(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(find_claim_objects(child))
    return found


def validate_claim(claim: dict[str, Any]) -> dict[str, Any]:
    source_locations = claim.get("source_locations")
    if not isinstance(source_locations, dict):
        raise SystemExit("author_reported_claim must contain source_locations")

    normalized = {
        "statement": claim.get("statement"),
        "source_locations": {
            "abstract": source_locations.get("abstract"),
            "conclusion": source_locations.get("conclusion"),
        },
    }
    values = {
        "statement": normalized["statement"],
        "abstract": normalized["source_locations"]["abstract"],
        "conclusion": normalized["source_locations"]["conclusion"],
    }
    for field in REQUIRED_FIELDS:
        if not isinstance(values[field], str) or not values[field].strip():
            raise SystemExit(f"author_reported_claim has no non-empty {field} value")
    return normalized


def claim_from_text(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    starts = [
        index for index, line in enumerate(lines) if normalize_heading(line) == SECTION
    ]
    if len(starts) != 1:
        raise SystemExit("Expected exactly one author_reported_claim section")

    values: dict[str, str] = {}
    for line in lines[starts[0] + 1 :]:
        stripped = line.strip()
        if not stripped:
            if all(field in values for field in REQUIRED_FIELDS):
                break
            continue
        for field in REQUIRED_FIELDS:
            prefix = f"- {field}:"
            if stripped.startswith(prefix):
                if field in values:
                    raise SystemExit(f"author_reported_claim contains duplicate {field}")
                values[field] = stripped[len(prefix) :].strip()
                break

    missing = [field for field in REQUIRED_FIELDS if not values.get(field)]
    if missing:
        raise SystemExit(
            "author_reported_claim is missing: " + ", ".join(missing)
        )
    return {
        "statement": values["statement"],
        "source_locations": {
            "abstract": values["abstract"],
            "conclusion": values["conclusion"],
        },
    }


def load_claim(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"Extraction artifact does not exist: {path}")
    text = path.read_text(encoding="utf-8")

    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = None

    if value is not None:
        claims = find_claim_objects(value)
        if len(claims) == 1:
            return validate_claim(claims[0])
        if len(claims) > 1:
            raise SystemExit("Expected exactly one author_reported_claim object")
        if isinstance(value, dict) and (output_text := response_output_text(value)):
            return claim_from_text(output_text)

    return claim_from_text(text)


def main() -> int:
    args = parse_args()
    claim = load_claim(args.extraction)
    result = {
        SECTION: {
            **claim,
            "extraction_artifact": str(args.extraction.resolve()),
        }
    }
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
