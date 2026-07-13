"""Runtime registry checks, recipe execution, and command runners."""
from __future__ import annotations

from .common import *

def check_runtime(name: str, runtime: dict[str, Any]) -> int:
    print(f"{name}: {runtime.get('description', '')}")
    status = 0
    env_values = merged_env_values()

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
        present = bool(env_values.get(str(key)))
        print(f"  env {key}: {'SET' if present else 'MISSING'}")
        if not present:
            status = 1

    optional = runtime.get("env_optional", []) or []
    if optional:
        set_count = sum(1 for key in optional if env_values.get(str(key)))
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
        completed = subprocess.run(command, cwd=str(cwd), shell=True, env=mesa_command_env())
        if completed.returncode != 0:
            status = completed.returncode
            break
    if not execute:
        print("Dry run only. Re-run with --yes to execute.")
    return status

def run_recipe(
    registry: dict[str, Any],
    recipe_name: str,
    execute: bool,
    continue_on_error: bool = False,
) -> int:
    recipe = get_recipe(registry, recipe_name)
    runtime_names = list(recipe.get("runtimes", []) or [])
    description = recipe.get("description", "")

    print(f"\nDependency recipe: {recipe_name}")
    if description:
        print(f"  {description}")
    print(f"  runtimes: {', '.join(runtime_names)}")
    if not execute:
        print("  mode: dry run; add --yes to execute installs and smoke tests")
    else:
        print("  mode: execute")

    status = 0
    for index, runtime_name in enumerate(runtime_names, start=1):
        runtime = get_runtime(registry, runtime_name)
        print(f"\nRecipe step {index}/{len(runtime_names)}: {runtime_name}")
        check_status = check_runtime(runtime_name, runtime)
        if check_status != 0:
            print(f"  readiness: ACTION REQUIRED before install may succeed")

        if not execute:
            print("  install plan:")
            status = max(status, run_commands(runtime, "install", execute=False))
            print("  smoke plan:")
            status = max(status, run_commands(runtime, "smoke", execute=False))
            continue

        print("  pre-install smoke:")
        pre_smoke = run_commands(runtime, "smoke", execute=True)
        if pre_smoke == 0:
            print(f"  result: SKIPPED already healthy")
            continue

        print("  install:")
        install_status = run_commands(runtime, "install", execute=True)
        if install_status != 0:
            print(f"  result: FAILED install exited {install_status}")
            status = install_status
            if not continue_on_error:
                break
            continue

        print("  post-install smoke:")
        smoke_status = run_commands(runtime, "smoke", execute=True)
        if smoke_status != 0:
            print(f"  result: FAILED smoke exited {smoke_status}")
            status = smoke_status
            if not continue_on_error:
                break
            continue

        print("  result: INSTALLED smoke OK")

    if status == 0:
        print(f"\nDependency recipe {recipe_name}: OK")
    else:
        print(f"\nDependency recipe {recipe_name}: ACTION REQUIRED")
    return status
