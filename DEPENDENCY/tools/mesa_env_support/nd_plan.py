"""Runtime install plan generation for non-deterministic MESA runtimes."""
from __future__ import annotations

from .common import *
from .nd_reporting import write_nondeterministic_analysis
from .nd_status import append_initialize_event, contract_output_names, safe_filename, utc_timestamp, write_initialize_status

def ensure_nondeterministic_profile(
    profile_path: Path,
    output_dir: Path | None,
    contracts_path: Path,
    auto_analyze: bool = True,
) -> dict[str, Any]:
    resolved_profile = repo_path(profile_path) or profile_path
    if not resolved_profile.is_file():
        if not auto_analyze:
            raise SystemExit(
                f"Missing non-deterministic profile: {resolved_profile}\n"
                "Run: uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py "
                "analyze-nondeterministic --output-dir project/<project_name>/initialization"
            )
        status = write_nondeterministic_analysis(output_dir, contracts_path)
        if status != 0:
            raise SystemExit("Could not generate non-deterministic profile.")
        generated_default = initialization_dir(output_dir) / "nondeterministic_profile.json"
        if not resolved_profile.is_file() and generated_default.is_file():
            resolved_profile = generated_default
    if not resolved_profile.is_file():
        raise SystemExit(f"Missing non-deterministic profile after analyzer run: {resolved_profile}")
    return load_json_mapping(resolved_profile)

def choose_cuda_tag(profile: dict[str, Any], runtime_name: str) -> dict[str, Any]:
    cuda = profile.get("cuda", {})
    if not isinstance(cuda, dict):
        cuda = {}
    toolkit = str(cuda.get("cuda_toolkit_version") or "")
    gpu_detected = bool(cuda.get("gpu_detected"))
    if not gpu_detected:
        return {
            "cuda_tag": "cpu",
            "torch_index_url": "https://download.pytorch.org/whl/cpu",
            "reason": "No GPU detected; CPU plan generated.",
            "warning": "CPU execution may be slow and is not recommended for AdsorbDiff." if runtime_name == "mesa-adsorbdiff" else "",
        }
    try:
        version = float(".".join(toolkit.split(".")[:2])) if toolkit else 0.0
    except ValueError:
        version = 0.0
    if version >= 12.4:
        tag = "cu124"
    elif version >= 12.1:
        tag = "cu121"
    elif version >= 11.8:
        tag = "cu118"
    else:
        tag = "cu118"
    return {
        "cuda_tag": tag,
        "torch_index_url": f"https://download.pytorch.org/whl/{tag}",
        "reason": f"GPU detected and CUDA toolkit probe reported {toolkit or 'unknown'}; selected {tag}.",
        "warning": "" if toolkit else "CUDA toolkit version was not detected; selected cu118 fallback.",
    }

def command_in_mamba_env(command: str, env_name: str) -> str:
    parts = command.strip().split(" ", 1)
    if parts and parts[0] == "python":
        suffix = parts[1] if len(parts) > 1 else ""
        return f"mamba run -n {env_name} python {suffix}".strip()
    return command

