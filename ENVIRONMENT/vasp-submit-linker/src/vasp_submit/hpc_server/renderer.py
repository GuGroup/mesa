from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any

from vasp_submit.common.config import dump_yaml
from vasp_submit.common.paths import require_safe_segment, resolve_under, safe_relative_path
from vasp_submit.common.spec import normalize_spec, project_input_specs_dir, validated_job_dir
from vasp_submit.hpc_server.jobs import now_iso


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def apply_vasp_ase_environment(spec: dict[str, Any], config: dict[str, Any]) -> None:
    for key, value in (config.get("vasp_ase_env") or {}).items():
        if value is not None:
            os.environ[str(key)] = str(value)
    if config.get("vasp_pp_path") is not None:
        os.environ["VASP_PP_PATH"] = str(Path(config["vasp_pp_path"]).expanduser())
    if config.get("vasp_pp_version") is not None:
        os.environ["VASP_PP_VERSION"] = str(config["vasp_pp_version"])


def write_vasp_inputs_with_vasp_ase(spec: dict[str, Any], config: dict[str, Any], directory: Path) -> None:
    try:
        from ase.io import read
        from vasp import Vasp
    except Exception as exc:
        raise RuntimeError("ase and vasp-ase are required on the HPC server") from exc

    apply_vasp_ase_environment(spec, config)
    atoms = read(directory / "POSCAR", format="vasp")
    vasp_spec = spec.get("vasp") or {}
    # parameters are passed straight to vasp-ase exactly as the spec provides
    # them (the agent assembles them from the skill's defaults.yaml).
    params = dict(vasp_spec.get("parameters") or {})
    for reserved in ("atoms", "directory", "label", "xc", "kpts", "gamma"):
        params.pop(reserved, None)
    calc_kwargs: dict[str, Any] = {"atoms": atoms, **params}
    if vasp_spec.get("xc"):
        calc_kwargs["xc"] = vasp_spec["xc"]
    if "kpts" in vasp_spec:
        calc_kwargs["kpts"] = tuple(vasp_spec["kpts"])
    if "gamma" in vasp_spec:
        calc_kwargs["gamma"] = bool(vasp_spec["gamma"])
    calc = Vasp(str(directory), **calc_kwargs)
    if not hasattr(calc, "write_input"):
        raise RuntimeError("vasp-ase Vasp calculator does not expose write_input")
    calc.write_input(atoms)

    required_files = ["INCAR", "POTCAR"]
    if "kpts" in vasp_spec or "kspacing" not in params:
        required_files.append("KPOINTS")
    missing = [name for name in required_files if not (directory / name).exists()]
    if missing:
        raise RuntimeError(f"vasp-ase did not generate required file(s): {', '.join(missing)}")


def parse_available_qq_nodes(output: str, config: dict[str, Any]) -> dict[int, list[str]]:
    auto = config.get("auto_preset") or {}
    ranges = auto.get("node_core_ranges") or {
        48: [[1, 30]],
        64: [[31, 40]],
    }
    available: dict[int, list[str]] = {}
    for line in output.splitlines():
        stripped = line.strip()
        match = re.match(r"^n(\d+)\s*$", stripped)
        if not match:
            continue
        node_number = int(match.group(1))
        node_name = f"n{node_number:02d}"
        for cores_raw, intervals in ranges.items():
            cores = int(cores_raw)
            for start, end in intervals:
                if int(start) <= node_number <= int(end):
                    available.setdefault(cores, []).append(node_name)
    return available


