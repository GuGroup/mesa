from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Union


JsonScalar = Union[str, int, float, bool, None]
JsonValue = Union[JsonScalar, list["JsonValue"], dict[str, "JsonValue"]]
JsonMap = dict[str, JsonValue]
JsonList = list[JsonValue]
PAPER_PREFIX: Final = "paper/"


@dataclass(frozen=True)  # noqa: SLOTS_OK -- verifier uses Python 3.9, where dataclass slots are unavailable.
class ValidationError(Exception):
    errors: tuple[str, ...]

    def __str__(self) -> str:
        return "\n".join(self.errors)


def parse_document(text: str, source: Path) -> JsonValue:
    stripped = text.strip()
    if not stripped:
        raise ValidationError((f"{source}: empty document is not valid",))
    if stripped.startswith(("{", "[")):
        decoded = json.loads(stripped)
        return decoded
    lines = [
        (len(line) - len(line.lstrip(" ")), line.strip())
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    value, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise ValidationError((f"{source}: malformed simple YAML near line {index + 1}",))
    return value


def load_data(path: Path) -> JsonValue:
    try:
        return parse_document(path.read_text(encoding="utf-8"), path)
    except json.JSONDecodeError as exc:
        raise ValidationError((f"{path}: malformed JSON: {exc.msg}",)) from exc
    except OSError as exc:
        raise ValidationError((f"{path}: cannot read file: {exc.strerror}",)) from exc


def require_map(value: JsonValue, label: str) -> JsonMap:
    if isinstance(value, dict):
        return value
    raise ValidationError((f"{label}: expected mapping",))


def require_list(value: JsonValue, label: str) -> JsonList:
    if isinstance(value, list):
        return value
    raise ValidationError((f"{label}: expected list",))


def require_str(value: JsonValue, label: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    raise ValidationError((f"{label}: expected non-empty string",))


def string_items(value: JsonValue, label: str) -> list[str]:
    return [require_str(item, f"{label} item") for item in require_list(value, label)]


def infer_paper_root(path: Path) -> Path | None:
    resolved = path.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if parent.name == "paper":
            return parent
    return None


def resolve_paper_path(
    paper_root: Path | None,
    raw_path: str,
    allowed_prefixes: tuple[str, ...] = (PAPER_PREFIX,),
) -> Path | None:
    if not raw_path.startswith(PAPER_PREFIX):
        return None
    if paper_root is None:
        raise ValidationError((f"cannot infer paper root for paper path: {raw_path}",))
    relative_path = Path(raw_path)
    if relative_path.is_absolute():
        raise ValidationError((f"absolute paper path is not allowed: {raw_path}",))
    if ".." in relative_path.parts:
        raise ValidationError((f"path escapes paper root: {raw_path}",))
    project_root = paper_root.parent.resolve()
    canonical_paper_root = paper_root.resolve()
    resolved = (project_root / relative_path).resolve(strict=False)
    if not _is_relative_to(resolved, canonical_paper_root):
        raise ValidationError((f"path escapes paper root: {raw_path}",))
    allowed_roots = tuple((project_root / prefix.rstrip("/")).resolve(strict=False) for prefix in allowed_prefixes)
    if not any(_is_relative_to(resolved, allowed_root) for allowed_root in allowed_roots):
        raise ValidationError((f"path outside allowed paper root: {raw_path}",))
    return resolved


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _parse_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[JsonValue, int]:
    if lines[index][1].startswith("- "):
        items: JsonList = []
        while index < len(lines) and lines[index][0] == indent and lines[index][1].startswith("- "):
            item, index = _parse_list_item(lines, index, indent)
            items.append(item)
        return items, index
    mapping: JsonMap = {}
    while index < len(lines) and lines[index][0] == indent and not lines[index][1].startswith("- "):
        key, value, index = _parse_key_value(lines, index, indent)
        mapping[key] = value
    return mapping, index


def _parse_list_item(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[JsonValue, int]:
    content = lines[index][1][2:].strip()
    if not content:
        return _parse_block(lines, index + 1, lines[index + 1][0])
    if ":" not in content:
        return _parse_scalar(content), index + 1
    key, value = _split_key_value(content)
    item: JsonMap = {key: value}
    index += 1
    while index < len(lines) and lines[index][0] > indent:
        next_key, next_value, index = _parse_key_value(lines, index, lines[index][0])
        item[next_key] = next_value
    return item, index


def _parse_key_value(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[str, JsonValue, int]:
    if lines[index][0] != indent or ":" not in lines[index][1]:
        raise ValidationError((f"malformed simple YAML near line {index + 1}",))
    key, value = _split_key_value(lines[index][1])
    if value is not None:
        return key, value, index + 1
    if index + 1 >= len(lines) or lines[index + 1][0] <= indent:
        return key, [], index + 1
    child, next_index = _parse_block(lines, index + 1, lines[index + 1][0])
    return key, child, next_index


def _split_key_value(content: str) -> tuple[str, JsonValue | None]:
    key, raw_value = content.split(":", 1)
    key = key.strip()
    if not key:
        raise ValidationError(("malformed simple YAML with empty key",))
    raw_value = raw_value.strip()
    return key, None if not raw_value else _parse_scalar(raw_value)


def _parse_scalar(raw_value: str) -> JsonValue:
    if raw_value.startswith("[") and raw_value.endswith("]"):
        inner = raw_value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    lowered = raw_value.lower()
    if lowered in {"null", "none"}:
        return None
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if (raw_value.startswith('"') and raw_value.endswith('"')) or (
        raw_value.startswith("'") and raw_value.endswith("'")
    ):
        return raw_value[1:-1]
    try:
        return int(raw_value)
    except ValueError:
        return raw_value