def build_runtime_plan(runtime_name: str, profile: dict[str, Any], contracts: dict[str, Any], profile_path: Path) -> dict[str, Any]:
    runtimes = contracts.get("runtimes", {})
    if not isinstance(runtimes, dict) or runtime_name not in runtimes:
        known = ", ".join(sorted(runtimes)) if isinstance(runtimes, dict) else ""
        raise SystemExit(f"Unknown non-deterministic runtime: {runtime_name}\nKnown runtimes: {known}")
    runtime = runtimes[runtime_name]
    if not isinstance(runtime, dict):
        raise SystemExit(f"Runtime contract is not a mapping: {runtime_name}")

    tools = profile.get("tools", {})
    if not isinstance(tools, dict):
        tools = {}
    scheduler = profile.get("scheduler", {})
    if not isinstance(scheduler, dict):
        scheduler = {}
    checkpoints = profile.get("checkpoints", {})
    if not isinstance(checkpoints, dict):
        checkpoints = {}
    deterministic = runtime.get("deterministic", {})
    if not isinstance(deterministic, dict):
        deterministic = {}

    cuda_choice = choose_cuda_tag(profile, runtime_name)
    env_name = "adsorbdiff" if runtime_name == "mesa-adsorbdiff" else runtime_name
    python_version = str(deterministic.get("python") or "3.11")
    if python_version == "machine-specific":
        python_version = "3.11"

    blockers: list[str] = []
    warnings: list[str] = []
    if not tools.get("mamba"):
        blockers.append("mamba command is missing; run bootstrap --install-mamba before executing this plan.")
    if cuda_choice.get("warning"):
        warnings.append(str(cuda_choice["warning"]))
    detected_scheduler = scheduler.get("detected", [])
    if not detected_scheduler:
        warnings.append("No qsub/sbatch scheduler command detected; plan uses local environment setup only.")
    if checkpoints.get("HF_TOKEN") != "SET":
        warnings.append("HF_TOKEN is missing; gated/private checkpoint downloads will require it later.")

    commands: list[dict[str, Any]] = [
        {
            "id": "create-env",
            "title": f"Create `{env_name}` environment",
            "kind": "command",
            "category": "environment",
            "cwd": str(REPO_ROOT),
            "command": f"mamba create -y -n {env_name} python={python_version}",
            "requires_yes": True,
        },
        {
            "id": "install-torch",
            "title": f"Install PyTorch for {cuda_choice['cuda_tag']}",
            "kind": "command",
            "category": "environment",
            "cwd": str(REPO_ROOT),
            "command": f"mamba run -n {env_name} python -m pip install torch torchvision torchaudio --index-url {cuda_choice['torch_index_url']}",
            "requires_yes": True,
        },
    ]

    if runtime_name == "mesa-adsorbdiff":
        cuda_tag = cuda_choice["cuda_tag"]
        commands.append(
            {
                "id": "install-pyg-extensions",
                "title": "Install PyG extension wheels matched to installed torch",
                "kind": "command",
                "category": "environment",
                "cwd": str(REPO_ROOT),
                "command": (
                    "TORCH_VERSION=$(mamba run -n adsorbdiff python -c "
                    "\"import torch; print(torch.__version__.split('+')[0])\") && "
                    "mamba run -n adsorbdiff python -m pip install "
                    "pyg_lib torch_scatter torch_sparse torch_cluster torch_spline_conv "
                    f"-f \"https://data.pyg.org/whl/torch-${{TORCH_VERSION}}+{cuda_tag}.html\""
                ),
                "requires_yes": True,
                "posix_shell": True,
            }
        )
    else:
        commands.append(
            {
                "id": "install-uma-packages",
                "title": "Install ASE and FAIR-Chem/UMA Python packages",
                "kind": "command",
                "category": "environment",
                "cwd": str(REPO_ROOT),
                "command": f"mamba run -n {env_name} python -m pip install ase fairchem-core",
                "requires_yes": True,
            }
        )

    smoke_commands = string_list(deterministic.get("smoke"))
    for index, smoke in enumerate(smoke_commands, start=1):
        commands.append(
            {
                "id": f"smoke-{index}",
                "title": "Run runtime smoke test",
                "kind": "command",
                "category": "smoke",
                "cwd": str(REPO_ROOT),
                "command": command_in_mamba_env(smoke, env_name),
                "requires_yes": True,
            }
        )

    checkpoint_names = string_list(deterministic.get("checkpoint_names"))
    if checkpoint_names:
        commands.append(
            {
                "id": "checkpoint-notice",
                "title": "Checkpoint download not included",
                "kind": "notification",
                "category": "checkpoint",
                "message": "Checkpoint files are not downloaded by this runtime install plan. Review checkpoint paths separately before running model workflows.",
                "expected_checkpoint_names": checkpoint_names,
            }
        )

    return {
        "schema": "mesa.runtime-plan.v1",
        "generated_at": utc_timestamp(),
        "runtime": runtime_name,
        "environment_name": env_name,
        "source_profile": str(profile_path),
        "approval_required": True,
        "blocked": bool(blockers),
        "blockers": blockers,
        "warnings": warnings,
        "decisions": {
            "cuda": cuda_choice,
            "scheduler": {
                "policy": scheduler.get("policy", "deferred_until_final_stage"),
                "detected": detected_scheduler if isinstance(detected_scheduler, list) else [],
                "submit_jobs": False,
            },
            "checkpoints": {
                "HF_TOKEN": checkpoints.get("HF_TOKEN", "MISSING"),
                "HF_HOME": checkpoints.get("HF_HOME", "MISSING"),
                "download_checkpoints": False,
                "expected_names": checkpoint_names,
            },
        },
        "steps": commands,
        "execution": {
            "requires_yes": True,
            "no_checkpoint_downloads": True,
            "no_scheduler_jobs": True,
            "executor_command": "uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan <PLAN_JSON> --yes",
        },
    }