def queue_status_output(config: dict[str, Any]) -> str:
    command = str(config.get("queue_status_command") or "qq")
    # subprocess does no tilde expansion, so expand a leading ~ here; bare
    # command names (e.g. "qq") and absolute paths pass through unchanged.
    if command.startswith("~"):
        command = str(Path(command).expanduser())
    proc = subprocess.run(
        [command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{command} failed: {proc.stderr.strip()}")
    return proc.stdout


def auto_select_preset(spec: dict[str, Any], config: dict[str, Any]) -> str:
    vasp = spec.get("vasp") or {}
    binary = "gam" if bool(vasp.get("gamma", False)) and vasp.get("kpts") == [1, 1, 1] else "std"
    available = parse_available_qq_nodes(queue_status_output(config), config)
    prefer = (config.get("auto_preset") or {}).get("prefer") or [64, 48]
    for cores in prefer:
        core_count = int(cores)
        if available.get(core_count):
            return f"preset{core_count}{binary}"
    fallback = (config.get("auto_preset") or {}).get("fallback")
    if fallback:
        return str(fallback)
    raise RuntimeError("No free 48/64 nodes found from queue status output")


def template_search_roots(config: dict[str, Any]) -> list[Path]:
    roots: list[Path] = []
    if config.get("template_root"):
        roots.append(Path(config["template_root"]).expanduser())
    roots.append(Path.cwd())
    module_path = Path(__file__).resolve()
    for parent_index in (2, 3, 4):
        try:
            root = module_path.parents[parent_index]
        except IndexError:
            continue
        if root not in roots:
            roots.append(root)
    return roots


def resolve_submit_template(config: dict[str, Any], preset: str) -> Path:
    templates = config.get("submit_templates") or {}
    template_value = templates.get(preset)
    if not template_value:
        raise ValueError(f"Unknown queue.preset: {preset}")
    template_path = Path(template_value).expanduser()
    if template_path.is_absolute():
        if template_path.exists():
            return template_path
        raise FileNotFoundError(f"Submit template not found: {template_path}")
    for root in template_search_roots(config):
        candidate = root / template_path
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Submit template not found: {template_value}")


def render_template_submit_script(spec: dict[str, Any], config: dict[str, Any]) -> str:
    queue = spec.get("queue") or {}
    preset = queue.get("preset")
    if not preset:
        raise ValueError("queue.preset is required; submit scripts must use an approved HPC preset template")
    if preset == "auto":
        preset = auto_select_preset(spec, config)
        queue["preset"] = preset
    template_path = resolve_submit_template(config, str(preset))
    raw = template_path.read_text(encoding="utf-8")
    job_name = require_safe_segment(str(spec["job_name"]), "job_name")
    values = {
        "job_name": job_name,
        "name": spec["job_name"],
        "preset": str(preset),
    }
    for key, value in queue.items():
        if isinstance(value, (str, int, float, bool)):
            values[str(key)] = str(value)
    rendered = raw
    for key, value in values.items():
        rendered = rendered.replace("{{ " + key + " }}", str(value))
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return Template(rendered).safe_substitute(values)


def generated_job_dir(name: str, config: dict[str, Any]) -> str:
    # Default job_uid is a hyphen-free uuid token. `job_dir_pattern` may reweave
    # {uuid}/{name}/{timestamp}; {uuid4} stays as a backward-compatible alias.
    length = max(4, min(int(config.get("job_uid_length") or 10), 32))
    token = uuid.uuid4().hex[:length]
    pattern = config.get("job_dir_pattern") or "{uuid}"
    timestamp = datetime.now().strftime("%y%m%d_%H%M")
    return pattern.format(
        name=require_safe_segment(name, "name"),
        timestamp=timestamp,
        uuid=token,
        uuid4=token,
    )


def prepare_roots(spec: dict[str, Any], config: dict[str, Any]) -> tuple[Path, Path]:
    trusted_roots = config.get("trusted_roots") or [spec["project"]["root"]]
    input_specs_root = project_input_specs_dir(spec, trusted_roots)
    jobs_root = validated_job_dir(spec, trusted_roots).parent
    input_specs_root.mkdir(parents=True, exist_ok=True)
    jobs_root.mkdir(parents=True, exist_ok=True)
    return input_specs_root, jobs_root


def job_index_dir(spec: dict[str, Any], config: dict[str, Any]) -> Path:
    root = Path(spec["project"]["root"]).expanduser()
    trusted_roots = config.get("trusted_roots") or [spec["project"]["root"]]
    from vasp_submit.common.paths import require_under_trusted_roots

    path = require_under_trusted_roots(root / "job_index", [Path(item) for item in trusted_roots])
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_job_metadata(
    directory: Path,
    spec: dict[str, Any],
    config: dict[str, Any],
    input_spec_path: Path,
    scheduler_id: str | None = None,
) -> dict[str, Any]:
    job_uid = directory.name
    metadata_path = directory / ".vasp_submit_metadata.json"
    index_path = job_index_dir(spec, config) / f"{job_uid}.json"
    existing: dict[str, Any] = {}
    if metadata_path.exists():
        existing = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata = {
        **existing,
        "job_uid": job_uid,
        "job_name": spec["job_name"],
        "task": spec.get("task"),
        "project": (spec.get("project") or {}).get("name"),
        "remote_dir": str(directory),
        "input_spec": str(input_spec_path),
        "index_path": str(index_path),
        "preset": (spec.get("queue") or {}).get("preset"),
        "created_at": existing.get("created_at") or now_iso(),
        "state": existing.get("state") or "prepared",
    }
    if scheduler_id:
        metadata["scheduler_id"] = scheduler_id
    write_text(directory / ".vasp_submit_job_uid", job_uid)
    write_text(metadata_path, json.dumps(metadata, ensure_ascii=True, indent=2))
    write_text(index_path, json.dumps(metadata, ensure_ascii=True, indent=2))
    return metadata


def preserve_input_spec(spec: dict[str, Any], config: dict[str, Any], original_yaml: str, job_dir: str) -> Path:
    input_specs_root, _ = prepare_roots(spec, config)
    safe_relative_path(job_dir, "generated job_dir")
    path = input_specs_root / f"{job_dir}.yml"
    write_text(path, original_yaml)
    return path


def resolve_poscar_content(structure: dict[str, Any], spec_base_dir: Path) -> str:
    if structure.get("format") != "poscar":
        raise ValueError("MVP supports only structure.format: poscar")
    if "content" in structure:
        poscar = str(structure.get("content") or "")
        if not poscar.strip():
            raise ValueError("structure.content is empty")
        return poscar

    source = resolve_under(spec_base_dir, safe_relative_path(str(structure["path"]), "structure.path"))
    if not source.is_file():
        raise FileNotFoundError(f"structure.path not found: {source}")
    poscar = source.read_text(encoding="utf-8")
    if not poscar.strip():
        raise ValueError(f"structure.path is empty: {source}")
    return poscar


def prepare_job(
    spec: dict[str, Any],
    config: dict[str, Any],
    original_yaml: str | None = None,
    *,
    spec_base_dir: Path | None = None,
) -> Path:
    spec = normalize_spec(spec, config)
    if not spec["project"].get("job_dir"):
        spec["project"]["job_dir"] = generated_job_dir(str(spec["job_name"]), config)
    trusted_roots = config.get("trusted_roots") or [spec["project"]["root"]]
    directory = validated_job_dir(spec, trusted_roots)
    overwrite = bool(spec["project"].get("overwrite", False))
    if directory.exists() and any(directory.iterdir()) and not overwrite:
        raise FileExistsError(f"{directory} exists and is not empty; set project.overwrite: true")

    submit_script = render_template_submit_script(spec, config)
    directory.mkdir(parents=True, exist_ok=True)

    normalized_yaml = dump_yaml(spec)
    preserved_path = preserve_input_spec(spec, config, original_yaml or normalized_yaml, str(spec["project"]["job_dir"]))
    write_text(directory / "input.yml", normalized_yaml)
    write_text(directory / ".vasp_submit_input_spec", str(preserved_path))
    write_job_metadata(directory, spec, config, preserved_path)

    poscar = resolve_poscar_content(spec["structure"], spec_base_dir or Path.cwd())
    write_text(directory / "POSCAR", poscar)

    write_vasp_inputs_with_vasp_ase(spec, config, directory)

    submit_path = directory / "submit_vasp.sh"
    write_text(submit_path, submit_script)
    submit_path.chmod(0o755)
    return directory


def submit_job(directory: Path) -> dict[str, Any]:
    proc = subprocess.run(
        ["qsub", "submit_vasp.sh"],
        cwd=directory,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return {"ok": False, "returncode": proc.returncode, "stderr": proc.stderr.strip()}
    match = re.search(r"\b(\d+)\b", proc.stdout)
    scheduler_id = match.group(1) if match else None
    metadata_path = directory / ".vasp_submit_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    if scheduler_id:
        write_text(directory / ".vasp_submit_scheduler_id", scheduler_id)
        metadata["scheduler_id"] = scheduler_id
        metadata["state"] = "submitted"
        metadata["submitted_at"] = now_iso()
        write_text(metadata_path, json.dumps(metadata, ensure_ascii=True, indent=2))
        if metadata.get("index_path"):
            write_text(Path(metadata["index_path"]), json.dumps(metadata, ensure_ascii=True, indent=2))
    return {
        "ok": True,
        "job_uid": metadata.get("job_uid") or directory.name,
        "scheduler_id": scheduler_id,
        "stdout": proc.stdout.strip(),
        "remote_dir": str(directory),
    }
