from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import require_safe_segment, require_under_trusted_roots, resolve_under, safe_relative_path


CLIENT_QUEUE_FIELDS = {"preset", "submit"}
QUEUE_PRESETS = {
    "auto",
    "preset48gam",
    "preset48std",
    "preset64gam",
    "preset64std",
    "presetg018gam",
    "presetg018std",
    "presetg01gam",
    "presetg01std",
}
TASK_TYPES = {"bulk", "slab", "freq", "static"}
SPEC_FIELDS = {
    "schema_version",
    "job_name",
    "task",
    "project",
    "job_dir",
    "overwrite",
    "structure",
    "vasp",
    "queue",
    "extends",
}
PROJECT_FIELDS = {"name", "job_dir", "overwrite", "root"}
STRUCTURE_FIELDS = {"format", "content", "path"}
VASP_FIELDS = {"xc", "kpts", "gamma", "parameters"}


def load_spec_text(text: str) -> dict[str, Any]:
    stripped = text.lstrip()
    if stripped.startswith("{"):
        data = json.loads(text)
    else:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise SystemExit("PyYAML is required: pip install pyyaml") from exc
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("job spec must be a mapping")
    return data


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(value, dict):
            merged[key] = deep_merge(base_value, value)
        else:
            merged[key] = value
    return merged


def merge_common_spec(common: dict[str, Any] | None, spec: dict[str, Any]) -> dict[str, Any]:
    if common is None:
        common = {}
    if not isinstance(common, dict):
        raise ValueError("common must be a mapping")
    if not isinstance(spec, dict):
        raise ValueError("spec must be a mapping")
    return deep_merge(common, spec)


def _strip_extends(spec: dict[str, Any]) -> dict[str, Any]:
    out = dict(spec)
    out.pop("extends", None)
    return out


def resolve_extends(
    spec: dict[str, Any],
    base_dir: str | Path,
    *,
    _seen: set[str] | None = None,
) -> dict[str, Any]:
    """Resolve a spec's in-file ``extends`` references into a single merged spec.

    ``extends`` is a relative path (or list of relative paths, resolved under
    ``base_dir``) to reusable common spec files. Precedence, weakest first:
    earlier ``extends`` entry < later ``extends`` entry < the spec itself. A
    referenced common file may itself use ``extends`` (resolved relative to its
    own directory); cycles raise an error.
    """
    if not isinstance(spec, dict):
        raise ValueError("spec must be a mapping")
    extends = spec.get("extends")
    if extends is None:
        return _strip_extends(spec)
    if isinstance(extends, str):
        extends = [extends]
    if not isinstance(extends, list) or not all(isinstance(item, str) for item in extends):
        raise ValueError("extends must be a string or a list of strings")

    base = Path(base_dir)
    seen = set(_seen or ())
    merged: dict[str, Any] = {}
    for rel in extends:
        rel_path = safe_relative_path(rel, "extends")
        target = resolve_under(base, rel_path)
        key = str(target)
        if key in seen:
            raise ValueError(f"circular extends reference: {target}")
        if not target.is_file():
            raise FileNotFoundError(f"extends file not found: {target}")
        loaded = load_spec_text(target.read_text(encoding="utf-8"))
        resolved_parent = resolve_extends(loaded, target.parent, _seen=seen | {key})
        merged = deep_merge(merged, resolved_parent)
    return deep_merge(merged, _strip_extends(spec))


def load_and_resolve_spec(
    spec: dict[str, Any],
    spec_base_dir: str | Path,
    *,
    common_path: str | Path | None = None,
) -> dict[str, Any]:
    """Apply reusable common parameters before normalization.

    Resolves the spec's own ``extends`` first, then overlays an optional external
    ``--common`` file (the weakest layer, so the job spec always wins). The
    returned mapping has no ``extends`` key and is ready for ``normalize_spec``.
    """
    resolved = resolve_extends(spec, spec_base_dir)
    if common_path is None:
        return resolved
    common_file = Path(common_path).expanduser()
    if not common_file.is_absolute():
        common_file = Path.cwd() / common_file
    common_file = common_file.resolve()
    if not common_file.is_file():
        raise FileNotFoundError(f"--common file not found: {common_file}")
    common = resolve_extends(
        load_spec_text(common_file.read_text(encoding="utf-8")),
        common_file.parent,
    )
    return merge_common_spec(common, resolved)


