"""Machine-specific runtime profiling for initialize-mesa."""
from __future__ import annotations

from .common import *

def collect_machine_profile(contracts_path: Path = DEFAULT_HANDOFF_CONTRACT) -> dict[str, Any]:
    env_values = merged_env_values()
    tool_names = [
        "uv",
        "python",
        "python3",
        "mamba",
        "micromamba",
        "conda",
        "nvidia-smi",
        "nvcc",
        "qsub",
        "sbatch",
    ]
    env_keys = [
        "HF_TOKEN",
        "HF_HOME",
        "CUDA_VISIBLE_DEVICES",
        "MESA_UMA_DEVICE",
        "PYTHON_BIN",
    ]
    return {
        "repo": str(REPO_ROOT),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "files": {
            "dependency_env": {
                "path": str(DEPENDENCY_ENV),
                "exists": DEPENDENCY_ENV.is_file(),
            },
            "handoff_contract": {
                "path": str(contracts_path),
                "exists": contracts_path.is_file(),
            },
        },
        "tools": {name: find_tool(name) for name in tool_names},
        "env": {key: ("SET" if env_values.get(key) else "MISSING") for key in env_keys},
        "probes": {
            "nvidia_smi": run_probe(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,driver_version",
                    "--format=csv,noheader",
                ]
            ),
            "nvcc": run_probe(["nvcc", "--version"]),
            "torch": run_probe(
                [
                    "python",
                    "-c",
                    "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())",
                ]
            ),
            "qsub": run_probe(["qsub", "--version"]),
            "sbatch": run_probe(["sbatch", "--version"]),
        },
    }

def parse_nvidia_smi_gpus(stdout: str) -> list[dict[str, str]]:
    gpus: list[dict[str, str]] = []
    for line in stdout.strip().splitlines():
        parts = [part.strip() for part in line.split(",")]
        if not parts or not parts[0]:
            continue
        entry = {"name": parts[0]}
        if len(parts) > 1:
            entry["memory_total"] = parts[1]
        if len(parts) > 2:
            entry["driver_version"] = parts[2]
        gpus.append(entry)
    return gpus

def parse_nvcc_release(stdout: str) -> str | None:
    match = re.search(r"release\s+([0-9.]+)", stdout)
    return match.group(1) if match else None

def parse_torch_probe(probe: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "python_command_available": bool(probe.get("available")),
        "import_ok": probe.get("returncode") == 0,
    }
    if probe.get("returncode") == 0:
        parts = str(probe.get("stdout", "")).strip().split()
        if parts:
            result["torch_version"] = parts[0]
        if len(parts) > 1:
            result["torch_cuda_version"] = parts[1]
        if len(parts) > 2:
            result["torch_cuda_available"] = parts[2].lower() == "true"
    else:
        text = str(probe.get("stderr") or probe.get("stdout") or probe.get("error") or "").strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        result["error_summary"] = lines[-1] if lines else ""
    return result

def summarize_tool_paths(tools: dict[str, Any], names: list[str]) -> dict[str, Any]:
    return {name: tools.get(name) for name in names}

def runtime_checkpoint_expectations(contracts: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    runtimes = contracts.get("runtimes", {})
    if not isinstance(runtimes, dict):
        return out
    for runtime_name, runtime in runtimes.items():
        if not isinstance(runtime, dict):
            continue
        deterministic = runtime.get("deterministic", {})
        if not isinstance(deterministic, dict):
            deterministic = {}
        names = string_list(deterministic.get("checkpoint_names"))
        policy = deterministic.get("checkpoint_policy")
        if names or policy:
            out[str(runtime_name)] = {
                "expected_names": names,
                "policy": policy,
            }
    return out

def collect_nondeterministic_profile(contracts_path: Path, contracts: dict[str, Any]) -> dict[str, Any]:
    base = collect_machine_profile(contracts_path)
    tools = base.get("tools", {})
    if not isinstance(tools, dict):
        tools = {}
    probes = base.get("probes", {})
    if not isinstance(probes, dict):
        probes = {}
    env = base.get("env", {})
    if not isinstance(env, dict):
        env = {}

    nvidia_probe = probes.get("nvidia_smi", {})
    nvcc_probe = probes.get("nvcc", {})
    torch_probe = probes.get("torch", {})
    qsub_probe = probes.get("qsub", {})
    sbatch_probe = probes.get("sbatch", {})
    if not isinstance(nvidia_probe, dict):
        nvidia_probe = {}
    if not isinstance(nvcc_probe, dict):
        nvcc_probe = {}
    if not isinstance(torch_probe, dict):
        torch_probe = {}
    if not isinstance(qsub_probe, dict):
        qsub_probe = {}
    if not isinstance(sbatch_probe, dict):
        sbatch_probe = {}

    gpus = parse_nvidia_smi_gpus(str(nvidia_probe.get("stdout", ""))) if nvidia_probe.get("returncode") == 0 else []
    detected_schedulers = [
        name
        for name, probe in (("qsub", qsub_probe), ("sbatch", sbatch_probe))
        if probe.get("available")
    ]

    handoff = contracts.get("handoff", {})
    if not isinstance(handoff, dict):
        handoff = {}
    runtimes = contracts.get("runtimes", {})
    if not isinstance(runtimes, dict):
        runtimes = {}

    return {
        "schema": "mesa.nondeterministic-profile.v1",
        "repo": base.get("repo", str(REPO_ROOT)),
        "contract": {
            "path": str(contracts_path),
            "exists": contracts_path.is_file(),
            "version": contracts.get("version"),
        },
        "platform": base.get("platform", {}),
        "python_env": {
            "checker_python": (base.get("platform", {}) or {}).get("python"),
            "python": tools.get("python"),
            "python3": tools.get("python3"),
            "PYTHON_BIN": env.get("PYTHON_BIN", "MISSING"),
            "torch": parse_torch_probe(torch_probe),
            "torch_probe": torch_probe,
        },
        "tools": summarize_tool_paths(
            tools,
            ["uv", "python", "python3", "mamba", "micromamba", "conda", "nvidia-smi", "nvcc", "qsub", "sbatch"],
        ),
        "env": env,
        "cuda": {
            "gpu_detected": bool(gpus),
            "gpus": gpus,
            "driver_version": gpus[0].get("driver_version") if gpus else None,
            "cuda_toolkit_version": parse_nvcc_release(str(nvcc_probe.get("stdout", ""))),
            "nvidia_smi": nvidia_probe,
            "nvcc": nvcc_probe,
            "torch": parse_torch_probe(torch_probe),
        },
        "scheduler": {
            "policy": handoff.get("scheduler_policy", "deferred_until_final_stage"),
            "detected": detected_schedulers,
            "qsub": qsub_probe,
            "sbatch": sbatch_probe,
        },
        "checkpoints": {
            "HF_TOKEN": env.get("HF_TOKEN", "MISSING"),
            "HF_HOME": env.get("HF_HOME", "MISSING"),
            "runtime_expectations": runtime_checkpoint_expectations(contracts),
            "download_policy": "do_not_download_without_explicit_yes",
        },
        "runtimes": runtimes,
        "policy": {
            "install_policy": handoff.get("install_policy", "do_not_install_without_explicit_yes"),
            "checkpoint_downloads_without_yes": False,
            "scheduler_jobs_without_yes": False,
        },
    }
