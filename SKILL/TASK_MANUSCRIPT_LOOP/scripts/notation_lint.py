from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

from validator_common import JsonMap, JsonValue, ValidationError, load_data, parse_document, require_map


REQUIRED_CATEGORIES: Final = ("systems", "methods", "energies", "figures", "abbreviations")


def lint_notation(notation_path: Path, sections_dir: Path) -> None:
    data = require_map(load_data(notation_path), str(notation_path))
    errors: list[str] = []
    definitions = _collect_definitions(data, errors)
    if not sections_dir.exists():
        errors.append(f"{sections_dir}: sections directory does not exist")
    if sections_dir.exists():
        for section in sorted(sections_dir.glob("*.md")):
            _lint_section(section, definitions, errors)
    if errors:
        raise ValidationError(tuple(errors))


def _collect_definitions(data: JsonMap, errors: list[str]) -> set[str]:
    definitions: set[str] = set()
    for category in REQUIRED_CATEGORIES:
        value = data.get(category)
        if not isinstance(value, list):
            errors.append(f"{category}: expected list")
            continue
        for index, entry in enumerate(value, start=1):
            label = f"{category}[{index}]"
            if not isinstance(entry, dict):
                errors.append(f"{label}: expected mapping")
                continue
            _add_entry_definitions(category, entry, label, definitions, errors)
    return definitions


def _add_entry_definitions(
    category: str,
    entry: JsonMap,
    label: str,
    definitions: set[str],
    errors: list[str],
) -> None:
    if category == "systems":
        _add_required(entry, "id", label, definitions, errors)
        _add_required(entry, "canonical", label, definitions, errors)
        aliases = entry.get("aliases")
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str) and alias:
                    definitions.add(alias)
        return
    if category == "methods":
        _add_required(entry, "id", label, definitions, errors)
        _add_required(entry, "canonical", label, definitions, errors)
        return
    if category == "energies":
        _add_required(entry, "symbol", label, definitions, errors)
        _add_required(entry, "meaning", label, definitions, errors)
        _add_required(entry, "units", label, definitions, errors)
        return
    if category == "figures":
        _add_required(entry, "id", label, definitions, errors)
        _add_required(entry, "label", label, definitions, errors)
        return
    if category == "abbreviations":
        _add_required(entry, "short", label, definitions, errors)
        _add_required(entry, "long", label, definitions, errors)
        return
    errors.append(f"{label}: unknown notation category {category}")


def _add_required(entry: JsonMap, field: str, label: str, definitions: set[str], errors: list[str]) -> None:
    value = entry.get(field)
    if isinstance(value, str) and value.strip():
        definitions.add(value)
        return
    errors.append(f"{label}.{field}: expected non-empty string")


def _lint_section(path: Path, definitions: set[str], errors: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    front_matter = _front_matter(text, path)
    body = _body_without_front_matter(text)
    declared = _declared_notation(front_matter, path, errors)
    for item in declared:
        if item not in definitions:
            errors.append(f"{path}: missing notation definition for {item}")
        if item not in body:
            errors.append(f"{path}: required notation {item} is not covered in section text")


def _front_matter(text: str, path: Path) -> JsonMap:
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


def _body_without_front_matter(text: str) -> str:
    if not text.startswith("---"):
        return text
    marker = text.find("\n---", 3)
    if marker == -1:
        return text
    return text[marker + 4 :]


def _declared_notation(front_matter: JsonMap, path: Path, errors: list[str]) -> list[str]:
    declared: list[str] = []
    for key in ("required_notation", "used_notation", "notation"):
        value = front_matter.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            errors.append(f"{path}: {key} must be a list")
            continue
        for item in value:
            if isinstance(item, str) and item.strip():
                declared.append(item)
            else:
                errors.append(f"{path}: {key} contains non-string item")
    return declared


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint section notation declarations against paper/logic/notation.yaml.")
    parser.add_argument("notation", type=Path)
    parser.add_argument("sections", type=Path)
    args = parser.parse_args(argv)
    try:
        lint_notation(args.notation, args.sections)
    except ValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"notation ok: {args.notation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
