from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
from typing import Any
import urllib.request


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY = REPO_ROOT / "DEPENDENCY" / "runtimes.yaml"
DEFAULT_HANDOFF_CONTRACT = REPO_ROOT / "DEPENDENCY" / "non_deterministic_runtimes.yaml"
PROJECT_ROOT = REPO_ROOT / "project"
PROJECT_PROFILE_FILENAME = "project_profile.md"
INITIALIZATION_DIR_NAME = "initialization"
DEPENDENCY_ENV = REPO_ROOT / "DEPENDENCY" / ".env"
ENV_EXAMPLE = REPO_ROOT / "DEPENDENCY" / ".env.example"
LEGACY_ROOT_ENV = REPO_ROOT / ".env"
LOCAL_BIN = REPO_ROOT / "DEPENDENCY" / "bin"
MAMBA_ROOT_PREFIX = REPO_ROOT / "DEPENDENCY" / ".micromamba"
LOCAL_MICROMAMBA = LOCAL_BIN / ("micromamba.exe" if platform.system() == "Windows" else "micromamba")
LOCAL_MAMBA = LOCAL_BIN / ("mamba.cmd" if platform.system() == "Windows" else "mamba")
EXPECTED_PAPER_SEARCH_CWD = REPO_ROOT / "EXTERNAL" / "paper-search-mcp"
EXPECTED_PAPER_SEARCH_ENV_FILE = "../../DEPENDENCY/.env"
EXPECTED_PAPER_SEARCH_ARGS = ["run", "--frozen", "-m", "paper_search_mcp.server"]
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_-]{12,}"),
    re.compile(r"[A-Z0-9_]*(?:API_KEY|TOKEN|SECRET)\s*=\s*['\"][^'\"]{8,}['\"]"),
]
def load_yaml_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except Exception:
        data = _parse_simple_yaml(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"YAML file did not parse to a mapping: {path}")
    return data
def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    data = load_yaml_mapping(path)
    data.setdefault("recipes", {})
    data.setdefault("runtimes", {})
    data.setdefault("skills", {})
    return data
def load_handoff_contract(path: Path = DEFAULT_HANDOFF_CONTRACT) -> dict[str, Any]:
    data = load_yaml_mapping(path)
    data.setdefault("handoff", {})
    data.setdefault("runtimes", {})
    return data
