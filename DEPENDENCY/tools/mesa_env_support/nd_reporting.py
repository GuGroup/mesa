"""Markdown/JSON report writers for non-deterministic initialize-mesa state."""
from __future__ import annotations

from .common import *
from .nd_profile import *

def first_probe_line(probe: dict[str, Any]) -> str:
    for key in ("stdout", "stderr", "error"):
        value = str(probe.get(key, "")).strip()
        if value:
            return value.splitlines()[0]
    return ""

def probe_summary(name: str, probe: dict[str, Any]) -> str:
    if not probe.get("available"):
        return f"- `{name}`: MISSING"
    rc = probe.get("returncode")
    status = "OK" if rc == 0 else f"returncode {rc}"
    detail = first_probe_line(probe)
    if detail:
        return f"- `{name}`: {status} - {detail}"
    return f"- `{name}`: {status}"

def render_handoff(profile: dict[str, Any], contracts: dict[str, Any]) -> str:
    handoff = contracts.get("handoff", {})
    if not isinstance(handoff, dict):
        handoff = {}
    runtimes = contracts.get("runtimes", {})
    if not isinstance(runtimes, dict):
        runtimes = {}

    platform_info = profile.get("platform", {})
    tools = profile.get("tools", {})
    env = profile.get("env", {})
    probes = profile.get("probes", {})

    lines: list[str] = [
        "# MESA Non-Deterministic Dependency Handoff",
        "",
        "This file is for future Codex setup of machine-specific runtimes. It records detected facts and the remaining decisions without installing CUDA stacks, downloading checkpoints, or configuring schedulers.",
        "",
        "## Machine Profile",
        "",
        f"- Repo: `{profile.get('repo', REPO_ROOT)}`",
        f"- OS: `{platform_info.get('system', 'unknown')} {platform_info.get('release', '')}`",
        f"- Machine: `{platform_info.get('machine', 'unknown')}`",
        f"- Checker Python: `{platform_info.get('python', 'unknown')}`",
        "",
        "## Tool Presence",
        "",
    ]

    for name in ("uv", "python", "python3", "mamba", "micromamba", "conda", "nvidia-smi", "nvcc", "qsub", "sbatch"):
        path = tools.get(name) if isinstance(tools, dict) else None
        lines.append(f"- `{name}`: {'OK ' + str(path) if path else 'MISSING'}")

    lines.extend(["", "## Environment Presence", ""])
    for key in ("HF_TOKEN", "HF_HOME", "CUDA_VISIBLE_DEVICES", "MESA_UMA_DEVICE", "PYTHON_BIN"):
        state = env.get(key, "MISSING") if isinstance(env, dict) else "MISSING"
        note = " value intentionally not recorded" if key.endswith("TOKEN") else ""
        lines.append(f"- `{key}`: {state}{note}")

    lines.extend(["", "## Probe Summary", ""])
    if isinstance(probes, dict):
        for key in ("nvidia_smi", "nvcc", "torch", "qsub", "sbatch"):
            probe = probes.get(key, {})
            if isinstance(probe, dict):
                lines.append(probe_summary(key, probe))

    scheduler_policy = handoff.get("scheduler_policy", "deferred_until_final_stage")
    install_policy = handoff.get("install_policy", "do_not_install_without_explicit_yes")
    lines.extend(
        [
            "",
            "## Global Policy",
            "",
            f"- Scheduler setup: `{scheduler_policy}`",
            f"- Install policy: `{install_policy}`",
            "- Do not download checkpoint/model files without explicit user approval.",
            "- Do not submit scheduler jobs from this handoff.",
            "- Prefer deterministic core setup first; handle CUDA and checkpoints only after inspecting the target machine.",
        ]
    )

    for runtime_name in sorted(runtimes):
        runtime = runtimes[runtime_name]
        if not isinstance(runtime, dict):
            continue
        deterministic = runtime.get("deterministic", {})
        decisions = runtime.get("codex_must_decide", {})
        if not isinstance(deterministic, dict):
            deterministic = {}
        if not isinstance(decisions, dict):
            decisions = {}

        lines.extend(
            [
                "",
                f"## {runtime_name}",
                "",
                str(runtime.get("description", "")).strip(),
                "",
                "### Deterministic Requirements",
                "",
                f"- Python: `{deterministic.get('python', 'machine-specific')}`",
            ]
        )

        required_imports = string_list(deterministic.get("required_imports"))
        if required_imports:
            lines.append("- Required imports:")
            lines.extend(f"  - `{item}`" for item in required_imports)

        optional_env = string_list(deterministic.get("optional_env"))
        if optional_env:
            lines.append("- Optional environment variables:")
            lines.extend(f"  - `{item}`" for item in optional_env)

        checkpoints = string_list(deterministic.get("checkpoint_names"))
        if checkpoints:
            lines.append("- Expected checkpoint names:")
            lines.extend(f"  - `{item}`" for item in checkpoints)

        baseline_commands = string_list(deterministic.get("baseline_commands"))
        if baseline_commands:
            lines.append("- Baseline commands to adapt after CUDA inspection:")
            lines.extend(f"  - `{item}`" for item in baseline_commands)

        smoke = deterministic.get("smoke")
        if smoke:
            lines.append(f"- Smoke test: `{smoke}`")

        checkpoint_policy = deterministic.get("checkpoint_policy")
        if checkpoint_policy:
            lines.append(f"- Checkpoint policy: {checkpoint_policy}")

        lines.extend(["", "### Codex Must Decide", ""])
        for section_name in ("cuda", "checkpoints", "scheduler"):
            section = decisions.get(section_name, {})
            if not isinstance(section, dict):
                continue
            lines.append(f"- {section_name}:")
            for key, value in section.items():
                if isinstance(value, list):
                    joined = ", ".join(f"`{item}`" for item in value)
                    lines.append(f"  - {key}: {joined}")
                else:
                    lines.append(f"  - {key}: `{value}`")

    lines.append("")
    return "\n".join(lines)