def reject_unknown_fields(data: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        fields = ", ".join(unknown)
        raise ValueError(f"unsupported {label} field(s): {fields}")


def require_bool(value: Any, field: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")


def normalize_spec(
    spec: dict[str, Any],
    config: dict[str, Any] | None = None,
    *,
    require_root: bool = True,
) -> dict[str, Any]:
    config = config or {}
    spec = dict(spec)
    # `extends` is resolved by load_and_resolve_spec before normalization; drop
    # any residual key so it is never written into the final job spec.
    spec.pop("extends", None)
    if "potcar" in spec:
        raise ValueError(
            "top-level potcar is not supported; configure POTCAR through "
            "vasp.xc, vasp.parameters.pp, vasp.parameters.setups, and the "
            "HPC vasp_pp_path setting"
        )
    reject_unknown_fields(spec, SPEC_FIELDS, "job spec")
    if "schema_version" not in spec:
        spec["schema_version"] = 1
    elif spec["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    job_name = spec.get("job_name")
    if not isinstance(job_name, str):
        raise ValueError("job_name must be a string")
    require_safe_segment(job_name, "job_name")
    spec["job_name"] = job_name

    task = spec.get("task")
    if task is not None:
        if not isinstance(task, str) or task not in TASK_TYPES:
            allowed = ", ".join(sorted(TASK_TYPES))
            raise ValueError(f"task must be one of: {allowed}")
        spec["task"] = task

    raw_project = spec.get("project")
    if isinstance(raw_project, str):
        project = {"name": raw_project}
    elif raw_project is None:
        project = {}
    elif isinstance(raw_project, dict):
        project = dict(raw_project)
    else:
        raise ValueError("project must be a string, mapping, or null")
    reject_unknown_fields(project, PROJECT_FIELDS, "project")

    if "root" in project:
        raise ValueError("project.root is managed by hpc-server config and must not be set in job specs")
    root = config.get("default_project_root")
    if require_root and not root:
        raise ValueError("default_project_root is required in server config")
    if root:
        project["root"] = root

    if project.get("name") is not None:
        if not isinstance(project["name"], str):
            raise ValueError("project.name must be a string")
        require_safe_segment(project["name"], "project.name")
    job_dir = spec.get("job_dir") or project.get("job_dir")
    if job_dir is not None:
        if not isinstance(job_dir, str):
            raise ValueError("job_dir must be a string")
        safe_relative_path(job_dir, "job_dir")
        project["job_dir"] = job_dir
    spec.pop("job_dir", None)
    overwrite = spec.pop("overwrite", project.get("overwrite", False))
    require_bool(overwrite, "overwrite")
    project["overwrite"] = overwrite
    spec["project"] = project

    raw_queue = spec.get("queue") or {}
    if not isinstance(raw_queue, dict):
        raise ValueError("queue must be a mapping")
    unsupported_queue_fields = sorted(set(raw_queue) - CLIENT_QUEUE_FIELDS)
    if unsupported_queue_fields:
        fields = ", ".join(unsupported_queue_fields)
        raise ValueError(
            f"queue.{fields} is managed by hpc-server presets/templates; "
            "job specs may set only queue.preset and queue.submit"
        )

    queue = dict(config.get("default_queue") or {})
    queue.update(raw_queue)
    if require_root:
        queue.setdefault("scheduler", "sge")
    queue.setdefault("submit", True)
    queue.pop("job_name", None)
    if "preset" in queue:
        preset = queue["preset"]
        if not isinstance(preset, str) or preset not in QUEUE_PRESETS:
            allowed = ", ".join(sorted(QUEUE_PRESETS))
            raise ValueError(f"queue.preset must be one of: {allowed}")
    require_bool(queue["submit"], "queue.submit")
    spec["queue"] = queue

    if "structure" not in spec:
        raise ValueError("structure is required")
    if not isinstance(spec["structure"], dict):
        raise ValueError("structure must be a mapping")
    reject_unknown_fields(spec["structure"], STRUCTURE_FIELDS, "structure")
    if spec["structure"].get("format") != "poscar":
        raise ValueError("structure.format must be poscar")
    has_content = "content" in spec["structure"]
    has_path = "path" in spec["structure"]
    if has_content == has_path:
        raise ValueError("structure must set exactly one of content or path")
    if has_content and not isinstance(spec["structure"].get("content"), str):
        raise ValueError("structure.content must be a string")
    if has_path:
        if not isinstance(spec["structure"].get("path"), str):
            raise ValueError("structure.path must be a string")
        safe_relative_path(spec["structure"]["path"], "structure.path")
    vasp = spec.get("vasp")
    if vasp is None:
        vasp = {}
    if not isinstance(vasp, dict):
        raise ValueError("vasp must be a mapping")
    reject_unknown_fields(vasp, VASP_FIELDS, "vasp")
    if "xc" in vasp and not isinstance(vasp["xc"], str):
        raise ValueError("vasp.xc must be a string")
    if "kpts" in vasp:
        kpts = vasp["kpts"]
        if (
            not isinstance(kpts, list)
            or len(kpts) != 3
            or not all(isinstance(item, int) for item in kpts)
        ):
            raise ValueError("vasp.kpts must be an integer array of length 3")
    if "gamma" in vasp:
        require_bool(vasp["gamma"], "vasp.gamma")
    if "parameters" in vasp and not isinstance(vasp["parameters"], dict):
        raise ValueError("vasp.parameters must be a mapping")
    # No server-side defaults: vasp.parameters is passed through to vasp-ase
    # exactly as the agent assembled it from the skill's defaults.yaml.
    spec["vasp"] = vasp
    return spec


def validated_job_dir(spec: dict[str, Any], trusted_roots: list[str | Path]) -> Path:
    project = spec["project"]
    root = Path(project["root"])
    parts = []
    if project.get("name"):
        parts.append(require_safe_segment(str(project["name"]), "project.name"))
    parts.append("jobs")
    parts.append(str(project["job_dir"]))
    rel = safe_relative_path("/".join(parts), "job_dir")
    target = resolve_under(root, rel)
    return require_under_trusted_roots(target, [Path(item) for item in trusted_roots])


def project_input_specs_dir(spec: dict[str, Any], trusted_roots: list[str | Path]) -> Path:
    project = spec["project"]
    root = Path(project["root"])
    parts = []
    if project.get("name"):
        parts.append(require_safe_segment(str(project["name"]), "project.name"))
    parts.append("input_specs")
    rel = safe_relative_path("/".join(parts), "project.input_specs")
    target = resolve_under(root, rel)
    return require_under_trusted_roots(target, [Path(item) for item in trusted_roots])


def spec_to_jsonable_result(**kwargs: Any) -> str:
    return json.dumps(kwargs, ensure_ascii=True, indent=2)