def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the small YAML subset used by DEPENDENCY/runtimes.yaml.

    Supported shapes: nested mappings, scalar values, and scalar lists. This is
    not a general YAML parser; install PyYAML for full YAML support.
    """

    rows: list[tuple[int, str]] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        content = line.lstrip()
        rows.append((len(line) - len(content), content))

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(rows):
            return {}, index
        if rows[index][0] < indent:
            return {}, index
        if rows[index][1].startswith("- "):
            return parse_list(index, indent)
        return parse_map(index, indent)

    def parse_map(index: int, indent: int) -> tuple[dict[str, Any], int]:
        out: dict[str, Any] = {}
        while index < len(rows):
            row_indent, content = rows[index]
            if row_indent < indent:
                break
            if row_indent > indent:
                raise ValueError(f"Unexpected indentation near: {content}")
            if content.startswith("- "):
                break
            if ":" not in content:
                raise ValueError(f"Expected key/value line: {content}")
            key, value = content.split(":", 1)
            key = key.strip()
            value = value.strip()
            index += 1
            if value:
                out[key] = parse_scalar(value)
            else:
                if index < len(rows) and rows[index][0] > row_indent:
                    out[key], index = parse_block(index, rows[index][0])
                else:
                    out[key] = {}
        return out, index

    def parse_list(index: int, indent: int) -> tuple[list[Any], int]:
        out: list[Any] = []
        while index < len(rows):
            row_indent, content = rows[index]
            if row_indent < indent:
                break
            if row_indent != indent or not content.startswith("- "):
                break
            item = content[2:].strip()
            index += 1
            out.append(parse_scalar(item))
        return out, index

    result, final_index = parse_block(0, rows[0][0] if rows else 0)
    if final_index != len(rows):
        raise ValueError("Could not parse full registry with fallback parser.")
    if not isinstance(result, dict):
        raise ValueError("Registry root must be a mapping.")
    return result
def parse_scalar(value: str) -> Any:
    if value in {"[]", "{}"}:
        return [] if value == "[]" else {}
    if value in {"true", "false"}:
        return value == "true"
    if value in {"null", "None", "~"}:
        return None
    if value and value[0] in {"'", '"'}:
        try:
            return ast.literal_eval(value)
        except Exception:
            return value.strip("'\"")
    try:
        return int(value)
    except ValueError:
        return value
def runtime_for_skill(registry: dict[str, Any], skill: str) -> str | None:
    skills = registry.get("skills", {})
    if not isinstance(skills, dict):
        return None
    return skills.get(skill)
def get_runtime(registry: dict[str, Any], name: str) -> dict[str, Any]:
    runtimes = registry.get("runtimes", {})
    if not isinstance(runtimes, dict) or name not in runtimes:
        known = ", ".join(sorted(runtimes)) if isinstance(runtimes, dict) else ""
        raise SystemExit(f"Unknown runtime: {name}\nKnown runtimes: {known}")
    runtime = runtimes[name]
    if not isinstance(runtime, dict):
        raise SystemExit(f"Runtime entry is not a mapping: {name}")
    return runtime
def get_recipe(registry: dict[str, Any], name: str) -> dict[str, Any]:
    recipes = registry.get("recipes", {})
    if not isinstance(recipes, dict) or name not in recipes:
        known = ", ".join(sorted(recipes)) if isinstance(recipes, dict) else ""
        raise SystemExit(f"Unknown recipe: {name}\nKnown recipes: {known}")
    recipe = recipes[name]
    if not isinstance(recipe, dict):
        raise SystemExit(f"Recipe entry is not a mapping: {name}")
    runtimes = recipe.get("runtimes", [])
    if not isinstance(runtimes, list) or not all(isinstance(item, str) for item in runtimes):
        raise SystemExit(f"Recipe runtimes must be a list of runtime names: {name}")
    return recipe
def resolve_runtime_name(registry: dict[str, Any], runtime: str | None, skill: str | None) -> str:
    if skill:
        found = runtime_for_skill(registry, skill)
        if not found:
            raise SystemExit(f"No runtime mapping found for skill: {skill}")
        return found
    if not runtime:
        raise SystemExit("Provide a runtime name or --skill.")
    return runtime
def repo_path(path_value: Any) -> Path | None:
    if not path_value:
        return None
    p = Path(str(path_value)).expanduser()
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p

def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)

def discover_project_profiles() -> list[Path]:
    if not PROJECT_ROOT.is_dir():
        return []
    return sorted(path for path in PROJECT_ROOT.glob(f"*/{PROJECT_PROFILE_FILENAME}") if path.is_file())

def default_initialization_dir() -> Path:
    profiles = discover_project_profiles()
    if len(profiles) == 1:
        return profiles[0].parent / INITIALIZATION_DIR_NAME
    if not profiles:
        raise SystemExit(
            "No active MESA project profile found. Provide "
            "--output-dir project/<project_name>/initialization or run initialize-mesa "
            "to create project/<project_name>/project_profile.md."
        )
    choices = "\n".join(f"  - {display_path(path.parent / INITIALIZATION_DIR_NAME)}" for path in profiles)
    raise SystemExit("Multiple MESA project profiles found. Provide an explicit initialization directory:\n" + choices)

def initialization_dir(path_value: Path | str | None) -> Path:
    resolved = repo_path(path_value)
    if resolved is not None:
        return resolved
    return default_initialization_dir()
def command_tool(command: str) -> str | None:
    try:
        parts = shlex.split(command)
    except ValueError:
        return None
    return parts[0] if parts else None
def find_tool(tool: str) -> str | None:
    found = shutil.which(tool)
    if found:
        return found
    for candidate in local_tool_candidates(tool):
        if candidate.is_file():
            return str(candidate)
    if tool == "python":
        return shutil.which("python3")
    return None
def local_tool_candidates(tool: str) -> list[Path]:
    names = [tool]
    if platform.system() == "Windows" and "." not in Path(tool).name:
        names.extend([f"{tool}.exe", f"{tool}.cmd", f"{tool}.bat"])
    return [LOCAL_BIN / name for name in names]
def mesa_command_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(merged_env_values())
    if LOCAL_BIN.is_dir():
        current_path = env.get("PATH", "")
        env["PATH"] = str(LOCAL_BIN) + (os.pathsep + current_path if current_path else "")
    if LOCAL_MICROMAMBA.is_file():
        env.setdefault("MAMBA_ROOT_PREFIX", str(MAMBA_ROOT_PREFIX))
    return env
def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip("'\"")
        values[key] = value
    return values
def merged_env_values() -> dict[str, str]:
    merged: dict[str, str] = {}
    for env_file in (LEGACY_ROOT_ENV, DEPENDENCY_ENV):
        for key, value in read_env_file(env_file).items():
            if value:
                merged[key] = value
    for key, value in os.environ.items():
        if value:
            merged[key] = value
    return merged
def string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value in (None, ""):
        return []
    return [str(value)]
def trim_probe_text(value: str, max_lines: int = 20, max_chars: int = 4000) -> str:
    lines = value.strip().splitlines()
    text = "\n".join(lines[:max_lines])
    if len(lines) > max_lines:
        text += f"\n... truncated after {max_lines} lines"
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... truncated"
    return text
def run_probe(command: list[str], timeout: int = 20) -> dict[str, Any]:
    if not command:
        return {"command": [], "available": False, "error": "empty command"}

    tool = command[0]
    found = find_tool(tool)
    display = " ".join(shlex.quote(part) for part in command)
    probe: dict[str, Any] = {
        "command": display,
        "available": bool(found),
    }
    if not found:
        return probe

    run_args = [found, *command[1:]]
    probe["path"] = found
    try:
        completed = subprocess.run(
            run_args,
            cwd=str(REPO_ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            env=mesa_command_env(),
        )
    except subprocess.TimeoutExpired as exc:
        probe["timeout"] = timeout
        probe["returncode"] = None
        probe["stdout"] = trim_probe_text(exc.stdout or "") if isinstance(exc.stdout, str) else ""
        probe["stderr"] = trim_probe_text(exc.stderr or "") if isinstance(exc.stderr, str) else ""
        return probe
    except Exception as exc:
        probe["error"] = str(exc)
        return probe

    probe["returncode"] = completed.returncode
    probe["stdout"] = trim_probe_text(completed.stdout)
    probe["stderr"] = trim_probe_text(completed.stderr)
    return probe
def load_json_mapping(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Could not parse JSON file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"JSON file did not parse to a mapping: {path}")
    return data