def render_nondeterministic_profile(profile: dict[str, Any]) -> str:
    platform_info = profile.get("platform", {})
    if not isinstance(platform_info, dict):
        platform_info = {}
    tools = profile.get("tools", {})
    if not isinstance(tools, dict):
        tools = {}
    env = profile.get("env", {})
    if not isinstance(env, dict):
        env = {}
    cuda = profile.get("cuda", {})
    if not isinstance(cuda, dict):
        cuda = {}
    scheduler = profile.get("scheduler", {})
    if not isinstance(scheduler, dict):
        scheduler = {}
    checkpoints = profile.get("checkpoints", {})
    if not isinstance(checkpoints, dict):
        checkpoints = {}
    python_env = profile.get("python_env", {})
    if not isinstance(python_env, dict):
        python_env = {}
    policy = profile.get("policy", {})
    if not isinstance(policy, dict):
        policy = {}

    lines: list[str] = [
        "# MESA Non-Deterministic Analyzer Profile",
        "",
        "This profile records machine-specific facts needed before planning CUDA, scheduler, checkpoint, UMA, or AdsorbDiff setup. It is read-only: it does not install dependencies, download checkpoints, or submit jobs.",
        "",
        "## Platform",
        "",
        f"- Repo: `{profile.get('repo', REPO_ROOT)}`",
        f"- OS: `{platform_info.get('system', 'unknown')} {platform_info.get('release', '')}`",
        f"- Machine: `{platform_info.get('machine', 'unknown')}`",
        f"- Checker Python: `{platform_info.get('python', 'unknown')}`",
        "",
        "## Python And Tools",
        "",
    ]

    for name in ("uv", "python", "python3", "mamba", "micromamba", "conda"):
        path = tools.get(name)
        lines.append(f"- `{name}`: {'OK ' + str(path) if path else 'MISSING'}")

    torch = python_env.get("torch", {})
    if isinstance(torch, dict):
        if torch.get("import_ok"):
            lines.append(
                "- `torch`: OK "
                f"{torch.get('torch_version', 'unknown')} "
                f"cuda={torch.get('torch_cuda_version', 'unknown')} "
                f"available={torch.get('torch_cuda_available')}"
            )
        else:
            lines.append(f"- `torch`: MISSING {torch.get('error_summary', '')}".rstrip())

    lines.extend(["", "## CUDA/GPU", ""])
    lines.append(f"- GPU detected: `{bool(cuda.get('gpu_detected'))}`")
    for gpu in cuda.get("gpus", []) or []:
        if isinstance(gpu, dict):
            detail = ", ".join(
                str(part)
                for part in (
                    gpu.get("name"),
                    gpu.get("memory_total"),
                    f"driver {gpu.get('driver_version')}" if gpu.get("driver_version") else None,
                )
                if part
            )
            lines.append(f"- GPU: `{detail}`")
    lines.append(f"- CUDA toolkit from `nvcc`: `{cuda.get('cuda_toolkit_version') or 'MISSING'}`")
    for key in ("nvidia_smi", "nvcc"):
        probe = cuda.get(key, {})
        if isinstance(probe, dict):
            lines.append(probe_summary(key, probe))

    lines.extend(["", "## Scheduler/HPC", ""])
    detected = scheduler.get("detected", [])
    if not isinstance(detected, list):
        detected = []
    lines.append(f"- Policy: `{scheduler.get('policy', 'deferred_until_final_stage')}`")
    lines.append(f"- Detected scheduler commands: `{', '.join(str(item) for item in detected) if detected else 'none'}`")
    for key in ("qsub", "sbatch"):
        probe = scheduler.get(key, {})
        if isinstance(probe, dict):
            lines.append(probe_summary(key, probe))

    lines.extend(["", "## Checkpoints", ""])
    for key in ("HF_TOKEN", "HF_HOME"):
        state = checkpoints.get(key, "MISSING")
        suffix = " value intentionally not recorded" if key.endswith("TOKEN") else ""
        lines.append(f"- `{key}`: {state}{suffix}")
    lines.append(f"- Download policy: `{checkpoints.get('download_policy', 'do_not_download_without_explicit_yes')}`")
    expectations = checkpoints.get("runtime_expectations", {})
    if isinstance(expectations, dict) and expectations:
        for runtime_name in sorted(expectations):
            entry = expectations[runtime_name]
            if not isinstance(entry, dict):
                continue
            names = entry.get("expected_names", []) or []
            if names:
                lines.append(f"- `{runtime_name}` expected checkpoints: {', '.join(f'`{name}`' for name in names)}")
            if entry.get("policy"):
                lines.append(f"- `{runtime_name}` policy: {entry.get('policy')}")

    lines.extend(["", "## Runtime Decision Inputs", ""])
    runtimes = profile.get("runtimes", {})
    if isinstance(runtimes, dict):
        for runtime_name in sorted(runtimes):
            runtime = runtimes[runtime_name]
            if not isinstance(runtime, dict):
                continue
            lines.append(f"### {runtime_name}")
            desc = str(runtime.get("description", "")).strip()
            if desc:
                lines.append(desc)
            deterministic = runtime.get("deterministic", {})
            decisions = runtime.get("codex_must_decide", {})
            if isinstance(deterministic, dict):
                imports = string_list(deterministic.get("required_imports"))
                if imports:
                    lines.append("- Required imports: " + ", ".join(f"`{item}`" for item in imports))
                smoke = deterministic.get("smoke")
                if smoke:
                    lines.append(f"- Smoke test: `{smoke}`")
            if isinstance(decisions, dict):
                for section_name in ("cuda", "checkpoints", "scheduler"):
                    section = decisions.get(section_name, {})
                    if isinstance(section, dict):
                        lines.append(f"- Must decide `{section_name}` before execution")
            lines.append("")

    lines.extend(
        [
            "## Policy",
            "",
            f"- Install policy: `{policy.get('install_policy', 'do_not_install_without_explicit_yes')}`",
            f"- Checkpoint downloads without `--yes`: `{policy.get('checkpoint_downloads_without_yes', False)}`",
            f"- Scheduler jobs without `--yes`: `{policy.get('scheduler_jobs_without_yes', False)}`",
            "",
            "Next stage: a runtime plan generator may consume `nondeterministic_profile.json`; no executor should re-decide machine-specific choices that are already recorded in a saved plan.",
            "",
        ]
    )
    return "\n".join(lines)