def render_runtime_plan(plan: dict[str, Any]) -> str:
    runtime = plan.get("runtime", "unknown-runtime")
    decisions = plan.get("decisions", {})
    if not isinstance(decisions, dict):
        decisions = {}
    cuda = decisions.get("cuda", {})
    scheduler = decisions.get("scheduler", {})
    checkpoints = decisions.get("checkpoints", {})
    if not isinstance(cuda, dict):
        cuda = {}
    if not isinstance(scheduler, dict):
        scheduler = {}
    if not isinstance(checkpoints, dict):
        checkpoints = {}

    lines = [
        f"# Runtime Install Plan: {runtime}",
        "",
        "Review this plan before execution. It is a saved proposal; the executor will not run it unless called with `--yes`.",
        "",
        "## Summary",
        "",
        f"- Runtime: `{runtime}`",
        f"- Environment name: `{plan.get('environment_name', runtime)}`",
        f"- Generated at: `{plan.get('generated_at', 'unknown')}`",
        f"- Source profile: `{plan.get('source_profile', '')}`",
        f"- Blocked: `{plan.get('blocked', False)}`",
        "",
        "## Decisions",
        "",
        f"- CUDA/Torch: `{cuda.get('cuda_tag', 'unknown')}` via `{cuda.get('torch_index_url', 'unknown')}`",
        f"- CUDA rationale: {cuda.get('reason', '')}",
        f"- Scheduler policy: `{scheduler.get('policy', 'deferred_until_final_stage')}`",
        f"- Scheduler job submission: `{scheduler.get('submit_jobs', False)}`",
        f"- Checkpoint downloads: `{checkpoints.get('download_checkpoints', False)}`",
        f"- HF_TOKEN: `{checkpoints.get('HF_TOKEN', 'MISSING')}` value intentionally not recorded",
        "",
    ]

    blockers = string_list(plan.get("blockers"))
    warnings = string_list(plan.get("warnings"))
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {item}" for item in blockers)
        lines.append("")
    if warnings:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {item}" for item in warnings)
        lines.append("")

    lines.extend(["## Steps", ""])
    for step in plan.get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        lines.append(f"### {step.get('id', 'step')}: {step.get('title', '')}")
        if step.get("kind") == "command":
            lines.append("")
            lines.append("```bash")
            lines.append(str(step.get("command", "")))
            lines.append("```")
        else:
            lines.append(str(step.get("message", "")))
        lines.append("")

    lines.extend(
        [
            "## Approval",
            "",
            "Dry-run the saved plan:",
            "",
            "```bash",
            "uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan <PLAN_JSON>",
            "```",
            "",
            "Execute only after review:",
            "",
            "```bash",
            "uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan <PLAN_JSON> --yes",
            "```",
            "",
        ]
    )
    return "\n".join(lines)

def write_runtime_plan(
    runtime_name: str,
    output_dir: Path | None,
    project_dir: Path | None,
    profile_path: Path | None,
    contracts_path: Path,
    auto_analyze: bool = True,
) -> int:
    contracts_path = repo_path(contracts_path) or DEFAULT_HANDOFF_CONTRACT
    contracts = load_handoff_contract(contracts_path)
    names = contract_output_names(contracts)
    project_out = initialization_dir(project_dir)
    if profile_path is None:
        profile_resolved = project_out / names["analyzer_json"]
    else:
        profile_resolved = repo_path(profile_path) or profile_path
    profile = ensure_nondeterministic_profile(profile_resolved, project_out, contracts_path, auto_analyze)
    plan = build_runtime_plan(runtime_name, profile, contracts, profile_resolved)

    plan_dir = repo_path(output_dir) or (project_out / names["runtime_plan_dir"])
    plan_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{safe_filename(runtime_name)}_plan"
    json_path = plan_dir / f"{stem}.json"
    markdown_path = plan_dir / f"{stem}.md"
    plan["plan_json"] = str(json_path)
    plan["plan_markdown"] = str(markdown_path)
    json_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_runtime_plan(plan), encoding="utf-8")

    append_initialize_event(
        project_out,
        "runtime-plan-generated",
        "blocked" if plan.get("blocked") else "ready",
        f"Generated runtime plan for {runtime_name}.",
        {"plan_json": str(json_path), "plan_markdown": str(markdown_path), "runtime": runtime_name},
        contracts,
    )
    status_path = write_initialize_status(
        project_out,
        contracts,
        f"Runtime plan generated for `{runtime_name}`. Review the plan before execution.",
    )

    print("\nRuntime plan generator")
    print(f"  runtime: {runtime_name}")
    print(f"  plan json: OK {json_path}")
    print(f"  plan markdown: OK {markdown_path}")
    print(f"  status: OK {status_path}")
    if plan.get("blocked"):
        print("  execution: BLOCKED until blockers are resolved")
        for blocker in plan.get("blockers", []) or []:
            print(f"    - {blocker}")
    else:
        print("  execution: ready after explicit --yes")
    print("  next dry-run:")
    print(f"    uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan {json_path}")
    print("  next execute:")
    print(f"    uv run --python 3.11 python DEPENDENCY/tools/mesa_env.py execute-runtime-plan {json_path} --yes")
    return 0
