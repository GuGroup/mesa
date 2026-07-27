"""Argument parser and command dispatch for mesa_env."""
from __future__ import annotations

from .bootstrap import *
from .common import *
from .nondeterministic import *
from .runtime import *

def cmd_bootstrap(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    recipes = registry.get("recipes", {})
    runtimes = registry.get("runtimes", {})
    skills = registry.get("skills", {})
    status = 0

    print("MESA bootstrap preflight")
    print(f"repo: {REPO_ROOT}")
    print(f"registry: {args.registry}")
    print(f"  recipes: {len(recipes) if isinstance(recipes, dict) else 'invalid'}")
    print(f"  runtimes: {len(runtimes) if isinstance(runtimes, dict) else 'invalid'}")
    print(f"  skill mappings: {len(skills) if isinstance(skills, dict) else 'invalid'}")
    if not isinstance(recipes, dict) or not isinstance(runtimes, dict) or not isinstance(skills, dict):
        status = 1

    status = max(status, check_platform())
    status = max(status, check_bootstrap_tools())
    status = max(status, check_secret_readiness())
    status = max(status, check_project_codex_config())
    status = max(status, check_conda_manager(args.install_mamba))

    if args.install_core:
        if args.yes and find_tool("mamba") is None:
            print("\nCore dependency recipe: ACTION REQUIRED")
            print("  mamba command is required for mesa-modeling and mesa-manuscript.")
            print("  Rerun with --install-mamba or install mamba/micromamba first.")
            status = 1
        elif status != 0 and args.yes:
            print("\nCore dependency recipe: SKIPPED")
            print("  Resolve bootstrap ACTION REQUIRED items before executing installs.")
        else:
            status = max(
                status,
                run_recipe(
                    registry,
                    "core",
                    execute=args.yes,
                    continue_on_error=args.continue_on_error,
                ),
            )
    else:
        print("\nCore dependency recipe")
        print("  not requested")
        print_core_install_help()

    print("\nProject-scoped initialization artifacts")
    print("  not handled by bootstrap")
    print("  run initialize-project before analyzer, handoff, status, or runtime-plan artifacts")

    print("\nRuntime next checks")
    print("  uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py list --skills")
    print("  uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py doctor --all")
    print("  uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py doctor --skill <SKILL_NAME>")

    if status == 0:
        print("\nBootstrap status: OK")
    else:
        print("\nBootstrap status: ACTION REQUIRED")
    return status

def cmd_list(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    recipes = registry.get("recipes", {})
    if args.recipes:
        print("recipes:")
        if isinstance(recipes, dict):
            for name in sorted(recipes):
                recipe = recipes[name]
                desc = recipe.get("description", "") if isinstance(recipe, dict) else ""
                runtimes = recipe.get("runtimes", []) if isinstance(recipe, dict) else []
                runtime_text = ", ".join(str(item) for item in runtimes) if isinstance(runtimes, list) else ""
                print(f"{name:22} {desc}")
                if runtime_text:
                    print(f"{'':22} {runtime_text}")
        if not args.skills:
            return 0
        print()

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

def cmd_handoff(args: argparse.Namespace) -> int:
    return write_dependency_handoff(args.output_dir, args.contracts)

def cmd_analyze_nondeterministic(args: argparse.Namespace) -> int:
    return write_nondeterministic_analysis(args.output_dir, args.contracts)

def cmd_notify(args: argparse.Namespace) -> int:
    contracts = load_handoff_contract(repo_path(args.contracts) or args.contracts)
    append_initialize_event(
        args.output_dir,
        "notification",
        "ok",
        args.message,
        contracts=contracts,
    )
    status_path = write_initialize_status(args.output_dir, contracts, args.message)
    print("\nInitialize notification")
    print(f"  status: OK {status_path}")
    print(f"  message: {args.message}")
    return 0

def cmd_generate_runtime_plan(args: argparse.Namespace) -> int:
    return write_runtime_plan(
        args.runtime,
        args.output_dir,
        args.project_dir,
        args.profile,
        args.contracts,
        auto_analyze=not args.no_auto_analyze,
    )

def cmd_execute_runtime_plan(args: argparse.Namespace) -> int:
    return execute_runtime_plan(
        args.plan,
        yes=args.yes,
        continue_on_error=args.continue_on_error,
        project_dir=args.project_dir,
    )

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
    p_bootstrap.add_argument(
        "--install-mamba",
        action="store_true",
        help="Install repo-local micromamba plus a mamba wrapper under DEPENDENCY/bin if needed.",
    )
    p_bootstrap.add_argument(
        "--install-core",
        action="store_true",
        help="Run the core dependency recipe. Dry-run by default; add --yes to execute.",
    )
    p_bootstrap.add_argument(
        "--continue-on-error",
        action="store_true",
        help="When executing --install-core, continue to later runtimes after a failure.",
    )
    p_bootstrap.add_argument("--yes", action="store_true", help="Actually execute --install-core commands.")
    p_bootstrap.set_defaults(func=cmd_bootstrap)

    p_list = sub.add_parser("list", help="List configured runtimes.")
    p_list.add_argument("--skills", action="store_true", help="Also print skill-to-runtime mappings.")
    p_list.add_argument("--recipes", action="store_true", help="Also print dependency recipes.")
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

    p_handoff = sub.add_parser("handoff", help="Write non-deterministic runtime handoff files.")
    p_handoff.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory for machine_profile.json and dependency_handoff.md. Defaults to the "
            "unique active project profile's initialization directory."
        ),
    )
    p_handoff.add_argument(
        "--contracts",
        type=Path,
        default=DEFAULT_HANDOFF_CONTRACT,
        help="Contract YAML describing machine-specific runtimes.",
    )
    p_handoff.set_defaults(func=cmd_handoff)

    p_nd = sub.add_parser(
        "analyze-nondeterministic",
        aliases=["nd-analyze"],
        help="Write structured non-deterministic analyzer profile files.",
    )
    p_nd.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory for nondeterministic_profile.json and nondeterministic_profile.md. "
            "Defaults to the unique active project profile's initialization directory."
        ),
    )
    p_nd.add_argument(
        "--contracts",
        type=Path,
        default=DEFAULT_HANDOFF_CONTRACT,
        help="Contract YAML describing machine-specific runtimes.",
    )
    p_nd.set_defaults(func=cmd_analyze_nondeterministic)

    p_notify = sub.add_parser(
        "notify",
        aliases=["status"],
        help="Write or refresh the user-facing initialization status artifacts.",
    )
    p_notify.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Initialization artifact directory for initialize_status.md and "
            "initialize_events.jsonl. Defaults to the unique active project profile's "
            "initialization directory."
        ),
    )
    p_notify.add_argument(
        "--contracts",
        type=Path,
        default=DEFAULT_HANDOFF_CONTRACT,
        help="Contract YAML for status artifact names.",
    )
    p_notify.add_argument(
        "--message",
        default="Initialization status refreshed.",
        help="Plain-language status message to record.",
    )
    p_notify.set_defaults(func=cmd_notify)

    p_plan = sub.add_parser(
        "generate-runtime-plan",
        aliases=["plan-runtime"],
        help="Generate a saved install plan for a non-deterministic runtime.",
    )
    p_plan.add_argument("runtime", help="Runtime name, for example mesa-uma or mesa-adsorbdiff.")
    p_plan.add_argument(
        "--profile",
        type=Path,
        default=None,
        help=(
            "Path to nondeterministic_profile.json. Defaults to the selected initialization "
            "directory's analyzer output."
        ),
    )
    p_plan.add_argument(
        "--contracts",
        type=Path,
        default=DEFAULT_HANDOFF_CONTRACT,
        help="Contract YAML describing machine-specific runtimes.",
    )
    p_plan.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory for <runtime>_plan.json and <runtime>_plan.md. Defaults to "
            "<initialization>/runtime_plans."
        ),
    )
    p_plan.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        help=(
            "Initialization artifact directory for status/event artifacts. Defaults to the "
            "unique active project profile's initialization directory."
        ),
    )
    p_plan.add_argument(
        "--no-auto-analyze",
        action="store_true",
        help="Fail if the non-deterministic profile is missing instead of generating it.",
    )
    p_plan.set_defaults(func=cmd_generate_runtime_plan)

    p_execute = sub.add_parser(
        "execute-runtime-plan",
        aliases=["run-runtime-plan"],
        help="Dry-run or execute a saved non-deterministic runtime plan.",
    )
    p_execute.add_argument("plan", type=Path, help="Path to a <runtime>_plan.json file.")
    p_execute.add_argument("--yes", action="store_true", help="Actually execute the saved plan.")
    p_execute.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue to later plan steps after a failed command.",
    )
    p_execute.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        help=(
            "Initialization artifact directory for status/event artifacts. Defaults to the "
            "unique active project profile's initialization directory."
        ),
    )
    p_execute.set_defaults(func=cmd_execute_runtime_plan)

    return parser

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
