"""Runtime install plan executor for initialize-mesa."""
from __future__ import annotations

from .common import *
from .nd_status import append_initialize_event, write_initialize_status

def execute_runtime_plan(plan_path: Path, yes: bool, continue_on_error: bool = False, project_dir: Path = DEFAULT_INITIALIZATION_DIR) -> int:
    resolved_plan = repo_path(plan_path) or plan_path
    if not resolved_plan.is_file():
        print(f"Runtime plan: MISSING {resolved_plan}", file=sys.stderr)
        return 1
    plan = load_json_mapping(resolved_plan)
    if plan.get("schema") != "mesa.runtime-plan.v1":
        print(f"Runtime plan schema: MISSING expected mesa.runtime-plan.v1", file=sys.stderr)
        return 1

    runtime = str(plan.get("runtime", "unknown-runtime"))
    project_out = repo_path(project_dir) or DEFAULT_INITIALIZATION_DIR
    print("\nRuntime plan executor")
    print(f"  runtime: {runtime}")
    print(f"  plan: {resolved_plan}")

    if plan.get("blocked"):
        print("  execution: BLOCKED")
        for blocker in plan.get("blockers", []) or []:
            print(f"    - {blocker}")
        append_initialize_event(
            project_out,
            "runtime-plan-execution-blocked",
            "blocked",
            f"Runtime plan for {runtime} is blocked.",
            {"plan_json": str(resolved_plan), "runtime": runtime},
        )
        write_initialize_status(project_out, headline=f"Runtime plan for `{runtime}` is blocked.")
        return 1 if yes else 0

    if not yes:
        print("  mode: dry run; add --yes to execute")
        for step in plan.get("steps", []) or []:
            if not isinstance(step, dict):
                continue
            if step.get("kind") == "command":
                print(f"  command [{step.get('id')}]: {step.get('command')}")
            else:
                print(f"  notice [{step.get('id')}]: {step.get('message', step.get('title', ''))}")
        append_initialize_event(
            project_out,
            "runtime-plan-dry-run",
            "ok",
            f"Dry-ran runtime plan for {runtime}.",
            {"plan_json": str(resolved_plan), "runtime": runtime},
        )
        write_initialize_status(project_out, headline=f"Runtime plan for `{runtime}` was dry-run only.")
        return 0

    status = 0
    append_initialize_event(
        project_out,
        "runtime-plan-execution-started",
        "running",
        f"Started executing runtime plan for {runtime}.",
        {"plan_json": str(resolved_plan), "runtime": runtime},
    )

    for step in plan.get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("id", "step"))
        if step.get("kind") != "command":
            print(f"  notice [{step_id}]: {step.get('message', step.get('title', ''))}")
            continue
        category = step.get("category")
        if category in {"checkpoint_download", "scheduler_submit"}:
            print(f"  command [{step_id}]: REFUSED unsafe category {category}", file=sys.stderr)
            status = 1
            if not continue_on_error:
                break
            continue
        command = str(step.get("command", "")).strip()
        if not command:
            continue
        cwd = repo_path(step.get("cwd")) or REPO_ROOT
        print(f"  command [{step_id}]: {command}")
        completed = subprocess.run(command, cwd=str(cwd), shell=True, env=mesa_command_env())
        if completed.returncode != 0:
            status = completed.returncode
            append_initialize_event(
                project_out,
                "runtime-plan-step-failed",
                "failed",
                f"Step {step_id} failed for {runtime}.",
                {"plan_json": str(resolved_plan), "runtime": runtime, "step": step_id, "returncode": completed.returncode},
            )
            if not continue_on_error:
                break
        else:
            append_initialize_event(
                project_out,
                "runtime-plan-step-completed",
                "ok",
                f"Step {step_id} completed for {runtime}.",
                {"plan_json": str(resolved_plan), "runtime": runtime, "step": step_id},
            )

    append_initialize_event(
        project_out,
        "runtime-plan-execution-finished",
        "ok" if status == 0 else "failed",
        f"Finished executing runtime plan for {runtime}.",
        {"plan_json": str(resolved_plan), "runtime": runtime, "returncode": status},
    )
    write_initialize_status(
        project_out,
        headline=f"Runtime plan for `{runtime}` {'completed' if status == 0 else 'failed'} with return code `{status}`.",
    )
    return status
