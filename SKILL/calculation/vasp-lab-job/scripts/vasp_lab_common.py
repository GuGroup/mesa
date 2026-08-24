#!/usr/bin/env python3
"""Shared helpers for the vasp-lab-job skill."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - handled at runtime on HPC
    yaml = None


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULTS_YAML = SKILL_DIR / "references" / "defaults.yaml"
ASSETS_DIR = SKILL_DIR / "assets"


class SkillError(RuntimeError):
    """Error raised for user-fixable skill input problems."""


def require_yaml() -> Any:
    if yaml is None:
        raise SkillError("PyYAML is required: install pyyaml or run in the modeling environment.")
    return yaml


def load_yaml(path: str | Path) -> dict[str, Any]:
    y = require_yaml()
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise SkillError(f"YAML file not found: {p}")
    data = y.safe_load(p.read_text()) or {}
    if not isinstance(data, dict):
        raise SkillError(f"YAML root must be a mapping: {p}")
    return data


def write_yaml(path: str | Path, data: dict[str, Any]) -> None:
    y = require_yaml()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(y.safe_dump(data, sort_keys=False, allow_unicode=True))


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)  # type: ignore[arg-type]
        else:
            result[key] = value
    return result


def parse_scalar(value: str) -> Any:
    """Parse command-line override scalar into bool/int/float/list/string."""
    text = value.strip()
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    if text.lower() in {"none", "null"}:
        return None
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(x.strip()) for x in inner.split(",")]
    try:
        if re.fullmatch(r"[-+]?\d+", text):
            return int(text)
        return float(text)
    except ValueError:
        return text


def parse_overrides(items: Iterable[str] | None) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for item in items or []:
        if "=" not in item:
            raise SkillError(f"Override must be key=value, got: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise SkillError(f"Override has empty key: {item}")
        overrides[key] = parse_scalar(value)
    return overrides


def parse_int_list(text: str | None, expected_len: int | None = None) -> list[int] | None:
    if text is None:
        return None
    cleaned = text.strip().replace("[", "").replace("]", "")
    parts = [p for p in re.split(r"[,.xX\s]+", cleaned) if p]
    values = [int(p) for p in parts]
    if expected_len is not None and len(values) != expected_len:
        raise SkillError(f"Expected {expected_len} integers, got {values}")
    return values


def parse_indices(text: str | None, natoms: int) -> list[int] | None:
    """Parse 1-based indices/ranges like '1-3,8,10-12' into 0-based indices."""
    if not text:
        return None
    result: set[int] = set()
    for chunk in text.replace(" ", "").split(","):
        if not chunk:
            continue
        if "-" in chunk:
            start_s, end_s = chunk.split("-", 1)
            start, end = int(start_s), int(end_s)
            if start > end:
                start, end = end, start
            result.update(range(start - 1, end))
        else:
            result.add(int(chunk) - 1)
    bad = [i + 1 for i in result if i < 0 or i >= natoms]
    if bad:
        raise SkillError(f"Atom indices out of range: {bad}; natoms={natoms}")
    return sorted(result)


def load_defaults(path: str | Path | None = None) -> dict[str, Any]:
    return load_yaml(path or DEFAULTS_YAML)


def profile_for_calc_type(defaults: dict[str, Any], calc_type: str) -> str:
    profile = defaults.get("profile_map", {}).get(calc_type)
    if not profile:
        raise SkillError(f"No default profile_map entry for calc_type={calc_type!r}")
    return str(profile)


def get_profile(defaults: dict[str, Any], profile_name: str, *, allow_unverified: bool = False) -> dict[str, Any]:
    profiles = defaults.get("profiles", {})
    if profile_name not in profiles:
        raise SkillError(f"Profile not found: {profile_name}. Available: {', '.join(sorted(profiles))}")
    profile = profiles[profile_name]
    source = profile.get("source", {}) if isinstance(profile, dict) else {}
    status = str(source.get("status", ""))
    if "needs_literature_verification" in status and not allow_unverified:
        raise SkillError(
            f"Profile {profile_name!r} is marked {status!r}. "
            "Use a literature profile with citation/DOI or pass --allow-unverified-profile."
        )
    return profile


def get_vasp_params(
    defaults: dict[str, Any],
    calc_type: str,
    profile_name: str | None = None,
    overrides: dict[str, Any] | None = None,
    *,
    allow_unverified: bool = False,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    name = profile_name or profile_for_calc_type(defaults, calc_type)
    profile = get_profile(defaults, name, allow_unverified=allow_unverified)
    params = dict(profile.get("vasp", {}) or {})
    params = deep_merge(params, overrides or {})
    # Remove None values, useful for template literature profiles.
    params = {k: v for k, v in params.items() if v is not None}
    return name, profile, params


def ensure_vasp_pp_path(defaults: dict[str, Any]) -> None:
    vasp_pp_path = defaults.get("pseudo", {}).get("vasp_pp_path")
    if vasp_pp_path:
        os.environ["VASP_PP_PATH"] = str(vasp_pp_path)


def setups_from_defaults(defaults: dict[str, Any]) -> dict[str, Any]:
    return dict(defaults.get("pseudo", {}).get("setups", {"base": "recommended"}))


def choose_submit_script(defaults: dict[str, Any], calc_type: str, kpts: list[int] | tuple[int, int, int], cores: int) -> str:
    if cores not in (48, 64):
        raise SkillError("cores must be 48 or 64")
    submit = defaults.get("submit", {})
    is_gamma_kpoint = list(kpts) == [1, 1, 1]
    if calc_type == "gas":
        return str(submit.get("standard", {}).get(cores) or f"submit_vasp_{cores}.sh")
    if is_gamma_kpoint:
        return str(submit.get("gamma", {}).get(cores) or f"submit_vasp_gam_{cores}.sh")
    return str(submit.get("standard", {}).get(cores) or f"submit_vasp_{cores}.sh")


def copy_submit_script(script_name: str, calc_dir: Path) -> Path:
    src = ASSETS_DIR / script_name
    if not src.is_file():
        raise SkillError(f"Submit template not found: {src}")
    dst = calc_dir / script_name
    shutil.copy2(src, dst)
    dst.chmod(dst.stat().st_mode | 0o111)
    return dst


def submit_with_qsub(script_name: str, calc_dir: Path, *, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        return {"submitted": False, "dry_run": True, "scheduler_id": None}
    try:
        proc = subprocess.run(
            ["qsub", script_name],
            cwd=str(calc_dir),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except FileNotFoundError as exc:
        raise SkillError("qsub not found. Run this on the SGE login node or omit --submit.") from exc
    except subprocess.CalledProcessError as exc:
        raise SkillError(f"qsub failed in {calc_dir}: stdout={exc.stdout!r} stderr={exc.stderr!r}") from exc
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    match = re.search(r"\b(\d+)\b", text)
    return {"submitted": True, "dry_run": False, "scheduler_id": match.group(1) if match else None, "qsub_output": text.strip()}


def write_manifest(calc_dir: Path, manifest: dict[str, Any]) -> None:
    write_yaml(calc_dir / "vasp_lab_manifest.yml", manifest)
    (calc_dir / "vasp_lab_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
