#!/usr/bin/env python3
"""Controller for POSCAR-first AdsorbDiff placement workflows."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from poscar_to_adsorbdiff_input import estimate_vacuum_a, parse_poscar, prepare_poscar


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
DEFAULT_REPO = SKILL_DIR / "assets" / "AdsorbDiff"
DEFAULT_DB = DEFAULT_REPO / "adsorbdiff" / "placement" / "pkls" / "adsorbates.pkl"
TASK_ID = "place-adsorbates-with-adsorbdiff.poscar-controller"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("controller input must be a JSON object")
    return data


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def as_path(value: str | Path, base: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (base / path).resolve()


def adsorbate_args(adsorbate: dict[str, Any]) -> list[str]:
    args: list[str] = []
    if adsorbate.get("id") is not None:
        args.extend(["--adsorbate-id", str(adsorbate["id"])])
    elif adsorbate.get("smiles"):
        args.extend(["--smiles", str(adsorbate["smiles"])])
    elif adsorbate.get("formula"):
        args.extend(["--formula", str(adsorbate["formula"])])
    return args


def run_adsorbate_check(
    adsorbate: dict[str, Any],
    output_path: Path,
    repo: Path,
    db_path: Path,
    allow_ambiguous_select: bool,
) -> dict[str, Any]:
    if not adsorbate_args(adsorbate):
        result = {
            "status": "failure",
            "errors": [{"type": "MissingAdsorbate", "message": "Provide adsorbate.id, adsorbate.smiles, or adsorbate.formula."}],
            "data": {},
            "messages": [],
        }
        write_json(output_path, result)
        return result
    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "adsorbate_checker.py"),
        "--repo",
        str(repo),
        "--db-path",
        str(db_path),
        "--output",
        str(output_path),
    ]
    cmd.extend(adsorbate_args(adsorbate))
    if allow_ambiguous_select:
        cmd.append("--allow-ambiguous-select")
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if output_path.exists():
        return read_json(output_path)
    result = {
        "status": "failure",
        "errors": [{"type": "AdsorbateCheckerFailure", "message": completed.stderr.strip() or completed.stdout.strip()}],
        "data": {},
        "messages": [],
    }
    write_json(output_path, result)
    return result


def grouped_axis_positions(values: list[float], tolerance: float = 0.35) -> list[list[float]]:
    if not values:
        return []
    groups: list[list[float]] = [[values[0]]]
    for value in values[1:]:
        if abs(value - sum(groups[-1]) / len(groups[-1])) <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return groups


def group_centers(groups: list[list[float]]) -> list[float]:
    return [sum(group) / len(group) for group in groups]


def decide_surface_settings(poscar_path: Path, requested: dict[str, Any]) -> dict[str, Any]:
    parsed = parse_poscar(poscar_path)
    c_length = vec_norm(parsed["cell"][2])
    frac_z = [float(atom["frac"][2]) for atom in parsed["atoms"]]
    cart_z = sorted(value * c_length for value in frac_z)
    groups = grouped_axis_positions(cart_z)
    centers = group_centers(groups)
    vacuum_a = estimate_vacuum_a(parsed["atoms"], parsed["cell"])
    bottom_vacuum_a = max(0.0, min(frac_z) * c_length)
    top_vacuum_a = max(0.0, (1.0 - max(frac_z)) * c_length)
    reasons: list[str] = [
        f"estimated_vacuum_a={vacuum_a:.3f}",
        f"top_vacuum_a={top_vacuum_a:.3f}",
        f"bottom_vacuum_a={bottom_vacuum_a:.3f}",
    ]

    if requested.get("surface_side") is not None:
        surface_side = str(requested["surface_side"])
        reasons.append(f"user explicitly set surface_side={surface_side}")
    elif top_vacuum_a >= 3.0 and bottom_vacuum_a >= 3.0 and abs(top_vacuum_a - bottom_vacuum_a) <= 2.0:
        surface_side = "top"
        reasons.append("both sides look vacuum-exposed; using top as deterministic working side")
    elif bottom_vacuum_a > top_vacuum_a + 1.0:
        surface_side = "bottom"
        reasons.append("bottom side has the larger vacuum gap")
    else:
        surface_side = "top"
        reasons.append("top side has the larger or comparable vacuum gap")

    if requested.get("surface_thickness_a") is not None:
        surface_thickness_a = float(requested["surface_thickness_a"])
        reasons.append(f"user explicitly set surface_thickness_a={surface_thickness_a:.3f}")
    elif len(centers) >= 2:
        if surface_side == "bottom":
            layer_gap = centers[1] - centers[0]
        else:
            layer_gap = centers[-1] - centers[-2]
        surface_thickness_a = min(3.0, max(0.8, 0.8 * abs(layer_gap)))
        reasons.append(f"nearest_layer_gap_a={abs(layer_gap):.3f}")
        reasons.append(f"inferred_surface_thickness_a={surface_thickness_a:.3f}")
    else:
        surface_thickness_a = 2.0
        reasons.append("could not identify multiple slab layers; using conservative 2.0 A surface thickness")

    if requested.get("vacuum_min_a") is not None:
        vacuum_min_a = float(requested["vacuum_min_a"])
        reasons.append(f"user explicitly set vacuum_min_a={vacuum_min_a:.3f}")
    else:
        vacuum_min_a = 8.0
        reasons.append("using 8.0 A as vacuum warning threshold")

    write_selective_dynamics = bool(requested.get("write_selective_dynamics", True))
    if requested.get("write_selective_dynamics") is not None:
        reasons.append(f"user explicitly set write_selective_dynamics={write_selective_dynamics}")
    else:
        reasons.append("writing Selective Dynamics flags so frozen/mobile atoms are explicit")

    return {
        "surface_side": surface_side,
        "surface_thickness_a": surface_thickness_a,
        "vacuum_min_a": vacuum_min_a,
        "write_selective_dynamics": write_selective_dynamics,
        "estimated_vacuum_a": vacuum_a,
        "top_vacuum_a": top_vacuum_a,
        "bottom_vacuum_a": bottom_vacuum_a,
        "layer_centers_a": centers,
        "decision_reasons": reasons,
    }


def positive_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    parsed = int(value)
    if parsed < 1:
        raise ValueError(f"expected positive integer, got {value!r}")
    return parsed


def adsorption_orientation_count(selected: dict[str, Any] | None) -> tuple[int, int, int, list[str]]:
    selected = selected or {}
    reasons: list[str] = []
    n_atoms = positive_int(selected.get("n_atoms"), None)
    if n_atoms is None:
        symbols = selected.get("symbols")
        n_atoms = len(symbols) if isinstance(symbols, list) and symbols else 1
    binding_indices = selected.get("binding_indices") or []
    n_binding = len(binding_indices) if isinstance(binding_indices, list) else 0

    if n_atoms <= 1:
        orientations = 1
        reasons.append("single-atom adsorbate uses one orientation per site")
    elif n_atoms <= 3:
        orientations = 2
        reasons.append("small molecular adsorbate uses two orientations per site")
    else:
        orientations = 3
        reasons.append("larger molecular adsorbate uses three orientations per site")

    if n_binding > 1:
        orientations += 1
        reasons.append("multiple binding atoms add one orientation per site")

    return n_atoms, n_binding, min(orientations, 4), reasons


def vec_cross(left: list[float], right: list[float]) -> list[float]:
    return [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]


def vec_norm(vector: list[float]) -> float:
    return math.sqrt(sum(component * component for component in vector))


def estimate_surface_area(metadata: dict[str, Any]) -> float | None:
    cell = metadata.get("cell")
    if not isinstance(cell, list) or len(cell) < 2:
        return None
    try:
        a_vec = [float(component) for component in cell[0]]
        b_vec = [float(component) for component in cell[1]]
    except (TypeError, ValueError):
        return None
    return vec_norm(vec_cross(a_vec, b_vec))


def requested_candidate_target(requested: dict[str, Any]) -> tuple[int | None, list[str]]:
    reasons: list[str] = []
    for key in ("candidate_count", "target_candidates", "candidate_budget"):
        value = requested.get(key)
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            target = positive_int(value, None)
            reasons.append(f"user requested {key}={target}")
            return int(target), reasons
    reasons.append("no explicit candidate count; controller inferred count from POSCAR and adsorbate")
    return None, reasons


def infer_site_count(surface_count: int, surface_area_a2: float | None) -> tuple[int, list[str]]:
    reasons = [f"surface_atom_count={surface_count}"]
    if surface_area_a2 is not None:
        area_sites = max(1, math.ceil(surface_area_a2 / 10.0))
        reasons.append(f"surface_area_a2={surface_area_a2:.3f}")
        reasons.append(f"area_based_site_count={area_sites}")
    else:
        area_sites = surface_count
        reasons.append("surface_area unavailable; using atom-count based site estimate")

    if surface_count <= 4:
        topology_sites = surface_count * 2
        reasons.append("small surface: sampling extra bridge/hollow-like sites")
    elif surface_count <= 16:
        topology_sites = math.ceil(surface_count * 1.5)
        reasons.append("medium surface: sampling more sites than top atoms")
    else:
        topology_sites = surface_count
        reasons.append("large surface: one primary site per tagged surface atom")

    site_count = max(1, max(area_sites, topology_sites))
    reasons.append(f"inferred_site_count={site_count}")
    return site_count, reasons


def automatic_candidate_bounds(surface_count: int, n_atoms: int) -> tuple[int, int, list[str]]:
    min_candidates = max(4, min(surface_count, 8))
    if n_atoms <= 1:
        max_candidates = max(8, min(surface_count * 8, 64))
    elif n_atoms <= 3:
        max_candidates = max(16, min(surface_count * 12, 96))
    else:
        max_candidates = max(24, min(surface_count * 16, 128))
    return min_candidates, max_candidates, [
        f"automatic_min_candidates={min_candidates}",
        f"automatic_max_candidates={max_candidates}",
    ]


def decide_interstitial_gap(selected: dict[str, Any], requested: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    if requested.get("interstitial_gap") is not None:
        gap = float(requested["interstitial_gap"])
        reasons.append(f"user explicitly set interstitial_gap={gap:.3f}")
        return gap, reasons

    n_atoms, n_binding, _, _ = adsorption_orientation_count(selected)
    if n_atoms <= 1:
        gap = 0.10
        reasons.append("single-atom adsorbate: using tight 0.10 A interstitial gap")
    elif n_atoms <= 3:
        gap = 0.18
        reasons.append("small molecular adsorbate: using 0.18 A interstitial gap")
    else:
        gap = 0.25
        reasons.append("larger molecular adsorbate: using 0.25 A interstitial gap")

    if n_binding > 1:
        gap = max(gap, 0.15)
        reasons.append("multiple binding atoms: keeping gap at least 0.15 A")

    return gap, reasons


def decide_placement(poscar_result: dict[str, Any], adsorbate_result: dict[str, Any], requested: dict[str, Any]) -> dict[str, Any]:
    metadata = poscar_result.get("data", {})
    surface_count = int(metadata.get("surface", {}).get("surface_atom_count", 1) or 1)
    selected = adsorbate_result.get("data", {}).get("selected")
    has_binding = bool(selected and selected.get("binding_indices"))
    selected_adsorbate = selected if isinstance(selected, dict) else {}

    mode = requested.get("mode")
    if mode is None:
        mode = "random_site_heuristic_placement" if has_binding else "random"

    n_atoms, n_binding, inferred_augmentations, adsorbate_reasons = adsorption_orientation_count(selected_adsorbate)
    auto_min_candidates, auto_max_candidates, bound_reasons = automatic_candidate_bounds(surface_count, n_atoms)
    min_candidates = positive_int(requested.get("min_candidates"), auto_min_candidates) or auto_min_candidates
    max_candidates = positive_int(requested.get("max_candidates"), auto_max_candidates) or auto_max_candidates
    requested_target, target_reasons = requested_candidate_target(requested)
    surface_area_a2 = estimate_surface_area(metadata)
    inferred_sites, site_reasons = infer_site_count(surface_count, surface_area_a2)

    num_sites = requested.get("num_sites")
    num_augmentations = requested.get("num_augmentations_per_site")
    explicit_sites = num_sites is not None
    explicit_augmentations = num_augmentations is not None
    if explicit_sites:
        num_sites = positive_int(num_sites, 1)
    if explicit_augmentations:
        num_augmentations = positive_int(num_augmentations, 1)

    if not explicit_sites and not explicit_augmentations:
        num_augmentations = inferred_augmentations
        num_sites = inferred_sites
        if requested_target is not None:
            num_sites = max(1, math.ceil(requested_target / num_augmentations))
    elif explicit_sites and not explicit_augmentations:
        if inferred_augmentations <= 1:
            num_augmentations = 1
        else:
            target_for_orientation = requested_target or (int(num_sites) * inferred_augmentations)
            num_augmentations = max(1, math.ceil(target_for_orientation / int(num_sites)))
            num_augmentations = min(num_augmentations, inferred_augmentations)
    elif explicit_augmentations and not explicit_sites:
        if requested_target is None:
            num_sites = inferred_sites
        else:
            num_sites = max(1, math.ceil(requested_target / int(num_augmentations)))

    actual_candidates = int(num_sites) * int(num_augmentations)
    if actual_candidates > max_candidates and not explicit_sites:
        num_sites = max(1, max_candidates // int(num_augmentations))
        actual_candidates = int(num_sites) * int(num_augmentations)
    if actual_candidates < min_candidates and not explicit_sites:
        num_sites = max(int(num_sites), math.ceil(min_candidates / int(num_augmentations)))
        actual_candidates = int(num_sites) * int(num_augmentations)

    interstitial_gap, gap_reasons = decide_interstitial_gap(selected_adsorbate, requested)

    return {
        "mode": mode,
        "num_sites": int(num_sites),
        "num_augmentations_per_site": int(num_augmentations),
        "target_candidate_count": int(requested_target) if requested_target is not None else None,
        "actual_candidate_count": int(actual_candidates),
        "decision_strategy": "agent_auto" if requested_target is None else "user_candidate_target",
        "interstitial_gap": float(interstitial_gap),
        "adsorbate_complexity": {
            "n_atoms": int(n_atoms),
            "n_binding_indices": int(n_binding),
            "inferred_orientations_per_site": int(inferred_augmentations),
        },
        "decision_reasons": [
            *target_reasons,
            *bound_reasons,
            *site_reasons,
            *adsorbate_reasons,
            "selected heuristic-capable placement because AdsorbDiff DB provides binding indices"
            if has_binding
            else "selected random placement because binding indices were unavailable",
            "user explicitly set num_sites" if explicit_sites else "controller inferred num_sites",
            "user explicitly set num_augmentations_per_site" if explicit_augmentations else "controller inferred num_augmentations_per_site",
            *gap_reasons,
        ],
    }


def checkpoint_name(value: Any) -> str:
    if value is None:
        return ""
    return Path(str(value)).name.lower()


def infer_sampling_config(checkpoint: Any, requested_config: Any) -> tuple[str, list[str]]:
    if requested_config:
        return str(requested_config), [f"user explicitly set sampling config={requested_config}"]

    name = checkpoint_name(checkpoint)
    if "eqv2" in name and ("cond" in name or "fewshot" in name):
        config = "configs/denoising/eqv2_conditional.yml"
    elif "eqv2" in name:
        config = "configs/denoising/eqv2_so3.yml"
    elif "gemnet" in name:
        config = "configs/denoising/gemnet_so3.yml"
    else:
        config = "configs/denoising/painn_so3.yml"
    return config, [f"controller matched sampling config {config} from checkpoint name {name or '<auto>'}"]


def find_existing_checkpoint(name_or_path: Any, workdir: Path, base: Path, extra_dirs: list[Any] | None = None) -> tuple[Any, list[str]]:
    if name_or_path is None:
        return None, []
    checkpoint = Path(str(name_or_path)).expanduser()
    reasons: list[str] = []
    if checkpoint.is_absolute() and checkpoint.exists():
        return str(checkpoint), [f"checkpoint path exists: {checkpoint}"]
    if not checkpoint.is_absolute() and (base / checkpoint).exists():
        found = (base / checkpoint).resolve()
        return str(found), [f"resolved checkpoint relative to input file: {found}"]
    if not checkpoint.is_absolute() and (workdir / checkpoint).exists():
        found = (workdir / checkpoint).resolve()
        return str(found), [f"resolved checkpoint relative to workdir: {found}"]

    filename = checkpoint.name
    search_dirs: list[Path] = [
        workdir / "checkpoints",
        base / "checkpoints",
        Path.cwd() / "checkpoints",
        SKILL_DIR / "assets" / "checkpoints",
        DEFAULT_REPO / "checkpoints",
    ]
    if extra_dirs:
        if isinstance(extra_dirs, (str, os.PathLike)):
            search_dirs.append(Path(str(extra_dirs)).expanduser())
        else:
            search_dirs.extend(Path(str(item)).expanduser() for item in extra_dirs)

    for directory in search_dirs:
        candidate = directory / filename
        if candidate.exists():
            found = candidate.resolve()
            return str(found), [f"found checkpoint by name in {directory}: {found}"]

    runs_dir = Path.cwd() / "runs"
    if runs_dir.exists():
        matches = sorted(runs_dir.glob(f"*/checkpoints/{filename}"))
        if matches:
            found = matches[-1].resolve()
            return str(found), [f"found checkpoint by name under runs/*/checkpoints: {found}"]

    reasons.append(f"checkpoint {filename} was not found locally; workflow report will mark it as missing")
    return str(name_or_path), reasons


def stable_seed(input_path: Path, selected: dict[str, Any], placement: dict[str, Any], requested_seed: Any) -> tuple[int, list[str]]:
    if requested_seed is not None:
        seed = int(requested_seed)
        return seed, [f"user explicitly set seed={seed}"]

    payload = {
        "input_path": str(input_path.resolve()),
        "adsorbate_id": selected.get("id"),
        "smiles": selected.get("smiles"),
        "formula": selected.get("formula"),
        "candidate_count": placement.get("actual_candidate_count"),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    seed = int(digest[:8], 16) % 2_147_483_647
    return seed, [f"controller generated deterministic seed={seed} from POSCAR, adsorbate, and candidate count"]


def default_num_workers(requested: Any) -> tuple[int, list[str]]:
    if requested is not None:
        workers = int(requested)
        return max(1, workers), [f"user explicitly set num_workers={max(1, workers)}"]
    cpu_count = os.cpu_count() or 1
    workers = max(1, min(4, cpu_count))
    return workers, [f"controller set num_workers={workers} from available CPU count"]


def detect_torch_cuda_runtime() -> tuple[bool, list[str]]:
    try:
        import torch
    except Exception as exc:
        return True, [f"torch import failed during device auto-detect; selecting CPU ({exc})"]

    try:
        if not torch.cuda.is_available():
            return True, ["torch reports CUDA unavailable; selecting CPU"]
        capability = torch.cuda.get_device_capability(0)
        arch = f"sm_{capability[0]}{capability[1]}"
        arch_list = list(torch.cuda.get_arch_list())
        device_name = torch.cuda.get_device_name(0)
        if arch_list and arch not in arch_list:
            return True, [
                f"CUDA device {device_name} requires {arch}, but torch wheel supports {','.join(arch_list)}; selecting CPU"
            ]
        return False, [f"torch CUDA device {device_name} with {arch} is supported; selecting GPU"]
    except Exception as exc:
        return True, [f"CUDA auto-detect failed; selecting CPU ({exc})"]


def decide_runtime_settings(input_data: dict[str, Any], sampling: dict[str, Any]) -> dict[str, Any]:
    requested_device = str(input_data.get("device", sampling.get("device", "auto"))).lower()
    cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    reasons: list[str] = []

    if requested_device == "cpu":
        cpu = True
        reasons.append("user requested CPU execution")
    elif requested_device in {"cuda", "gpu"}:
        cpu = False
        reasons.append("user requested GPU execution")
    elif cuda_visible == "":
        cpu = True
        reasons.append("CUDA_VISIBLE_DEVICES is empty; selecting CPU execution")
    else:
        cpu, cuda_reasons = detect_torch_cuda_runtime()
        reasons.extend(cuda_reasons)

    ngpus = int(input_data.get("ngpus", sampling.get("ngpus", 1)))
    distributed = bool(input_data.get("distributed", ngpus > 1))
    amp = bool(input_data.get("amp", sampling.get("amp", not cpu)))
    debug = bool(input_data.get("debug", sampling.get("debug", True)))
    return {
        "cpu": cpu,
        "ngpus": ngpus,
        "distributed": distributed,
        "amp": amp,
        "debug": debug,
        "decision_reasons": reasons,
    }


def decide_sampling_settings(
    input_data: dict[str, Any],
    sampling: dict[str, Any],
    selected: dict[str, Any],
    placement: dict[str, Any],
    input_path: Path,
    workdir: Path,
) -> dict[str, Any]:
    reasons: list[str] = []
    if sampling.get("checkpoint") is None:
        checkpoint = "PT_zeroshot_painn.pt"
        reasons.append("controller selected PaiNN zero-shot diffusion checkpoint name for fast default inference")
    else:
        checkpoint = sampling["checkpoint"]
        reasons.append(f"user explicitly set sampling checkpoint={checkpoint}")

    checkpoint, checkpoint_reasons = find_existing_checkpoint(
        checkpoint,
        workdir,
        input_path.parent,
        input_data.get("checkpoint_dirs") or sampling.get("checkpoint_dirs"),
    )
    config_yml, config_reasons = infer_sampling_config(checkpoint, sampling.get("config_yml"))
    seed, seed_reasons = stable_seed(input_path, selected, placement, sampling.get("seed"))
    workers, worker_reasons = default_num_workers(sampling.get("num_workers"))
    runtime = decide_runtime_settings(input_data, sampling)

    if sampling.get("conversion_enabled") is None:
        conversion_enabled = True
        reasons.append("controller enabled trajectory-to-LMDB conversion for GemNet validation")
    else:
        conversion_enabled = bool(sampling["conversion_enabled"])
        reasons.append(f"user explicitly set conversion_enabled={conversion_enabled}")

    if sampling.get("relaxation_enabled") is None:
        relaxation_enabled = True
        reasons.append("controller enabled pretrained GemNet relaxation by default")
    else:
        relaxation_enabled = bool(sampling["relaxation_enabled"])
        reasons.append(f"user explicitly set relaxation_enabled={relaxation_enabled}")

    if sampling.get("relaxation_checkpoint") is None:
        relaxation_checkpoint = "gemnet_oc_base_s2ef_2M.pt"
        reasons.append("controller selected pretrained GemNet-OC base S2EF 2M checkpoint for validation")
    else:
        relaxation_checkpoint = sampling["relaxation_checkpoint"]
        reasons.append(f"user explicitly set relaxation checkpoint={relaxation_checkpoint}")

    if sampling.get("relaxation_config_yml") is None:
        relaxation_config = "configs/relaxation/gemnet_oc/gemnet_relax.yml"
        reasons.append("controller selected AdsorbDiff GemNet relaxation config")
    else:
        relaxation_config = sampling["relaxation_config_yml"]
        reasons.append(f"user explicitly set relaxation config={relaxation_config}")
    relaxation_checkpoint, relaxation_checkpoint_reasons = find_existing_checkpoint(
        relaxation_checkpoint,
        workdir,
        input_path.parent,
        input_data.get("checkpoint_dirs") or sampling.get("checkpoint_dirs"),
    )

    relaxation_extra = list(sampling.get("relaxation_extra_overrides") or [])
    if "--model.name=gemnet_oc_plain" not in relaxation_extra:
        relaxation_extra.append("--model.name=gemnet_oc_plain")
    if "--optim.num_workers=0" not in relaxation_extra:
        relaxation_extra.append("--optim.num_workers=0")
    if "--optim.batch_size=1" not in relaxation_extra:
        relaxation_extra.append("--optim.batch_size=1")
    if "--optim.eval_batch_size=1" not in relaxation_extra:
        relaxation_extra.append("--optim.eval_batch_size=1")
    if not any(str(item).startswith("--task.relaxation_steps=") for item in relaxation_extra):
        relaxation_extra.append("--task.relaxation_steps=300")
    if not any(str(item).startswith("--task.relaxation_fmax=") for item in relaxation_extra):
        relaxation_extra.append("--task.relaxation_fmax=0.01")

    return {
        "sampling": {
            "checkpoint": checkpoint,
            "config_yml": config_yml,
            "traj_dir": "samples/site0",
            "seed": seed,
        },
        "conversion": {
            "enabled": conversion_enabled,
            "converter": "skill",
            "out_path": "samples/site0/final_struct_lmdb",
            "num_workers": workers,
            "summary": "results/traj_to_lmdb_summary.json",
        },
        "relaxation": {
            "enabled": relaxation_enabled,
            "dataset_src": "samples/site0/final_struct_lmdb",
            "checkpoint": relaxation_checkpoint,
            "config_yml": relaxation_config,
            "traj_dir": "samples/site0/relaxations",
            "extra_overrides": relaxation_extra,
        },
        "runtime": runtime,
        "decision_reasons": [
            *reasons,
            *checkpoint_reasons,
            *config_reasons,
            *seed_reasons,
            *worker_reasons,
            *relaxation_checkpoint_reasons,
            *runtime["decision_reasons"],
        ],
    }


def decide_handoff_policy(placement: dict[str, Any], sampling_decision: dict[str, Any], requested: dict[str, Any]) -> dict[str, Any]:
    actual = int(placement.get("actual_candidate_count", 1) or 1)
    if requested.get("top_k") is not None:
        top_k = positive_int(requested.get("top_k"), 1) or 1
        reasons = [f"user explicitly set handoff.top_k={top_k}"]
    else:
        top_k = max(1, min(8, math.ceil(math.sqrt(actual))))
        reasons = [f"controller set handoff top_k={top_k} from sqrt(actual_candidate_count={actual})"]

    metric = requested.get("ranking_metric")
    if metric is None:
        metric = "gemnet_relaxed_energy" if sampling_decision["relaxation"]["enabled"] else "adsorbdiff_sample_order"
        reasons.append(f"controller selected ranking_metric={metric}")
    else:
        reasons.append(f"user explicitly set ranking_metric={metric}")

    return {
        "top_k": int(top_k),
        "ranking_metric": str(metric),
        "requires_gemnet_validation": bool(sampling_decision["relaxation"]["enabled"]),
        "decision_reasons": reasons,
    }


def build_controller(input_data: dict[str, Any], input_path: Path, execute_candidates: bool) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    messages: list[str] = []
    artifacts: list[dict[str, str]] = []

    base = input_path.parent
    workdir = as_path(input_data.get("workdir", "adsorbdiff_poscar_run"), base)
    results_dir = workdir / "results"
    repo = as_path(input_data.get("adsorbdiff_repo", str(DEFAULT_REPO)), SKILL_DIR)
    db_path = as_path(input_data.get("adsorbate_db", str(DEFAULT_DB)), SKILL_DIR)
    poscar_path = input_data.get("poscar_path")
    if not poscar_path:
        errors.append({"type": "MissingInput", "message": "poscar_path is required."})
        poscar_abs = workdir / "MISSING_POSCAR"
    else:
        poscar_abs = as_path(poscar_path, base)

    prepared_poscar = workdir / "adsorbdiff_slab" / "POSCAR"
    poscar_metadata = results_dir / "adsorbdiff_poscar_metadata.json"
    tags_output = results_dir / "adsorbdiff_tags.txt"
    surface = input_data.get("surface", {}) or {}
    if not errors:
        try:
            surface_decision = decide_surface_settings(poscar_abs, surface)
        except Exception as exc:  # noqa: BLE001 - keep controller output structured.
            surface_decision = {
                "surface_side": str(surface.get("surface_side", "top")),
                "surface_thickness_a": float(surface.get("surface_thickness_a", 2.0)),
                "vacuum_min_a": float(surface.get("vacuum_min_a", 8.0)),
                "write_selective_dynamics": bool(surface.get("write_selective_dynamics", True)),
                "decision_reasons": [
                    f"surface auto-detection failed before POSCAR preparation: {type(exc).__name__}: {exc}",
                    "falling back to conservative top/2.0 A/8.0 A settings so POSCAR prep can report structured errors",
                ],
            }
        poscar_result = prepare_poscar(
            input_poscar=poscar_abs,
            output_poscar=prepared_poscar,
            metadata_output=poscar_metadata,
            tags_output=tags_output,
            surface_thickness_a=float(surface_decision["surface_thickness_a"]),
            surface_side=str(surface_decision["surface_side"]),
            vacuum_min_a=float(surface_decision["vacuum_min_a"]),
            write_selective_dynamics=bool(surface_decision["write_selective_dynamics"]),
        )
        errors.extend(poscar_result.get("errors", []))
        messages.extend(poscar_result.get("messages", []))
        artifacts.extend(poscar_result.get("artifacts", []))
    else:
        surface_decision = {}
        poscar_result = {"status": "failure", "data": {}, "errors": errors}

    adsorbate = input_data.get("adsorbate", {}) or {}
    adsorbate_check_path = results_dir / "adsorbate_check.json"
    allow_agent_choice = bool(input_data.get("allow_agent_adsorbate_choice", True))
    adsorbate_result = run_adsorbate_check(
        adsorbate=adsorbate,
        output_path=adsorbate_check_path,
        repo=repo,
        db_path=db_path,
        allow_ambiguous_select=allow_agent_choice,
    )
    artifacts.append({"path": str(adsorbate_check_path), "kind": "adsorbate_check"})
    messages.extend(adsorbate_result.get("messages", []))
    allow_unverified = bool(input_data.get("allow_unverified_adsorbate", False))
    if adsorbate_result.get("errors") and not allow_unverified:
        errors.extend(adsorbate_result.get("errors", []))

    placement_requested = input_data.get("placement", {}) or {}
    for key in ("candidate_budget", "target_candidates", "max_candidates", "min_candidates"):
        if key in input_data and key not in placement_requested:
            placement_requested[key] = input_data[key]
    placement = decide_placement(poscar_result, adsorbate_result, placement_requested)
    candidates_dir = workdir / "adsorbdiff_candidates"
    candidate_lmdb = workdir / "candidate_lmdb"
    candidate_result_path = results_dir / "adsorbdiff_candidates.json"
    place_cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "adsorbdiff_place_candidates.py"),
        "--prepared-poscar",
        str(prepared_poscar),
        "--metadata",
        str(poscar_metadata),
        "--output-dir",
        str(candidates_dir),
        "--repo",
        str(repo),
        "--db-path",
        str(db_path),
        "--mode",
        placement["mode"],
        "--num-sites",
        str(placement["num_sites"]),
        "--num-augmentations-per-site",
        str(placement["num_augmentations_per_site"]),
        "--interstitial-gap",
        str(placement["interstitial_gap"]),
        "--lmdb-output",
        str(candidate_lmdb),
        "--output",
        str(candidate_result_path),
    ]
    selected = adsorbate_result.get("data", {}).get("selected")
    if isinstance(selected, dict) and selected.get("id") is not None:
        place_cmd.extend(["--adsorbate-id", str(selected["id"])])
    elif adsorbate.get("id") is not None:
        place_cmd.extend(["--adsorbate-id", str(adsorbate["id"])])
    elif adsorbate.get("smiles"):
        place_cmd.extend(["--smiles", str(adsorbate["smiles"])])

    candidate_execution = {"attempted": False, "result": None}
    if execute_candidates and not errors:
        completed = subprocess.run(place_cmd, capture_output=True, text=True, check=False)
        candidate_execution["attempted"] = True
        if candidate_result_path.exists():
            candidate_execution["result"] = read_json(candidate_result_path)
            errors.extend(candidate_execution["result"].get("errors", []))
        else:
            errors.append(
                {
                    "type": "CandidatePlacementFailure",
                    "message": completed.stderr.strip() or completed.stdout.strip(),
                }
            )

    sampling = input_data.get("sampling", {}) or {}
    selected_adsorbate = adsorbate_result.get("data", {}).get("selected")
    selected_adsorbate = selected_adsorbate if isinstance(selected_adsorbate, dict) else {}
    sampling_decision = decide_sampling_settings(input_data, sampling, selected_adsorbate, placement, input_path, workdir)
    handoff = decide_handoff_policy(placement, sampling_decision, input_data.get("handoff", {}) or {})
    runtime_decision = sampling_decision["runtime"]
    workflow_input = {
        "workdir": str(workdir / "adsorbdiff_sampling"),
        "python": sys.executable,
        "ngpus": int(runtime_decision["ngpus"]),
        "distributed": bool(runtime_decision["distributed"]),
        "cpu": bool(runtime_decision["cpu"]),
        "amp": bool(runtime_decision["amp"]),
        "debug": bool(runtime_decision["debug"]),
        "sampling": {
            "dataset_src": str(candidate_lmdb),
            **sampling_decision["sampling"],
        },
        "conversion": sampling_decision["conversion"],
        "relaxation": sampling_decision["relaxation"],
    }
    workflow_input_path = results_dir / "adsorbdiff_workflow.input.json"
    write_json(workflow_input_path, workflow_input)
    artifacts.append({"path": str(workflow_input_path), "kind": "workflow_input"})

    resolved = {
        "status": "failure" if errors else "success",
        "task_id": TASK_ID,
        "skill": "adsorbdiff_controller",
        "data": {
            "workdir": str(workdir),
            "surface_decision": surface_decision,
            "poscar_prepare": poscar_result.get("data", {}),
            "adsorbate_check": adsorbate_result.get("data", {}),
            "placement": placement,
            "sampling_decision": sampling_decision,
            "handoff": handoff,
            "candidate_command": place_cmd,
            "candidate_execution": candidate_execution,
            "workflow_input": str(workflow_input_path),
        },
        "artifacts": artifacts,
        "messages": messages,
        "errors": errors,
        "provenance": {
            "inputs": [str(input_path)],
            "generated_files": [item["path"] for item in artifacts],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "next_action": {
            "recommendation": "fix_inputs" if errors else "run_candidate_command",
            "reason": "Controller found blocking input issues." if errors else "POSCAR, adsorbate, and placement decisions are resolved.",
        },
    }
    resolved_path = results_dir / "resolved_adsorbdiff_config.json"
    resolved["artifacts"].append({"path": str(resolved_path), "kind": "resolved_config"})
    resolved["provenance"]["generated_files"].append(str(resolved_path))
    write_json(resolved_path, resolved)
    return resolved


def template() -> dict[str, Any]:
    return {
        "poscar_path": "POSCAR",
        "workdir": "runs/adsorbdiff_poscar_case",
        "adsorbate": {"smiles": "*CO"},
        "surface": {},
        "placement": {},
        "sampling": {},
        "handoff": {},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute-candidates", action="store_true")
    parser.add_argument("--print-template", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.print_template:
        print(json.dumps(template(), indent=2, sort_keys=True))
        return 0
    if args.input is None:
        raise SystemExit("--input is required unless --print-template is used")
    input_path = args.input.resolve()
    input_data = read_json(input_path)
    result = build_controller(input_data, input_path, execute_candidates=args.execute_candidates)
    if args.output:
        write_json(args.output.resolve(), result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
