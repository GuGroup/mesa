from __future__ import annotations

import re
from pathlib import Path


SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


def require_safe_segment(value: str, field: str) -> str:
    if not value or not SAFE_SEGMENT.match(value):
        raise ValueError(f"{field} must contain only letters, numbers, '.', '_', '-'")
    if value in {".", ".."}:
        raise ValueError(f"{field} must not be '.' or '..'")
    return value


def safe_relative_path(value: str, field: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        raise ValueError(f"{field} must be relative")
    parts = path.parts
    if not parts:
        raise ValueError(f"{field} must not be empty")
    for part in parts:
        require_safe_segment(part, field)
    return Path(*parts)


def resolve_under(root: Path, relative: Path) -> Path:
    root_resolved = root.expanduser().resolve()
    target = (root_resolved / relative).resolve()
    if root_resolved not in [target, *target.parents]:
        raise ValueError("target path escaped root")
    return target


def require_under_trusted_roots(path: Path, trusted_roots: list[Path]) -> Path:
    resolved = path.expanduser().resolve()
    for root in trusted_roots:
        root_resolved = root.expanduser().resolve()
        if root_resolved in [resolved, *resolved.parents]:
            return resolved
    roots = ", ".join(str(root) for root in trusted_roots)
    raise ValueError(f"{resolved} is not under a trusted root: {roots}")
