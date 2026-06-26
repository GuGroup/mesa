#!/usr/bin/env python3
"""Bootstrap and preflight helper for MESA runtime environments.

The script is intentionally stdlib-only so a fresh clone can run it before any
project environment exists. It reads DEPENDENCY/runtimes.yaml. If PyYAML is
available it uses that; otherwise it falls back to a small YAML subset parser
that supports this registry file.
"""

from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = REPO_ROOT / "DEPENDENCY" / "runtimes.yaml"


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except Exception:
        data = _parse_simple_yaml(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"Registry did not parse to a mapping: {path}")
    data.setdefault("runtimes", {})
    data.setdefault("skills", {})
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
    if tool == "python":
        return shutil.which("python3")
    return None


def check_runtime(name: str, runtime: dict[str, Any]) -> int:
    print(f"{name}: {runtime.get('description', '')}")
    status = 0

    for field in ("cwd", "spec", "lock"):
        value = runtime.get(field)
        if not value:
            continue
        path = repo_path(value)
        exists = bool(path and path.exists())
        print(f"  {field}: {path} {'OK' if exists else 'MISSING'}")
        if not exists:
            status = 1

    for tool in runtime.get("check_tools", []) or []:
        found = find_tool(str(tool))
        detail = ""
        if found and Path(found).name != str(tool):
            detail = f" via {Path(found).name}"
        print(f"  tool {tool}: {'OK' if found else 'MISSING'}{detail}")
        if not found:
            status = 1

    for key in runtime.get("env_required", []) or []:
        present = bool(os.environ.get(str(key)))
        print(f"  env {key}: {'SET' if present else 'MISSING'}")
        if not present:
            status = 1

    optional = runtime.get("env_optional", []) or []
    if optional:
        set_count = sum(1 for key in optional if os.environ.get(str(key)))
        print(f"  optional env: {set_count}/{len(optional)} set")

    install = runtime.get("install", []) or []
    if runtime.get("kind") == "external-manual":
        print("  install: manual runtime; see spec file")
    elif install:
        print("  install command:")
        for command in install:
            print(f"    {command}")

    return status


def run_commands(runtime: dict[str, Any], command_key: str, execute: bool) -> int:
    commands = runtime.get(command_key, []) or []
    if not commands:
        print(f"No {command_key} commands configured.")
        return 0

    cwd = repo_path(runtime.get("cwd")) or REPO_ROOT
    if not cwd.exists():
        print(f"Working directory does not exist: {cwd}", file=sys.stderr)
        return 1

    status = 0
    for command in commands:
        command = str(command)
        print(f"[{cwd}] {command}")
        if not execute:
            continue
        tool = command_tool(command)
        if tool and find_tool(tool) is None and command != "No runtime install required.":
            print(f"Missing command: {tool}", file=sys.stderr)
            status = 1
            continue
        completed = subprocess.run(command, cwd=str(cwd), shell=True)
        if completed.returncode != 0:
            status = completed.returncode
            break
    if not execute:
        print("Dry run only. Re-run with --yes to execute.")
    return status


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


def merged_env_from_root() -> dict[str, str]:
    merged = read_env_file(REPO_ROOT / ".env")
    for key, value in os.environ.items():
        if value:
            merged[key] = value
    return merged


def env_status(label: str, present: bool, required: bool = False) -> int:
    state = "SET" if present else "MISSING"
    suffix = " REQUIRED" if required and not present else ""
    print(f"  {label}: {state}{suffix}")
    return 1 if required and not present else 0


