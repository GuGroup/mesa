"""Small shared utility functions."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .errors import MesaValidationError


def safe_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def is_number(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return False
        try:
            return math.isfinite(float(stripped))
        except ValueError:
            return False
    return False


def to_float(value: Any, label: str) -> float:
    if not is_number(value):
        raise MesaValidationError(f"Non-numeric energy value for {label}: {value!r}")
    return float(value)


def resolve_path(path_value: str, context: dict[str, Any] | None) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    if context and context.get("workdir"):
        return Path(str(context["workdir"])) / path
    return path
