from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def load_yaml(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PyYAML is required: pip install pyyaml") from exc
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def dump_yaml(data: dict[str, Any]) -> str:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PyYAML is required: pip install pyyaml") from exc
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=False)


def default_config_path(kind: str) -> Path:
    base = os.environ.get("VASP_SUBMIT_CONFIG_DIR")
    if base:
        return Path(base).expanduser() / f"{kind}.yml"
    return Path.home() / ".config" / "vasp-submit" / f"{kind}.yml"
