#!/usr/bin/env python3
"""Build a dry-run or executable AdsorbDiff sampling/relaxation workflow."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
DEFAULT_REPO = SKILL_DIR / "assets" / "AdsorbDiff"
TASK_ID = "TASK_ADSORBDIFF_PLACEMENT"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("input JSON must contain an object at the top level")
    return data


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def as_path(value: str | os.PathLike[str], base: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (base / path).resolve()


def script_path(value: str | os.PathLike[str]) -> str:
    text = str(value)
    if os.name == "nt":
        text = text.replace("\\", "/")
    return text


def q(value: str | os.PathLike[str]) -> str:
    return shlex.quote(script_path(value))


def rel_or_abs(path: str, repo: Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        return script_path(candidate)
    return script_path(path)


def config_path(value: str | os.PathLike[str], repo: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return repo / path


def command_prefix(python_exe: str, distributed: bool, ngpus: int, port: int) -> list[str]:
    if distributed:
        return [
            python_exe,
            "-u",
            "-m",
            "torch.distributed.launch",
            f"--nproc_per_node={ngpus}",
            f"--master_port={port}",
            "main.py",
        ]
    return [python_exe, "-u", "main.py"]


def shell_join(parts: list[str]) -> str:
    return " ".join(q(part) for part in parts)


def get_section(data: dict[str, Any], name: str) -> dict[str, Any]:
    section = data.get(name, {})
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise ValueError(f"{name} must be an object")
    return section


def localize_adsorbdiff_config(
    source_config: str | os.PathLike[str],
    local_repo: Path,
    output_path: Path,
    relax_dataset_src: Path | str | None,
    relax_traj_dir: Path | str,
    section: dict[str, Any],
    mode: str,
    errors: list[dict[str, str]],
) -> str:
    source_path = config_path(source_config, local_repo)
    if not source_path.exists():
        errors.append({"type": "MissingPath", "message": f"config_yml does not exist: {source_path}"})
        return str(source_config)

    try:
        loaded = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report structured workflow errors.
        errors.append({"type": type(exc).__name__, "message": f"failed to read config_yml {source_path}: {exc}"})
        return str(source_config)
    if not isinstance(loaded, dict):
        errors.append({"type": "InvalidInput", "message": f"config_yml must contain a YAML object: {source_path}"})
        return str(source_config)

    config = dict(loaded)
    config["dataset"] = [{}]
    config.pop("val_dataset", None)

    task = config.setdefault("task", {})
    if isinstance(task, dict):
        relax_dataset = task.setdefault("relax_dataset", {})
        if isinstance(relax_dataset, dict) and relax_dataset_src is not None:
            relax_dataset["src"] = script_path(relax_dataset_src)
        relax_opt = task.setdefault("relax_opt", {})
        if isinstance(relax_opt, dict):
            relax_opt["traj_dir"] = script_path(relax_traj_dir)
        if section.get("relaxation_steps") is not None:
            task["relaxation_steps"] = int(section["relaxation_steps"])
        if section.get("relaxation_fmax") is not None:
            task["relaxation_fmax"] = float(section["relaxation_fmax"])

    optim = config.setdefault("optim", {})
    if isinstance(optim, dict):
        optim["batch_size"] = int(section.get("batch_size", 1))
        optim["eval_batch_size"] = int(section.get("eval_batch_size", 1))
        optim["num_workers"] = int(section.get("num_workers", 0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return str(output_path)


def add_path_check(
    path_text: str | None,
    label: str,
    base: Path,
    allow_missing: bool,
    errors: list[dict[str, str]],
    messages: list[str],
) -> Path | None:
    if not path_text:
        errors.append({"type": "MissingInput", "message": f"{label} is required."})
        return None
    path = as_path(path_text, base)
    if not path.exists():
        item = f"{label} does not exist yet: {path}"
        if allow_missing:
            messages.append(item)
        else:
            errors.append({"type": "MissingPath", "message": item})
    return path


def build_plan(data: dict[str, Any], workdir: Path, execute: bool) -> tuple[dict[str, Any], str]:
    messages: list[str] = []
    errors: list[dict[str, str]] = []
    generated_files: list[str] = []

    local_repo = as_path(str(data.get("adsorbdiff_repo", DEFAULT_REPO)), SKILL_DIR)
    runtime_repo = str(data.get("runtime_adsorbdiff_repo", local_repo))
    python_exe = str(data.get("python", "python"))
    ngpus = int(data.get("ngpus", 1))
    master_port = int(data.get("master_port", 1235))
    distributed = bool(data.get("distributed", ngpus > 1))
    cpu = bool(data.get("cpu", False))
    amp = bool(data.get("amp", False if cpu else True))
    debug = bool(data.get("debug", True))
    allow_missing_external = bool(data.get("allow_missing_external", not execute))

    required_repo_files = [
        local_repo / "main.py",
        local_repo / "setup.py",
        local_repo / "configs" / "denoising",
        local_repo / "configs" / "relaxation",
    ]
    for repo_file in required_repo_files:
        if not repo_file.exists():
            errors.append(
                {
                    "type": "MissingRepoFile",
                    "message": f"Required AdsorbDiff repo file is missing: {repo_file}",
                }
            )

    sampling = get_section(data, "sampling")
    conversion = get_section(data, "conversion")
    relaxation = get_section(data, "relaxation")
    localize_configs = bool(data.get("localize_configs", True))

    sampling_config = sampling.get("config_yml", "configs/denoising/painn_so3.yml")
    sampling_dataset = add_path_check(
        sampling.get("dataset_src"),
        "sampling.dataset_src",
        workdir,
        allow_missing_external,
        errors,
        messages,
    )
    sampling_checkpoint = add_path_check(
        sampling.get("checkpoint"),
        "sampling.checkpoint",
        workdir,
        allow_missing_external,
        errors,
        messages,
    )
    sampling_traj = as_path(sampling.get("traj_dir", "adsorbdiff_samples"), workdir)
    sampling_seed = int(sampling.get("seed", data.get("seed", 0)))
    sampling_run_dir = as_path(sampling.get("run_dir", "adsorbdiff_run"), workdir)
    so3_cache = as_path(data.get("so3_cache", "so3_cache"), workdir)
    sampling_extra = sampling.get("extra_overrides", [])
    if not isinstance(sampling_extra, list):
        errors.append({"type": "InvalidInput", "message": "sampling.extra_overrides must be a list."})
        sampling_extra = []
    if bool(sampling.get("localize_config", localize_configs)):
        sampling_config = localize_adsorbdiff_config(
            sampling_config,
            local_repo,
            workdir / "results" / "sampling_runtime.yml",
            sampling_dataset or sampling.get("dataset_src", ""),
            sampling_traj,
            sampling,
            "sampling",
            errors,
        )
        generated_files.append(str(sampling_config))

    commands: list[str] = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"cd {q(runtime_repo)}",
        'export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"',
        f"export ADSORBDIFF_SO3_CACHE={q(so3_cache)}",
        f"mkdir -p {q(so3_cache)}",
        f"mkdir -p {q(sampling_traj)} {q(sampling_run_dir)}",
    ]

    sampling_cmd = command_prefix(python_exe, distributed, ngpus, master_port)
    sampling_cmd.extend(
        [
            "--mode",
            "run-relaxations",
            "--config-yml",
            rel_or_abs(str(sampling_config), local_repo),
            "--task.relax_dataset.src=" + script_path(sampling_dataset or sampling.get("dataset_src", "")),
            "--task.relax_opt.traj_dir=" + script_path(sampling_traj),
            "--checkpoint",
            script_path(sampling_checkpoint or sampling.get("checkpoint", "")),
            "--model.sampling=True",
            "--seed",
            str(sampling_seed),
            "--run-dir",
            script_path(sampling_run_dir),
        ]
    )
    if distributed:
        sampling_cmd.append("--distributed")
    if amp:
        sampling_cmd.append("--amp")
    if debug:
        sampling_cmd.append("--debug")
    if cpu:
        sampling_cmd.append("--cpu")
    sampling_cmd.extend(str(item) for item in sampling_extra)
    commands.append(shell_join(sampling_cmd))

    conversion_enabled = bool(conversion.get("enabled", True))
    converted_lmdb = as_path(conversion.get("out_path", sampling_traj / "final_struct_lmdb"), workdir)
    if conversion_enabled:
        converter_kind = str(conversion.get("converter", "skill"))
        skill_converter = SCRIPTS_DIR / "adsorbdiff_traj_to_lmdb.py"
        upstream_converter = local_repo / "scripts" / "create_lmdbs" / "pred_traj_to_lmdb.py"
        converter_path = skill_converter if converter_kind == "skill" else upstream_converter
        if not converter_path.exists():
            errors.append(
                {
                    "type": "MissingRepoFile",
                    "message": f"Trajectory-to-LMDB converter is missing: {converter_path}",
                }
            )
        commands.append(f"mkdir -p {q(converted_lmdb.parent)}")
        if converter_kind == "skill":
            converter_cmd = [
                python_exe,
                script_path(skill_converter),
                "--input-dir",
                script_path(sampling_traj),
                "--output-lmdb",
                script_path(converted_lmdb),
                "--repo",
                script_path(runtime_repo),
                "--num-workers",
                str(int(conversion.get("num_workers", 4))),
                "--summary",
                script_path(as_path(conversion.get("summary", "results/traj_to_lmdb_summary.json"), workdir)),
            ]
            if bool(conversion.get("overwrite", False)):
                converter_cmd.append("--overwrite")
        else:
            converter_cmd = [
                python_exe,
                "scripts/create_lmdbs/pred_traj_to_lmdb.py",
                "--data-path",
                script_path(sampling_traj),
                "--out-path",
                script_path(converted_lmdb),
                "--num-workers",
                str(int(conversion.get("num_workers", 4))),
            ]
        commands.append(shell_join(converter_cmd))

    relaxation_enabled = bool(relaxation.get("enabled", False))
    relaxation_traj = None
    if relaxation_enabled:
        relax_dataset_value = relaxation.get("dataset_src", str(converted_lmdb))
        relax_dataset_path = as_path(relax_dataset_value, workdir)
        relax_dataset_is_generated = conversion_enabled and relax_dataset_path == converted_lmdb
        relax_dataset = add_path_check(
            relax_dataset_value,
            "relaxation.dataset_src",
            workdir,
            allow_missing_external or relax_dataset_is_generated,
            errors,
            messages,
        )
        relax_checkpoint = add_path_check(
            relaxation.get("checkpoint"),
            "relaxation.checkpoint",
            workdir,
            allow_missing_external,
            errors,
            messages,
        )
        relaxation_config = relaxation.get(
            "config_yml", "configs/relaxation/gemnet_oc/gemnet_relax.yml"
        )
        relaxation_traj = as_path(relaxation.get("traj_dir", sampling_traj / "relaxations"), workdir)
        relaxation_run_dir = as_path(relaxation.get("run_dir", "adsorbdiff_relax_run"), workdir)
        relaxation_extra = relaxation.get("extra_overrides", [])
        if not isinstance(relaxation_extra, list):
            errors.append(
                {"type": "InvalidInput", "message": "relaxation.extra_overrides must be a list."}
            )
            relaxation_extra = []
        if bool(relaxation.get("localize_config", localize_configs)):
            relaxation_config = localize_adsorbdiff_config(
                relaxation_config,
                local_repo,
                workdir / "results" / "gemnet_relax_runtime.yml",
                relax_dataset or relax_dataset_value,
                relaxation_traj,
                relaxation,
                "relaxation",
                errors,
            )
            generated_files.append(str(relaxation_config))
        commands.append(f"mkdir -p {q(relaxation_traj)} {q(relaxation_run_dir)}")
        relaxation_cmd = command_prefix(python_exe, distributed, ngpus, master_port + 1)
        relaxation_cmd.extend(
            [
                "--mode",
                "run-relaxations",
                "--config-yml",
                rel_or_abs(str(relaxation_config), local_repo),
                "--checkpoint",
                script_path(relax_checkpoint or relaxation.get("checkpoint", "")),
                "--task.relax_dataset.src=" + script_path(relax_dataset or relax_dataset_value),
                "--task.relax_opt.traj_dir=" + script_path(relaxation_traj),
                "--run-dir",
                script_path(relaxation_run_dir),
            ]
        )
        if distributed:
            relaxation_cmd.append("--distributed")
        if amp:
            relaxation_cmd.append("--amp")
        if debug:
            relaxation_cmd.append("--debug")
        if cpu:
            relaxation_cmd.append("--cpu")
        relaxation_cmd.extend(str(item) for item in relaxation_extra)
        commands.append(shell_join(relaxation_cmd))

    script = "\n\n".join(commands) + "\n"
    plan = {
        "status": "failure" if errors else "success",
        "task_id": TASK_ID,
        "skill": "adsorbdiff-placement",
        "data": {
            "adsorbdiff_repo": str(local_repo),
            "runtime_adsorbdiff_repo": runtime_repo,
            "so3_cache": str(so3_cache),
            "ngpus": ngpus,
            "distributed": distributed,
            "cpu": cpu,
            "sampling": {
                "config_yml": str(sampling_config),
                "dataset_src": str(sampling_dataset or sampling.get("dataset_src", "")),
                "checkpoint": str(sampling_checkpoint or sampling.get("checkpoint", "")),
                "traj_dir": str(sampling_traj),
                "seed": sampling_seed,
            },
            "conversion": {
                "enabled": conversion_enabled,
                "out_path": str(converted_lmdb),
                "converter": str(conversion.get("converter", "skill")),
            },
            "relaxation": {
                "enabled": relaxation_enabled,
                "traj_dir": str(relaxation_traj) if relaxation_traj else None,
            },
        },
        "artifacts": [],
        "messages": messages,
        "errors": errors,
        "provenance": {
            "inputs": [],
            "external_calls": [],
            "generated_files": generated_files,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "next_action": {
            "recommendation": "fix_errors" if errors else ("executed" if execute else "review_submit_script"),
            "reason": "Resolve missing or invalid inputs." if errors else "AdsorbDiff workflow plan is ready.",
        },
    }
    return plan, script


def template() -> dict[str, Any]:
    return {
        "workdir": "runs/adsorbdiff_job",
        "ngpus": 1,
        "cpu": False,
        "localize_configs": True,
        "sampling": {
            "dataset_src": "/path/to/sampling_lmdb",
            "checkpoint": "/path/to/PT_zeroshot_painn.pt",
            "config_yml": "configs/denoising/painn_so3.yml",
            "traj_dir": "samples/site0",
            "seed": 0,
        },
        "conversion": {
            "enabled": True,
            "converter": "skill",
            "out_path": "samples/site0/final_struct_lmdb",
            "num_workers": 4,
        },
        "relaxation": {
            "enabled": True,
            "dataset_src": "samples/site0/final_struct_lmdb",
            "checkpoint": "/path/to/gemnet_oc_base_s2ef_2M.pt",
            "config_yml": "configs/relaxation/gemnet_oc/gemnet_relax.yml",
            "traj_dir": "samples/site0/relaxations",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="AdsorbDiff workflow input JSON.")
    parser.add_argument("--workdir", type=Path, help="Workflow directory.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Plan JSON output path. Defaults to <workdir>/results/adsorbdiff_plan.json.",
    )
    parser.add_argument(
        "--script-output",
        type=Path,
        help="Bash script output path. Defaults to <workdir>/submit_adsorbdiff.sh.",
    )
    parser.add_argument("--execute", action="store_true", help="Run the generated bash script.")
    parser.add_argument("--print-template", action="store_true", help="Print an example input JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.print_template:
        print(json.dumps(template(), indent=2, sort_keys=True))
        return 0
    if args.input is None:
        print("--input is required unless --print-template is used", file=sys.stderr)
        return 2

    input_path = args.input.resolve()
    data = read_json(input_path)
    workdir = as_path(str(args.workdir or data.get("workdir", ".")), Path.cwd())
    output = as_path(str(args.output or workdir / "results" / "adsorbdiff_plan.json"), Path.cwd())
    script_output = as_path(str(args.script_output or workdir / "submit_adsorbdiff.sh"), Path.cwd())

    plan, script = build_plan(data, workdir, args.execute)
    plan["provenance"]["inputs"].append(str(input_path))
    script_output.parent.mkdir(parents=True, exist_ok=True)
    script_output.write_text(script, encoding="utf-8", newline="\n")
    plan["artifacts"].append({"path": str(script_output), "kind": "bash_script"})
    plan["provenance"]["generated_files"].append(str(script_output))
    plan["provenance"]["generated_files"].append(str(output))
    write_json(output, plan)

    if args.execute and not plan["errors"]:
        completed = subprocess.run(["bash", str(script_output)], cwd=str(workdir), check=False)
        plan["data"]["returncode"] = completed.returncode
        if completed.returncode != 0:
            plan["status"] = "failure"
            plan["errors"].append(
                {
                    "type": "ExecutionFailure",
                    "message": f"submit script exited with code {completed.returncode}",
                }
            )
            plan["next_action"] = {
                "recommendation": "inspect_logs",
                "reason": "AdsorbDiff execution returned a non-zero exit code.",
            }
        else:
            plan["next_action"] = {
                "recommendation": "inspect_candidates",
                "reason": "AdsorbDiff execution completed; inspect sampled/relaxed structures.",
            }
        write_json(output, plan)

    print(json.dumps(plan, indent=2, sort_keys=True))
    return 1 if plan["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