def write_nondeterministic_analysis(output_dir: Path | None, contracts_path: Path) -> int:
    print("\nNon-deterministic analyzer")
    contracts_path = repo_path(contracts_path) or DEFAULT_HANDOFF_CONTRACT
    try:
        contracts = load_handoff_contract(contracts_path)
    except Exception as exc:
        print(f"  analyzer contract: MISSING {exc}")
        return 1

    handoff = contracts.get("handoff", {})
    if not isinstance(handoff, dict):
        handoff = {}
    out_dir = initialization_dir(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_name = str(handoff.get("analyzer_output_json", "nondeterministic_profile.json"))
    markdown_name = str(handoff.get("analyzer_output_markdown", "nondeterministic_profile.md"))
    json_path = out_dir / json_name
    markdown_path = out_dir / markdown_name

    profile = collect_nondeterministic_profile(contracts_path, contracts)
    json_path.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_nondeterministic_profile(profile), encoding="utf-8")

    print(f"  contract: OK {contracts_path}")
    print(f"  profile json: OK {json_path}")
    print(f"  profile markdown: OK {markdown_path}")
    print("  installs: none")
    print("  checkpoint downloads: none")
    print("  scheduler jobs: none")
    return 0

def write_dependency_handoff(output_dir: Path | None, contracts_path: Path) -> int:
    print("\nNon-deterministic runtime handoff")
    contracts_path = repo_path(contracts_path) or DEFAULT_HANDOFF_CONTRACT
    try:
        contracts = load_handoff_contract(contracts_path)
    except Exception as exc:
        print(f"  handoff contract: MISSING {exc}")
        return 1

    profile = collect_machine_profile(contracts_path)
    out_dir = initialization_dir(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "machine_profile.json"
    markdown_path = out_dir / "dependency_handoff.md"

    json_path.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_handoff(profile, contracts), encoding="utf-8")

    print(f"  contract: OK {contracts_path}")
    print(f"  machine profile: OK {json_path}")
    print(f"  handoff markdown: OK {markdown_path}")
    print("  installs: none")
    print("  checkpoint downloads: none")
    return 0