def load_toml(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        import tomllib
    except Exception:
        return None, "tomllib unavailable; use Python 3.11+ for TOML validation"
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception as exc:
        return None, str(exc)
    return data, None


def check_project_codex_config() -> int:
    print("\nCodex project config")
    status = 0
    config_path = REPO_ROOT / ".codex" / "config.toml"
    if not config_path.is_file():
        print(f"  .codex/config.toml: MISSING")
        return 1
    print(f"  .codex/config.toml: OK")

    data, error = load_toml(config_path)
    if error or data is None:
        print(f"  TOML parse: MISSING {error}")
        return 1
    print("  TOML parse: OK")

    servers = data.get("mcp_servers", {})
    paper = servers.get("paper_search") if isinstance(servers, dict) else None
    if not isinstance(paper, dict):
        print("  mcp_servers.paper_search: MISSING")
        return 1
    print("  mcp_servers.paper_search: OK")

    command = paper.get("command")
    args = paper.get("args")
    cwd_value = paper.get("cwd")
    print(f"  command: {'OK' if command else 'MISSING'}")
    if not isinstance(args, list) or "paper_search_mcp.server" not in " ".join(str(x) for x in args):
        print("  args: MISSING expected paper_search_mcp.server launch")
        status = 1
    else:
        print("  args: OK")

    cwd_path = (config_path.parent / str(cwd_value)).resolve() if cwd_value else None
    if cwd_path and cwd_path.is_dir():
        print(f"  cwd: OK {cwd_path}")
    else:
        print(f"  cwd: MISSING {cwd_path or '<unset>'}")
        status = 1

    env_table = paper.get("env", {})
    env_file = env_table.get("PAPER_SEARCH_MCP_ENV_FILE") if isinstance(env_table, dict) else None
    if env_file:
        env_path = (cwd_path / str(env_file)).resolve() if cwd_path else Path(str(env_file))
        print(f"  PAPER_SEARCH_MCP_ENV_FILE: OK {env_path}")
    else:
        print("  PAPER_SEARCH_MCP_ENV_FILE: MISSING")
        status = 1

    text = config_path.read_text(encoding="utf-8")
    if "sk-" in text:
        print("  secret scan: MISSING possible literal API key in config")
        status = 1
    else:
        print("  secret scan: OK no obvious literal API key")
    return status


def check_secret_readiness() -> int:
    print("\nSecrets and API keys")
    status = 0
    env_example = REPO_ROOT / "DEPENDENCY" / ".env.example"
    root_env = REPO_ROOT / ".env"
    print(f"  DEPENDENCY/.env.example: {'OK' if env_example.is_file() else 'MISSING'}")
    if not env_example.is_file():
        status = 1
    print(f"  repo .env: {'OK' if root_env.is_file() else 'MISSING'}")

    values = merged_env_from_root()
    status = max(status, env_status("OPENAI_API_KEY", bool(values.get("OPENAI_API_KEY")), required=True))
    mp_present = bool(values.get("MP_API_KEY") or values.get("PMG_MAPI_KEY"))
    status = max(status, env_status("MP_API_KEY or PMG_MAPI_KEY", mp_present, required=True))

    optional = [
        "OPENAI_MODEL",
        "OPENAI_EMBEDDING_KEY",
        "PAPER_SEARCH_MCP_UNPAYWALL_EMAIL",
        "PAPER_SEARCH_MCP_CORE_API_KEY",
        "PAPER_SEARCH_MCP_SEMANTIC_SCHOLAR_API_KEY",
    ]
    set_count = sum(1 for key in optional if values.get(key))
    print(f"  useful optional keys: {set_count}/{len(optional)} set")
    return status


def check_bootstrap_tools() -> int:
    print("\nBootstrap tools")
    status = 0
    required = ["python", "uv"]
    optional = ["mamba", "qsub"]
    for tool in required:
        found = find_tool(tool)
        detail = f" ({Path(found).name})" if found else ""
        print(f"  {tool}: {'OK' if found else 'MISSING'}{detail}")
        if not found:
            status = 1
    for tool in optional:
        found = find_tool(tool)
        detail = f" ({Path(found).name})" if found else ""
        print(f"  {tool}: {'OK' if found else 'MISSING'}{detail} optional until needed")
    return status


def cmd_bootstrap(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    runtimes = registry.get("runtimes", {})
    skills = registry.get("skills", {})
    status = 0

    print("MESA bootstrap preflight")
    print(f"repo: {REPO_ROOT}")
    print(f"registry: {args.registry}")
    print(f"  runtimes: {len(runtimes) if isinstance(runtimes, dict) else 'invalid'}")
    print(f"  skill mappings: {len(skills) if isinstance(skills, dict) else 'invalid'}")
    if not isinstance(runtimes, dict) or not isinstance(skills, dict):
        status = 1

    status = max(status, check_project_codex_config())
    status = max(status, check_secret_readiness())
    status = max(status, check_bootstrap_tools())

    print("\nRuntime next checks")
    print("  python3 DEPENDENCY/tools/mesa_env.py list --skills")
    print("  python3 DEPENDENCY/tools/mesa_env.py doctor --all")
    print("  python3 DEPENDENCY/tools/mesa_env.py doctor --skill <SKILL_NAME>")

    if status == 0:
        print("\nBootstrap status: OK")
    else:
        print("\nBootstrap status: ACTION REQUIRED")
    return status


def cmd_list(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    runtimes = registry.get("runtimes", {})
    if not isinstance(runtimes, dict):
        raise SystemExit("Registry runtimes field is invalid.")
    for name in sorted(runtimes):
        runtime = runtimes[name]
        kind = runtime.get("kind", "") if isinstance(runtime, dict) else ""
        desc = runtime.get("description", "") if isinstance(runtime, dict) else ""
        print(f"{name:22} {kind:16} {desc}")
    if args.skills:
        print("\nskill mappings:")
        skills = registry.get("skills", {})
        if isinstance(skills, dict):
            for skill in sorted(skills):
                print(f"{skill:45} {skills[skill]}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    runtimes = registry.get("runtimes", {})
    if args.all:
        status = 0
        for name in sorted(runtimes):
            runtime = get_runtime(registry, name)
            status = max(status, check_runtime(name, runtime))
        return status
    name = resolve_runtime_name(registry, args.runtime, args.skill)
    return check_runtime(name, get_runtime(registry, name))


def cmd_install(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    name = resolve_runtime_name(registry, args.runtime, args.skill)
    runtime = get_runtime(registry, name)
    key = "update" if args.update else "install"
    print(f"{key}: {name}")
    return run_commands(runtime, key, args.yes)


def cmd_smoke(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    name = resolve_runtime_name(registry, args.runtime, args.skill)
    runtime = get_runtime(registry, name)
    print(f"smoke: {name}")
    return run_commands(runtime, "smoke", args.yes)


def cmd_doctor(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    if args.all:
        return cmd_check(args)
    name = resolve_runtime_name(registry, args.runtime, args.skill)
    runtime = get_runtime(registry, name)
    status = check_runtime(name, runtime)
    print("\nsmoke commands:")
    run_commands(runtime, "smoke", execute=False)
    return status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="Path to runtimes.yaml.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_bootstrap = sub.add_parser("bootstrap", help="Run repo bootstrap preflight checks.")
    p_bootstrap.set_defaults(func=cmd_bootstrap)

    p_list = sub.add_parser("list", help="List configured runtimes.")
    p_list.add_argument("--skills", action="store_true", help="Also print skill-to-runtime mappings.")
    p_list.set_defaults(func=cmd_list)

    p_check = sub.add_parser("check", help="Check paths, tools, and env vars for a runtime.")
    p_check.add_argument("runtime", nargs="?", help="Runtime name.")
    p_check.add_argument("--skill", help="Resolve runtime from skill folder/name.")
    p_check.add_argument("--all", action="store_true", help="Check every runtime.")
    p_check.set_defaults(func=cmd_check)

    p_install = sub.add_parser("install", help="Print or execute install commands.")
    p_install.add_argument("runtime", nargs="?", help="Runtime name.")
    p_install.add_argument("--skill", help="Resolve runtime from skill folder/name.")
    p_install.add_argument("--update", action="store_true", help="Use update commands instead of install commands.")
    p_install.add_argument("--yes", action="store_true", help="Actually execute commands.")
    p_install.set_defaults(func=cmd_install)

    p_smoke = sub.add_parser("smoke", help="Print or execute smoke-test commands.")
    p_smoke.add_argument("runtime", nargs="?", help="Runtime name.")
    p_smoke.add_argument("--skill", help="Resolve runtime from skill folder/name.")
    p_smoke.add_argument("--yes", action="store_true", help="Actually execute commands.")
    p_smoke.set_defaults(func=cmd_smoke)

    p_doctor = sub.add_parser("doctor", help="Check a runtime and print smoke commands.")
    p_doctor.add_argument("runtime", nargs="?", help="Runtime name.")
    p_doctor.add_argument("--skill", help="Resolve runtime from skill folder/name.")
    p_doctor.add_argument("--all", action="store_true", help="Check every runtime.")
    p_doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
