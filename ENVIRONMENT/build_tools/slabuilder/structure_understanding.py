"""Read-only structure understanding packets for modeling agents.

The functions here summarize ASE structures into bounded, deterministic data
that an LLM can reason over without receiving a raw coordinate dump.
"""

from __future__ import annotations

from collections import Counter
import copy
import json
from typing import Any

import numpy as np
from ase import Atoms
from ase.constraints import FixAtoms
from ase.formula import Formula
from ase.neighborlist import NeighborList, natural_cutoffs

from slabuilder.adsorption import ADSORBATE_TAG, FIXED_SLAB_TAG, RELAXABLE_SLAB_TAG
from slabuilder.config import DEFAULT_BOND_HEIGHT
from slabuilder.site_map import build_site_map, site_map_to_jsonable
from slabuilder.structure_checks import check_min_distance


TAG_MEANING = {
    FIXED_SLAB_TAG: "fixed_slab",
    RELAXABLE_SLAB_TAG: "relaxable_slab",
    ADSORBATE_TAG: "adsorbate",
}


def cell_to_params(cell_matrix: Any) -> tuple[float, float, float, float, float, float]:
    """Return (a, b, c, alpha, beta, gamma) from a 3x3 row-vector cell matrix."""
    matrix = np.array(cell_matrix, dtype=float)
    a, b, c = (np.linalg.norm(matrix[i]) for i in range(3))
    alpha = float(np.degrees(np.arccos(np.clip(np.dot(matrix[1], matrix[2]) / (b * c), -1, 1))))
    beta = float(np.degrees(np.arccos(np.clip(np.dot(matrix[0], matrix[2]) / (a * c), -1, 1))))
    gamma = float(np.degrees(np.arccos(np.clip(np.dot(matrix[0], matrix[1]) / (a * b), -1, 1))))
    return float(a), float(b), float(c), alpha, beta, gamma


def composition_counts(atoms: Atoms) -> dict[str, int]:
    """Return element-count composition for an ASE Atoms object."""
    return dict(Counter(atoms.get_chemical_symbols()))


def _json_info(atoms: Atoms, key: str, *, default: Any = None) -> Any:
    raw = atoms.info.get(key)
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return default


def _bounded_indices(indices: list[int], *, max_indices: int) -> dict[str, Any]:
    values = [int(index) for index in indices]
    return {
        "count": len(values),
        "indices": values[:max_indices],
        "truncated": len(values) > max_indices,
    }


def _detect_z_layers(atoms: Atoms, *, gap: float = 0.8, max_indices: int = 80) -> list[dict[str, Any]]:
    layers = _z_layer_groups(atoms, gap=gap)
    if not layers:
        return []
    z = np.array(atoms.positions[:, 2], dtype=float)
    symbols = atoms.get_chemical_symbols()
    tags = atoms.get_tags() if "tags" in getattr(atoms, "arrays", {}) else None
    out: list[dict[str, Any]] = []
    for layer_id, layer_indices in enumerate(layers):
        z_values = [float(z[index]) for index in layer_indices]
        element_counts = Counter(symbols[index] for index in layer_indices)
        tag_counts = Counter(int(tags[index]) for index in layer_indices) if tags is not None else Counter()
        out.append({
            "id": layer_id,
            "z_min": min(z_values),
            "z_max": max(z_values),
            "z_mean": float(np.mean(z_values)),
            "n_atoms": len(layer_indices),
            "element_counts": dict(sorted(element_counts.items())),
            "tag_counts": {str(tag): int(count) for tag, count in sorted(tag_counts.items())},
            "atom_indices": _bounded_indices(layer_indices, max_indices=max_indices),
        })
    return out


def _z_layer_groups(atoms: Atoms, *, gap: float = 0.8) -> list[list[int]]:
    if len(atoms) == 0:
        return []
    z = np.array(atoms.positions[:, 2], dtype=float)
    order = np.argsort(z)
    layers: list[list[int]] = [[int(order[0])]]
    for idx in order[1:]:
        layer_z_min = z[layers[-1][0]]
        if float(z[idx] - layer_z_min) > gap:
            layers.append([int(idx)])
        else:
            layers[-1].append(int(idx))
    return layers


def _tag_summary(atoms: Atoms) -> dict[str, Any]:
    present = "tags" in getattr(atoms, "arrays", {})
    tags = atoms.get_tags()
    counts = Counter(int(tag) for tag in tags)
    return {
        "present": bool(present),
        "meaning": {str(key): value for key, value in TAG_MEANING.items()},
        "counts": {str(tag): int(count) for tag, count in sorted(counts.items())},
    }


def _magmom_summary(atoms: Atoms) -> dict[str, Any]:
    present = "initial_magmoms" in getattr(atoms, "arrays", {})
    if not present:
        return {"present": False}
    values = np.array(atoms.get_initial_magnetic_moments(), dtype=float)
    nonzero = int(np.sum(np.abs(values) > 1e-8))
    return {
        "present": True,
        "count": int(len(values)),
        "nonzero_count": nonzero,
        "min": float(np.min(values)) if len(values) else 0.0,
        "max": float(np.max(values)) if len(values) else 0.0,
        "sum": float(np.sum(values)) if len(values) else 0.0,
    }


def _adsorbate_groups(
    atoms: Atoms,
    *,
    record: dict[str, Any] | None,
    max_indices: int,
) -> list[dict[str, Any]]:
    metadata = (record or {}).get("adsorbate_metadata") or _json_info(atoms, "adsorbate_metadata_json", default={}) or {}
    indices = metadata.get("atom_indices")
    if not indices and "tags" in getattr(atoms, "arrays", {}):
        tags = atoms.get_tags()
        indices = np.where(tags == ADSORBATE_TAG)[0].astype(int).tolist()
    if not indices:
        return []
    valid = [int(index) for index in indices if 0 <= int(index) < len(atoms)]
    symbols = atoms.get_chemical_symbols()
    formula = metadata.get("formula")
    if not formula:
        formula = "".join(
            f"{el}{count if count > 1 else ''}"
            for el, count in sorted(Counter(symbols[index] for index in valid).items())
        )
    anchor_index = metadata.get("anchor_index")
    if anchor_index is None and valid:
        anchor_index = valid[0]
    return [{
        "formula": formula,
        "atom_indices": _bounded_indices(valid, max_indices=max_indices),
        "anchor_index": int(anchor_index) if anchor_index is not None else None,
        "metadata": metadata,
    }]


def _adsorbate_indices(
    atoms: Atoms,
    *,
    record: dict[str, Any] | None,
) -> list[int]:
    metadata = (record or {}).get("adsorbate_metadata") or _json_info(atoms, "adsorbate_metadata_json", default={}) or {}
    indices = metadata.get("atom_indices")
    if not indices and "tags" in getattr(atoms, "arrays", {}):
        tags = atoms.get_tags()
        indices = np.where(tags == ADSORBATE_TAG)[0].astype(int).tolist()
    return _valid_indices(atoms, indices or [])


def _valid_indices(atoms: Atoms, indices: list[int] | tuple[int, ...]) -> list[int]:
    valid: list[int] = []
    seen: set[int] = set()
    for raw in indices:
        try:
            index = int(raw)
        except Exception:
            continue
        if 0 <= index < len(atoms) and index not in seen:
            valid.append(index)
            seen.add(index)
    return valid


def _formula_for_indices(atoms: Atoms, indices: list[int] | tuple[int, ...]) -> str:
    symbols = atoms.get_chemical_symbols()
    counts = Counter(symbols[int(index)] for index in indices)
    return "".join(f"{el}{count if count > 1 else ''}" for el, count in sorted(counts.items()))


def _selection_candidate(
    atoms: Atoms,
    *,
    candidate_id: str,
    label: str,
    intent: str,
    indices: list[int],
    source: str,
    max_indices: int,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    valid = _valid_indices(atoms, indices)
    return {
        "id": candidate_id,
        "label": label,
        "intent": intent,
        "source": source,
        "count": len(valid),
        "formula": _formula_for_indices(atoms, valid),
        "atom_indices": _bounded_indices(valid, max_indices=max_indices),
        "warnings": warnings or [],
    }


def _site_summary(record: dict[str, Any] | None, atoms: Atoms) -> dict[str, Any]:
    source_site = (record or {}).get("source_site") or _json_info(atoms, "source_site_json", default=None)
    site_map = (record or {}).get("site_map") or {}
    sites = site_map.get("sites") if isinstance(site_map, dict) else None
    neighbors = site_map.get("neighbors") if isinstance(site_map, dict) else None
    site_types: dict[str, int] = {}
    if isinstance(sites, list):
        for site in sites:
            site_type = str(site.get("site_type") or "unknown") if isinstance(site, dict) else "unknown"
            site_types[site_type] = site_types.get(site_type, 0) + 1
    return {
        "source_site": source_site,
        "site_map": {
            "present": bool(isinstance(sites, list) and sites),
            "n_sites": len(sites) if isinstance(sites, list) else 0,
            "n_edges": len(neighbors) if isinstance(neighbors, list) else 0,
            "site_type_counts": dict(sorted(site_types.items())),
        },
    }


def _site_position(site: dict[str, Any] | None) -> np.ndarray | None:
    if not isinstance(site, dict):
        return None
    value = site.get("placed_position") or site.get("position")
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    try:
        return np.array(value[:3], dtype=float)
    except Exception:
        return None


def _site_surface_indices(site: dict[str, Any] | None) -> tuple[int, ...]:
    if not isinstance(site, dict):
        return ()
    raw = site.get("surface_atom_indices")
    if raw is None:
        raw = site.get("surface_atom_idx")
    if not isinstance(raw, (list, tuple)):
        return ()
    out: list[int] = []
    for value in raw:
        try:
            out.append(int(value))
        except Exception:
            continue
    return tuple(sorted(out))


def _mic_norm(atoms: Atoms, left: np.ndarray, right: np.ndarray) -> float:
    delta = np.array(left, dtype=float) - np.array(right, dtype=float)
    cell = np.array(atoms.get_cell(), dtype=float)
    if abs(np.linalg.det(cell)) > 1e-8:
        try:
            frac = np.linalg.solve(cell.T, delta)
            pbc = atoms.get_pbc()
            for axis in range(3):
                if pbc[axis]:
                    frac[axis] -= np.round(frac[axis])
            delta = frac @ cell
        except Exception:
            pass
    return float(np.linalg.norm(delta))


def _mic_lateral_norm(atoms: Atoms, left: np.ndarray, right: np.ndarray) -> float:
    projected = np.array(left, dtype=float)
    target = np.array(right, dtype=float)
    projected[2] = target[2]
    return _mic_norm(atoms, projected, target)


def _slab_atom_count_for_sites(atoms: Atoms, record: dict[str, Any]) -> tuple[int, list[str]]:
    warnings: list[str] = []
    raw_count = record.get("slab_atom_count") or atoms.info.get("slab_atom_count")
    if raw_count is not None:
        try:
            count = int(raw_count)
            if 0 < count <= len(atoms):
                return count, warnings
        except Exception:
            warnings.append("invalid slab_atom_count metadata ignored")
    ads_indices = _adsorbate_indices(atoms, record=record)
    if ads_indices:
        count = min(ads_indices)
        if count > 0:
            return int(count), warnings
    return len(atoms), warnings


def _slab_atoms_for_sites(
    atoms: Atoms,
    record: dict[str, Any],
    *,
    preserve_pbc: bool = False,
) -> tuple[Atoms, list[str], list[int]]:
    warnings: list[str] = []
    raw_indices = record.get("slab_atom_indices")
    if isinstance(raw_indices, (list, tuple)):
        indices = _valid_indices(atoms, raw_indices)
        if indices:
            slab = atoms[indices].copy()
            if not preserve_pbc:
                slab.set_pbc([True, True, False])
            return slab, warnings, indices
        warnings.append("invalid slab_atom_indices metadata ignored")
    n_slab, count_warnings = _slab_atom_count_for_sites(atoms, record)
    warnings.extend(count_warnings)
    slab = atoms[:n_slab].copy()
    if not preserve_pbc:
        slab.set_pbc([True, True, False])
    return slab, warnings, list(range(n_slab))


def _normalize_site(site: dict[str, Any], index: int) -> dict[str, Any]:
    normalized = dict(site)
    normalized.setdefault("id", f"site:{index}")
    normalized.setdefault("site_type", "unknown")
    normalized.setdefault("position", [0.0, 0.0, 0.0])
    normalized.setdefault("surface_atom_indices", [])
    normalized.setdefault("sources", [])
    if "validation_score" not in normalized:
        normalized["validation_score"] = 0.0
    return normalized


def _remap_weighted_site_map_indices(
    site_map: dict[str, Any],
    subset_to_original: list[int],
) -> dict[str, Any]:
    remapped = copy.deepcopy(site_map)

    def original_index(local_index: Any) -> int:
        if isinstance(local_index, bool) or not isinstance(local_index, int):
            raise ValueError(f"weighted-alpha site index is not an int: {local_index!r}")
        if not 0 <= local_index < len(subset_to_original):
            raise ValueError(f"weighted-alpha site index is out of subset range: {local_index}")
        return int(subset_to_original[local_index])

    for site in remapped.get("sites") or []:
        if not isinstance(site, dict):
            continue
        site["surface_atom_indices"] = [
            original_index(index) for index in site.get("surface_atom_indices") or []
        ]
        metadata = site.get("metadata")
        weighted = metadata.get("weighted_alpha") if isinstance(metadata, dict) else None
        if not isinstance(weighted, dict):
            continue
        image_containers = [weighted]
        candidate = weighted.get("candidate")
        if isinstance(candidate, dict):
            image_containers.append(candidate)
        for container in image_containers:
            for image in container.get("source_atom_images") or []:
                if isinstance(image, dict) and "ase_atom_index" in image:
                    image["ase_atom_index"] = original_index(image["ase_atom_index"])
        run = weighted.get("run")
        if isinstance(run, dict):
            local_engine_map = run.get("engine_to_ase_index")
            if isinstance(local_engine_map, list):
                run["engine_to_original_ase_index"] = [
                    original_index(index) for index in local_engine_map
                ]
            run["subset_to_original_ase_index"] = list(subset_to_original)
    top_metadata = remapped.get("metadata")
    top_run = (
        top_metadata.get("weighted_alpha_run")
        if isinstance(top_metadata, dict)
        else None
    )
    if isinstance(top_run, dict):
        local_engine_map = top_run.get("engine_to_ase_index")
        if isinstance(local_engine_map, list):
            top_run["engine_to_original_ase_index"] = [
                original_index(index) for index in local_engine_map
            ]
        top_run["subset_to_original_ase_index"] = list(subset_to_original)
    return remapped


def _filter_site_neighbors(
    neighbors: list[dict[str, Any]],
    *,
    max_site_distance: float,
    neighbor_shell: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for edge in neighbors:
        if not isinstance(edge, dict):
            continue
        try:
            distance = float(edge.get("distance", 0.0))
            shell = int(edge.get("shell", 1))
        except Exception:
            continue
        if distance <= float(max_site_distance) and shell <= int(neighbor_shell):
            out.append({
                "source_site_id": str(edge.get("source_site_id")),
                "target_site_id": str(edge.get("target_site_id")),
                "distance": distance,
                "shell": shell,
            })
    out.sort(key=lambda item: (item["shell"], item["distance"], item["source_site_id"], item["target_site_id"]))
    return out


def _nearest_site(
    atoms: Atoms,
    sites: list[dict[str, Any]],
    position: np.ndarray | None,
) -> dict[str, Any] | None:
    if position is None or not sites:
        return None
    best: tuple[float, dict[str, Any]] | None = None

    for site in sites:
        site_pos = _site_position(site)
        if site_pos is None:
            continue
        distance = _mic_norm(atoms, position, site_pos)
        if best is None or distance < best[0]:
            best = (distance, site)
    if best is None:
        return None
    site = dict(best[1])
    site["match_distance"] = float(best[0])
    return site


def _match_source_site_to_site_map(
    atoms: Atoms,
    sites: list[dict[str, Any]],
    source_site: dict[str, Any] | None,
    *,
    max_position_match_distance: float = 1.25,
) -> tuple[dict[str, Any], float, str] | None:
    if not isinstance(source_site, dict) or not sites:
        return None

    source_id = source_site.get("id")
    if source_id is not None:
        for site in sites:
            if str(site.get("id")) == str(source_id):
                position = _site_position(source_site)
                site_position = _site_position(site)
                distance = (
                    _mic_norm(atoms, position, site_position)
                    if position is not None and site_position is not None
                    else 0.0
                )
                return site, float(distance), "id"

    source_type = str(source_site.get("site_type") or "")
    source_indices = _site_surface_indices(source_site)
    source_position = _site_position(source_site)

    indexed_candidates: list[tuple[int, float, str, dict[str, Any]]] = []
    if source_indices:
        for site in sites:
            site_indices = _site_surface_indices(site)
            if not site_indices or site_indices != source_indices:
                continue
            type_penalty = 0 if str(site.get("site_type") or "") == source_type else 1
            site_position = _site_position(site)
            distance = (
                _mic_norm(atoms, source_position, site_position)
                if source_position is not None and site_position is not None
                else 0.0
            )
            indexed_candidates.append((type_penalty, float(distance), str(site.get("id")), site))
        if indexed_candidates:
            type_penalty, distance, _, site = min(indexed_candidates, key=lambda item: item[:3])
            method = "surface_atom_indices" if type_penalty == 0 else "surface_atom_indices_type_mismatch"
            return site, float(distance), method

    if source_type and source_position is not None:
        typed_candidates: list[tuple[float, str, dict[str, Any]]] = []
        for site in sites:
            if str(site.get("site_type") or "") != source_type:
                continue
            site_position = _site_position(site)
            if site_position is None:
                continue
            typed_candidates.append((
                float(_mic_norm(atoms, source_position, site_position)),
                str(site.get("id")),
                site,
            ))
        if typed_candidates:
            distance, _, site = min(typed_candidates, key=lambda item: item[:2])
            if distance > float(max_position_match_distance):
                return None
            return site, float(distance), "site_type_position"

    return None


def _current_site_from_source_site(
    atoms: Atoms,
    sites: list[dict[str, Any]],
    source_site: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(source_site, dict):
        return None

    current = dict(source_site)
    if "position" not in current or current.get("position") is None:
        current["position"] = [0.0, 0.0, 0.0]
    if "placed_position" in current and current.get("placed_position") is not None:
        current.setdefault("source_position", current.get("position"))
        current["position"] = current.get("placed_position")
    current.setdefault("site_type", "unknown")
    current.setdefault("surface_atom_indices", list(_site_surface_indices(current)))
    current.setdefault("sources", [])
    if "validation_score" not in current:
        current["validation_score"] = 0.0

    match = _match_source_site_to_site_map(atoms, sites, source_site)
    if match is not None:
        site, distance, method = match
        if site.get("id") is not None:
            current["id"] = str(site.get("id"))
            current["site_map_id"] = str(site.get("id"))
        current["site_map_site_type"] = str(site.get("site_type") or "unknown")
        current["site_map_match_distance"] = float(distance)
        current["site_map_match_method"] = method
    else:
        current.setdefault("id", "source_site")

    current["source"] = "metadata"
    current["match_distance"] = 0.0
    return current


def _anchor_position_for_sites(atoms: Atoms, record: dict[str, Any]) -> np.ndarray | None:
    ads_meta = record.get("adsorbate_metadata") or _json_info(atoms, "adsorbate_metadata_json", default=None)
    if isinstance(ads_meta, dict):
        anchor = ads_meta.get("anchor_index")
        if anchor is not None:
            try:
                index = int(anchor)
                if 0 <= index < len(atoms):
                    return np.array(atoms.positions[index], dtype=float)
            except Exception:
                pass
    ads_indices = _adsorbate_indices(atoms, record=record)
    if ads_indices:
        return np.array(atoms.positions[ads_indices[0]], dtype=float)
    return None


def analyze_surface_sites_packet(
    atoms: Atoms,
    *,
    record: dict[str, Any] | None = None,
    structure_id: str | None = None,
    backend: str = "acat",
    target_adsorbate: str = "H",
    max_site_distance: float = 3.5,
    neighbor_shell: int = 2,
    max_sites: int = 120,
    max_edges: int = 240,
    weighted_alpha_config: object | None = None,
) -> dict[str, Any]:
    """Return a read-only surface-site graph packet for a saved structure."""
    record = record or {}
    warnings: list[str] = []
    backend_name = str(backend or "acat").strip().lower()

    source = "rebuilt"
    raw_site_map = record.get("site_map") or _json_info(atoms, "site_map_json", default=None)
    subset_to_original = list(range(len(atoms)))
    raw_subset = record.get("slab_atom_indices")
    if isinstance(raw_subset, (list, tuple)):
        valid_subset = _valid_indices(atoms, raw_subset)
        if valid_subset:
            subset_to_original = valid_subset
    cached_map_allowed = backend_name != "weighted_alpha"
    if (
        cached_map_allowed
        and isinstance(raw_site_map, dict)
        and isinstance(raw_site_map.get("sites"), list)
        and raw_site_map.get("sites")
    ):
        source = "metadata"
        site_map = raw_site_map
    else:
        slab, slab_warnings, subset_to_original = _slab_atoms_for_sites(
            atoms,
            record,
            preserve_pbc=backend_name == "weighted_alpha",
        )
        warnings.extend(slab_warnings)
        try:
            site_map = site_map_to_jsonable(
                build_site_map(
                    slab,
                    target_adsorbate=target_adsorbate or "H",
                    max_site_distance=max_site_distance,
                    backend=backend_name,
                    weighted_alpha_config=weighted_alpha_config,
                )
            )
            if backend_name == "weighted_alpha":
                site_map = _remap_weighted_site_map_indices(
                    site_map, subset_to_original
                )
        except Exception as exc:
            if backend_name == "weighted_alpha":
                raise
            site_map = {"sites": [], "neighbors": []}
            warnings.append(f"site detection failed: {exc}")
    sites = [
        _normalize_site(site, i)
        for i, site in enumerate(site_map.get("sites") or [])
        if isinstance(site, dict)
    ]
    neighbors = _filter_site_neighbors(
        [edge for edge in (site_map.get("neighbors") or []) if isinstance(edge, dict)],
        max_site_distance=max_site_distance,
        neighbor_shell=neighbor_shell,
    )
    source_site = record.get("source_site") or _json_info(atoms, "source_site_json", default=None)
    current_site = _current_site_from_source_site(atoms, sites, source_site)
    if current_site is None:
        current_site = _nearest_site(atoms, sites, _anchor_position_for_sites(atoms, record))

    site_type_counts = Counter(str(site.get("site_type") or "unknown") for site in sites)
    result = {
        "structure_id": structure_id or record.get("id") or record.get("structure_id"),
        "source": source,
        "backend": "metadata" if source == "metadata" else backend_name,
        "backend_requested": backend_name,
        "target_adsorbate": target_adsorbate,
        "source_site": source_site,
        "current_site": current_site,
        "site_type_counts": dict(sorted(site_type_counts.items())),
        "n_sites": len(sites),
        "n_edges": len(neighbors),
        "sites": sites[:max_sites],
        "sites_truncated": len(sites) > max_sites,
        "neighbors": neighbors[:max_edges],
        "neighbors_truncated": len(neighbors) > max_edges,
        "max_site_distance": float(max_site_distance),
        "neighbor_shell": int(neighbor_shell),
        "warnings": warnings,
    }
    if backend_name == "weighted_alpha":
        result["slab_atom_indices"] = list(subset_to_original)
        result["site_map_metadata"] = copy.deepcopy(site_map.get("metadata") or {})
    return result


def _formula_counts_from_text(value: str | None) -> dict[str, int] | None:
    if not value:
        return None
    token = str(value).strip()
    if not token:
        return None
    try:
        return {str(k): int(v) for k, v in Formula(token).count().items()}
    except Exception:
        return None


def _invalid_formula_warning(field: str, value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    if _formula_counts_from_text(value) is None:
        return f"invalid {field} formula {value!r}"
    return None


def _indices_counts(atoms: Atoms, indices: list[int] | tuple[int, ...]) -> dict[str, int]:
    counts = Counter(atoms[int(index)].symbol for index in indices)
    return {str(k): int(v) for k, v in counts.items()}


def _site_by_id(sites: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(site.get("id")): site for site in sites if site.get("id") is not None}


def _distance_shell(distance: float, shells: list[float], *, tolerance: float = 0.25) -> int:
    for index, existing in enumerate(shells, start=1):
        if abs(float(distance) - existing) <= float(tolerance):
            return index
    shells.append(float(distance))
    return len(shells)


def _neighbor_site_targets(
    site_packet: dict[str, Any],
    *,
    source_site: dict[str, Any] | None = None,
    atoms: Atoms | None = None,
) -> list[tuple[dict[str, Any], float, int]]:
    current = source_site if source_site is not None else site_packet.get("current_site")
    current_id = str(current.get("id")) if isinstance(current, dict) and current.get("id") is not None else ""
    if not isinstance(current, dict):
        return []
    by_id = _site_by_id(site_packet.get("sites") or [])
    targets: list[tuple[dict[str, Any], float, int]] = []
    seen: set[str] = set()
    if current_id:
        for edge in site_packet.get("neighbors") or []:
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("source_site_id"))
            target = str(edge.get("target_site_id"))
            if source == current_id:
                target_id = target
            elif target == current_id:
                target_id = source
            else:
                continue
            site = by_id.get(target_id)
            if site is None or target_id in seen:
                continue
            seen.add(target_id)
            try:
                distance = float(edge.get("distance", 0.0))
                shell = int(edge.get("shell", 1))
            except Exception:
                distance = 0.0
                shell = 1
            targets.append((site, distance, shell))
    if targets:
        targets.sort(key=lambda item: (item[2], item[1], str(item[0].get("id"))))
        return targets

    current_position = _site_position(current)
    if not isinstance(atoms, Atoms) or current_position is None:
        return []
    max_site_distance = float(site_packet.get("max_site_distance") or 3.5)
    neighbor_shell = int(site_packet.get("neighbor_shell") or 2)
    current_indices = _site_surface_indices(current)
    current_type = str(current.get("site_type") or "")
    spatial: list[tuple[float, str, dict[str, Any]]] = []
    for site in site_packet.get("sites") or []:
        if not isinstance(site, dict):
            continue
        site_id = str(site.get("id")) if site.get("id") is not None else ""
        if current_id and site_id == current_id:
            continue
        site_indices = _site_surface_indices(site)
        if current_indices and site_indices == current_indices and str(site.get("site_type") or "") == current_type:
            continue
        site_position = _site_position(site)
        if site_position is None:
            continue
        distance = _mic_norm(atoms, current_position, site_position)
        if 0.35 < distance <= max_site_distance:
            spatial.append((float(distance), site_id, site))
    spatial.sort(key=lambda item: (item[0], item[1]))
    shells: list[float] = []
    for distance, _, site in spatial:
        shell = _distance_shell(distance, shells)
        if shell <= neighbor_shell:
            targets.append((site, float(distance), int(shell)))
    return targets


def _adsorbate_bond_pairs(
    atoms: Atoms,
    indices: list[int],
    *,
    cutoff_scale: float = 1.15,
) -> list[tuple[int, int]]:
    if len(indices) < 2:
        return []
    subset = atoms[indices].copy()
    subset.set_pbc(False)
    cutoffs = [float(value) * float(cutoff_scale) for value in natural_cutoffs(subset)]
    nl = NeighborList(cutoffs, self_interaction=False, bothways=True)
    nl.update(subset)
    bonds: set[tuple[int, int]] = set()
    for local_i, global_i in enumerate(indices):
        local_neighbors, _ = nl.get_neighbors(local_i)
        for local_j in local_neighbors:
            global_j = indices[int(local_j)]
            if int(global_i) != int(global_j):
                bonds.add(tuple(sorted((int(global_i), int(global_j)))))
    return _prune_terminal_terminal_bonds(atoms, sorted(bonds))


def _prune_terminal_terminal_bonds(atoms: Atoms, bonds: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Remove spurious terminal-terminal bonds induced by covalent cutoffs."""
    normalized = {tuple(sorted((int(a), int(b)))) for a, b in bonds}
    pruned: list[tuple[int, int]] = []
    for a, b in sorted(normalized):
        if atoms[a].symbol != atoms[b].symbol:
            pruned.append((a, b))
            continue
        remove = False
        for center in range(len(atoms)):
            if center in {a, b}:
                continue
            if atoms[center].symbol == atoms[a].symbol:
                continue
            if tuple(sorted((a, center))) in normalized and tuple(sorted((b, center))) in normalized:
                remove = True
                break
        if not remove:
            pruned.append((a, b))
    return pruned


def _components_after_removing_bond_readonly(
    nodes: list[int],
    bonds: list[tuple[int, int]],
    removed: tuple[int, int],
) -> list[list[int]]:
    graph: dict[int, set[int]] = {int(node): set() for node in nodes}
    removed_key = tuple(sorted(removed))
    for i, j in bonds:
        if tuple(sorted((i, j))) == removed_key:
            continue
        graph[int(i)].add(int(j))
        graph[int(j)].add(int(i))
    components: list[list[int]] = []
    seen: set[int] = set()
    for node in nodes:
        if node in seen:
            continue
        stack = [int(node)]
        seen.add(int(node))
        component: list[int] = []
        while stack:
            current = stack.pop()
            component.append(current)
            for nxt in sorted(graph[current]):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        components.append(sorted(component))
    return components


def _fragment_anchor_candidates(
    atoms: Atoms,
    indices: list[int],
    fragment_formula: str | None,
) -> list[int]:
    if not indices:
        return []
    candidates = [int(index) for index in indices]
    counts = _formula_counts_from_text(fragment_formula)
    if counts:
        non_h_symbols = [symbol for symbol in counts if symbol != "H"]
        preferred = [index for index in candidates if atoms[index].symbol in non_h_symbols]
        if preferred:
            candidates = preferred
    return candidates


def _fragment_current_site(
    atoms: Atoms,
    indices: list[int],
    sites: list[dict[str, Any]],
    fragment_formula: str | None,
) -> tuple[int | None, dict[str, Any] | None, float]:
    candidates = _fragment_anchor_candidates(atoms, indices, fragment_formula)
    if not candidates or not sites:
        return None, None, float("inf")
    ranked: list[tuple[float, float, int, str, int, dict[str, Any]]] = []
    for index in candidates:
        position = np.array(atoms.positions[int(index)], dtype=float)
        best_site: tuple[float, float, int, str, dict[str, Any]] | None = None
        for site in sites:
            site_position = _site_position(site)
            if site_position is None:
                continue
            lateral = _mic_lateral_norm(atoms, position, site_position)
            full = _mic_norm(atoms, position, site_position)
            priority = int(site.get("priority", 99) or 99)
            site_id = str(site.get("id", ""))
            if best_site is None or (lateral, full, priority, site_id) < best_site[:4]:
                best_site = (lateral, full, priority, site_id, site)
        if best_site is not None:
            lateral, full, priority, site_id, site = best_site
            ranked.append((lateral, full, priority, site_id, int(index), site))
    if not ranked:
        return None, None, float("inf")
    ranked.sort(key=lambda item: item[:5])
    lateral, full, _, _, anchor, site = ranked[0]
    matched = dict(site)
    matched["match_distance"] = float(full)
    matched["lateral_match_distance"] = float(lateral)
    return int(anchor), matched, float(lateral)


def _cleavage_proposals(
    atoms: Atoms,
    ads_indices: list[int],
    *,
    moving_fragment: str,
    remaining_fragment: str | None,
    break_bond: list[str] | tuple[str, ...] | None,
) -> list[dict[str, Any]]:
    bonds = _adsorbate_bond_pairs(atoms, ads_indices)
    moving_counts = _formula_counts_from_text(moving_fragment)
    remaining_counts = _formula_counts_from_text(remaining_fragment)
    break_symbols = tuple(sorted(str(v) for v in break_bond)) if break_bond else None
    out: list[dict[str, Any]] = []
    for bond in bonds:
        symbols = tuple(sorted((atoms[bond[0]].symbol, atoms[bond[1]].symbol)))
        if break_symbols is not None and symbols != break_symbols:
            continue
        components = _components_after_removing_bond_readonly(ads_indices, bonds, bond)
        if len(components) != 2:
            continue
        for moving, remaining in ((components[0], components[1]), (components[1], components[0])):
            if moving_counts is not None and _indices_counts(atoms, moving) != moving_counts:
                continue
            if remaining_counts is not None and _indices_counts(atoms, remaining) != remaining_counts:
                continue
            out.append({
                "moving_indices": moving,
                "remaining_indices": remaining,
                "moving_formula": _formula_for_indices(atoms, moving),
                "remaining_formula": _formula_for_indices(atoms, remaining),
                "broken_bond": [int(bond[0]), int(bond[1])],
                "broken_bond_symbols": [atoms[int(bond[0])].symbol, atoms[int(bond[1])].symbol],
            })
    return out


def propose_local_transform_packet(
    atoms: Atoms,
    *,
    record: dict[str, Any] | None = None,
    structure_id: str | None = None,
    transform_type: str = "diffusion",
    moving_fragment: str | None = None,
    remaining_fragment: str | None = None,
    break_bond: list[str] | tuple[str, ...] | None = None,
    target_adsorbate: str | None = None,
    max_site_distance: float = 3.5,
    neighbor_shell: int = 2,
    max_candidates: int = 20,
    max_indices: int = 120,
    backend: str = "acat",
    weighted_alpha_config: object | None = None,
) -> dict[str, Any]:
    """Return read-only local diffusion/dissociation transform candidates."""
    record = record or {}
    normalized = str(transform_type or "diffusion").strip().lower()
    if normalized not in {"diffusion", "dissociation"}:
        return {
            "structure_id": structure_id or record.get("id") or record.get("structure_id"),
            "transform_type": normalized,
            "candidates": [],
            "warnings": [f"unsupported transform_type {transform_type!r}; use diffusion or dissociation"],
        }

    ads_indices = _adsorbate_indices(atoms, record=record)
    warnings: list[str] = []
    if not ads_indices:
        warnings.append("no adsorbate atom indices found from metadata or tags")

    target_label = target_adsorbate or moving_fragment or (_formula_for_indices(atoms, ads_indices) if ads_indices else "H")
    site_packet = analyze_surface_sites_packet(
        atoms,
        record=record,
        structure_id=structure_id,
        backend=backend,
        target_adsorbate=target_label,
        max_site_distance=max_site_distance,
        neighbor_shell=neighbor_shell,
        max_sites=max(500, max_candidates * 10),
        max_edges=max(1000, max_candidates * 20),
        weighted_alpha_config=weighted_alpha_config,
    )
    warnings.extend(site_packet.get("warnings") or [])
    source_site = site_packet.get("current_site") or site_packet.get("source_site")
    targets = _neighbor_site_targets(site_packet, atoms=atoms)
    if not source_site:
        warnings.append("no current/source adsorption site could be matched")
    if normalized == "diffusion" and not targets:
        warnings.append("no neighboring target sites found within shell/distance limits")

    candidates: list[dict[str, Any]] = []
    if normalized == "diffusion":
        moving = ads_indices
        moving_formula = moving_fragment or (_formula_for_indices(atoms, moving) if moving else None)
        anchor = _anchor_position_for_sites(atoms, record)
        for target, distance, shell in targets:
            target_pos = _site_position(target)
            score = _mic_norm(atoms, anchor, target_pos) if anchor is not None and target_pos is not None else float(distance)
            candidates.append({
                "id": f"transform:diffusion:{len(candidates)}",
                "transform_type": "diffusion",
                "source_site": source_site,
                "target_site": target,
                "site_distance": float(distance),
                "neighbor_shell": int(shell),
                "moving_fragment": moving_formula,
                "moving_indices": _bounded_indices(moving, max_indices=max_indices),
                "moving_anchor_index": int(ads_indices[0]) if ads_indices else None,
                "remaining_fragment": None,
                "remaining_indices": _bounded_indices([], max_indices=max_indices),
                "broken_bond": None,
                "score": float(score),
                "warnings": [] if moving else ["empty moving atom group"],
            })
            if len(candidates) >= max_candidates:
                break
    else:
        moving_label = moving_fragment or "H"
        formula_warnings = [
            warning
            for warning in (
                _invalid_formula_warning("moving_fragment", moving_label),
                _invalid_formula_warning("remaining_fragment", remaining_fragment),
            )
            if warning is not None
        ]
        warnings.extend(formula_warnings)
        cleavages = [] if formula_warnings else (
            _cleavage_proposals(
                atoms,
                ads_indices,
                moving_fragment=moving_label,
                remaining_fragment=remaining_fragment,
                break_bond=break_bond,
            ) if ads_indices else []
        )
        if not cleavages:
            warnings.append("no matching bond cleavage candidates found")
        seen: set[tuple] = set()
        sites = [site for site in (site_packet.get("sites") or []) if isinstance(site, dict)]
        for cleavage in cleavages:
            moving = [int(index) for index in cleavage["moving_indices"]]
            remaining = [int(index) for index in cleavage["remaining_indices"]]
            moving_anchor, moving_source_site, moving_source_distance = _fragment_current_site(
                atoms,
                moving,
                sites,
                moving_label,
            )
            if moving_anchor is None or moving_source_site is None:
                continue
            moving_targets = _neighbor_site_targets(site_packet, source_site=moving_source_site, atoms=atoms)
            if not moving_targets:
                continue

            remaining_anchor = None
            remaining_source_site = None
            remaining_source_distance = 0.0
            remaining_targets: list[tuple[dict[str, Any], float, int]] = []
            if remaining_fragment:
                remaining_anchor, remaining_source_site, remaining_source_distance = _fragment_current_site(
                    atoms,
                    remaining,
                    sites,
                    remaining_fragment,
                )
                if remaining_source_site is not None:
                    remaining_targets = _neighbor_site_targets(site_packet, source_site=remaining_source_site, atoms=atoms)

            pairs: list[tuple[dict[str, Any], float, int, dict[str, Any] | None, float | None, int | None]] = []
            for target, distance, shell in moving_targets:
                pairs.append((target, distance, shell, None, None, None))
                for remaining_target, remaining_distance, remaining_shell in remaining_targets:
                    if str(remaining_target.get("id")) == str(target.get("id")):
                        continue
                    pairs.append((target, distance, shell, remaining_target, remaining_distance, remaining_shell))

            for target, distance, shell, remaining_target, remaining_distance, remaining_shell in pairs:
                target_position = _site_position(target)
                if target_position is None:
                    continue
                moving_target_position = np.array(target_position, dtype=float)
                moving_target_position[2] += float(DEFAULT_BOND_HEIGHT.get(moving_label, 1.6))
                moving_score = _mic_norm(atoms, np.array(atoms.positions[moving_anchor]), moving_target_position)

                remaining_target_anchor = None
                remaining_score = 0.0
                if remaining_target is not None:
                    if remaining_anchor is None:
                        continue
                    remaining_target_position = _site_position(remaining_target)
                    if remaining_target_position is None:
                        continue
                    remaining_target_position = np.array(remaining_target_position, dtype=float)
                    remaining_target_position[2] += float(DEFAULT_BOND_HEIGHT.get(remaining_fragment or "", 1.6))
                    remaining_target_anchor = remaining_anchor
                    remaining_score = _mic_norm(
                        atoms,
                        np.array(atoms.positions[remaining_target_anchor]),
                        remaining_target_position,
                    )

                key = (
                    str(moving_source_site.get("id")),
                    tuple(cleavage["moving_indices"]),
                    tuple(cleavage["remaining_indices"]),
                    tuple(cleavage["broken_bond"]),
                    str(target.get("id")),
                    str(remaining_target.get("id")) if remaining_target else "",
                )
                if key in seen:
                    continue
                seen.add(key)
                candidates.append({
                    "id": f"transform:dissociation:{len(candidates)}",
                    "transform_type": "dissociation",
                    "source_site": moving_source_site,
                    "target_site": target,
                    "site_distance": float(distance),
                    "neighbor_shell": int(shell),
                    "moving_fragment": moving_label,
                    "moving_indices": _bounded_indices(cleavage["moving_indices"], max_indices=max_indices),
                    "moving_anchor_index": moving_anchor,
                    "moving_source_lateral_distance": float(moving_source_distance),
                    "moving_anchor_target_distance": float(moving_score),
                    "remaining_fragment": remaining_fragment or cleavage["remaining_formula"],
                    "remaining_indices": _bounded_indices(cleavage["remaining_indices"], max_indices=max_indices),
                    "remaining_source_site": remaining_source_site,
                    "remaining_source_lateral_distance": float(remaining_source_distance),
                    "remaining_target_site": remaining_target,
                    "remaining_site_distance": float(remaining_distance) if remaining_distance is not None else None,
                    "remaining_neighbor_shell": int(remaining_shell) if remaining_shell is not None else None,
                    "remaining_anchor_index": remaining_target_anchor,
                    "remaining_anchor_target_distance": float(remaining_score),
                    "broken_bond": cleavage["broken_bond"],
                    "broken_bond_symbols": cleavage["broken_bond_symbols"],
                    "score": float(
                        moving_score
                        + remaining_score
                        + moving_source_distance
                        + remaining_source_distance
                    ),
                    "warnings": [],
                })
        if cleavages and not candidates:
            warnings.append("no neighboring target sites found from moving fragment current site")

    candidates.sort(key=lambda item: (item.get("neighbor_shell", 99), float(item.get("site_distance", 0.0)), float(item.get("score", 0.0)), item.get("id", "")))
    return {
        "structure_id": structure_id or record.get("id") or record.get("structure_id"),
        "transform_type": normalized,
        "source": "site_graph_and_fragment_graph",
        "source_site": source_site,
        "target_adsorbate": target_label,
        "adsorbate_indices": _bounded_indices(ads_indices, max_indices=max_indices),
        "site_graph": {
            "source": site_packet.get("source"),
            "backend": site_packet.get("backend"),
            "n_sites": site_packet.get("n_sites", 0),
            "n_edges": site_packet.get("n_edges", 0),
            "site_type_counts": site_packet.get("site_type_counts", {}),
        },
        "parameters": {
            "moving_fragment": moving_fragment,
            "remaining_fragment": remaining_fragment,
            "break_bond": list(break_bond) if break_bond else None,
            "max_site_distance": float(max_site_distance),
            "neighbor_shell": int(neighbor_shell),
            "max_candidates": int(max_candidates),
        },
        "candidates": candidates[:max_candidates],
        "warnings": warnings,
    }


def _cell_packet(atoms: Atoms) -> dict[str, Any]:
    cell = np.array(atoms.get_cell(), dtype=float)
    finite = bool(np.all(np.isfinite(cell)))
    lengths = [float(np.linalg.norm(cell[i])) for i in range(3)] if finite else [0.0, 0.0, 0.0]
    if finite and all(length > 1e-12 for length in lengths):
        a, b, c, alpha, beta, gamma = cell_to_params(cell)
    else:
        a, b, c = lengths
        alpha = beta = gamma = 0.0
    return {
        "lengths": [a, b, c],
        "angles": [alpha, beta, gamma],
        "volume": float(abs(np.linalg.det(cell))) if finite else 0.0,
        "pbc": [bool(value) for value in atoms.get_pbc()],
    }


def analyze_structure_packet(
    atoms: Atoms,
    *,
    record: dict[str, Any] | None = None,
    structure_id: str | None = None,
    min_distance: float = 0.5,
    max_atoms: int = 200,
    max_indices: int = 80,
) -> dict[str, Any]:
    """Return a bounded structure-understanding packet."""
    record = record or {}
    check = check_min_distance(atoms, threshold=min_distance)
    site = _site_summary(record, atoms)
    return {
        "structure_id": structure_id or record.get("id") or record.get("structure_id"),
        "kind": record.get("kind"),
        "parent_ids": record.get("parent_ids") or record.get("parent_structure_ids") or [],
        "mpid": record.get("mpid"),
        "formula": atoms.get_chemical_formula(),
        "n_atoms": len(atoms),
        "composition": composition_counts(atoms),
        "cell": _cell_packet(atoms),
        "tags": _tag_summary(atoms),
        "magmoms": _magmom_summary(atoms),
        "layers": _detect_z_layers(atoms, max_indices=max_indices),
        "adsorbates": _adsorbate_groups(atoms, record=record, max_indices=max_indices),
        "surface": site,
        "quality": {
            "min_distance": float(check.min_distance),
            "min_distance_threshold": float(check.threshold),
            "min_distance_passed": bool(check.passed),
            "min_distance_pair": [check.atom_i, check.atom_j],
            "atom_count_passed": bool(len(atoms) <= max_atoms),
            "max_atoms": int(max_atoms),
        },
    }


def propose_atom_selection_packet(
    atoms: Atoms,
    *,
    record: dict[str, Any] | None = None,
    structure_id: str | None = None,
    intent: str = "adsorbate",
    indices: list[int] | tuple[int, ...] | None = None,
    n_layers: int = 1,
    tag: int | None = None,
    element: str | None = None,
    max_indices: int = 120,
) -> dict[str, Any]:
    """Return read-only atom-selection candidates for a saved structure."""
    record = record or {}
    normalized = str(intent or "adsorbate").strip().lower().replace("-", "_")
    tags_present = "tags" in getattr(atoms, "arrays", {})
    tags = atoms.get_tags() if tags_present else None
    candidates: list[dict[str, Any]] = []

    def add(candidate_id: str, label: str, values: list[int], source: str, warnings: list[str] | None = None) -> None:
        candidates.append(_selection_candidate(
            atoms,
            candidate_id=candidate_id,
            label=label,
            intent=normalized,
            indices=values,
            source=source,
            max_indices=max_indices,
            warnings=warnings,
        ))

    if normalized in {"adsorbate", "adsorbates"}:
        ads = _adsorbate_indices(atoms, record=record)
        warnings = [] if ads else ["no adsorbate atom indices found from metadata or tags"]
        add("selection:adsorbate", "adsorbate atoms", ads, "adsorbate_metadata_or_tags", warnings)
    elif normalized == "fixed_slab":
        values = np.where(tags == FIXED_SLAB_TAG)[0].astype(int).tolist() if tags_present else []
        warnings = [] if tags_present else ["tags array missing; cannot identify fixed slab atoms"]
        add("selection:fixed_slab", "fixed slab atoms", values, "tags==0", warnings)
    elif normalized == "relaxable_slab":
        values = np.where(tags == RELAXABLE_SLAB_TAG)[0].astype(int).tolist() if tags_present else []
        warnings = [] if tags_present else ["tags array missing; cannot identify relaxable slab atoms"]
        add("selection:relaxable_slab", "relaxable slab atoms", values, "tags==1", warnings)
    elif normalized in {"top_layers", "bottom_layers"}:
        layer_groups = _z_layer_groups(atoms)
        n = max(1, int(n_layers or 1))
        selected = layer_groups[-n:] if normalized == "top_layers" else layer_groups[:n]
        values = [index for group in selected for index in group]
        label = f"{'top' if normalized == 'top_layers' else 'bottom'} {min(n, len(layer_groups))} layer(s)"
        add(f"selection:{normalized}:{n}", label, values, "z_layer_grouping")
    elif normalized == "explicit":
        raw = list(indices or [])
        values = _valid_indices(atoms, raw)
        bad_count = len(raw) - len(values)
        warnings = [f"{bad_count} invalid or duplicate index value(s) ignored"] if bad_count else []
        add("selection:explicit", "explicit atom indices", values, "user_indices", warnings)
    elif normalized == "tag":
        if tag is None:
            add("selection:tag", "tag selection", [], "tags", ["tag value is required"])
        else:
            values = np.where(tags == int(tag))[0].astype(int).tolist() if tags_present else []
            warnings = [] if tags_present else ["tags array missing; cannot select by tag"]
            add(f"selection:tag:{int(tag)}", f"tag {int(tag)} atoms", values, f"tags=={int(tag)}", warnings)
    elif normalized == "element":
        symbol = str(element or "").strip()
        if not symbol:
            add("selection:element", "element selection", [], "symbols", ["element symbol is required"])
        else:
            values = [i for i, atom in enumerate(atoms) if atom.symbol == symbol]
            add(f"selection:element:{symbol}", f"{symbol} atoms", values, f"symbol=={symbol}")
    elif normalized == "all":
        add("selection:all", "all atoms", list(range(len(atoms))), "all_atoms")
    else:
        add(
            "selection:unknown",
            "unknown selection intent",
            [],
            "none",
            [f"unsupported intent {intent!r}; use adsorbate, fixed_slab, relaxable_slab, top_layers, bottom_layers, explicit, tag, element, or all"],
        )

    return {
        "structure_id": structure_id or record.get("id") or record.get("structure_id"),
        "intent": normalized,
        "n_atoms": len(atoms),
        "candidates": candidates,
    }


def identify_fragments_packet(
    atoms: Atoms,
    *,
    record: dict[str, Any] | None = None,
    structure_id: str | None = None,
    atom_indices: list[int] | tuple[int, ...] | None = None,
    cutoff_scale: float = 1.15,
    max_indices: int = 120,
) -> dict[str, Any]:
    """Return a read-only covalent graph and connected fragments."""
    record = record or {}
    selected = _valid_indices(atoms, list(atom_indices or []))
    source = "user_indices"
    if not selected:
        selected = _adsorbate_indices(atoms, record=record)
        source = "adsorbate_metadata_or_tags"
    if not selected:
        selected = list(range(len(atoms)))
        source = "all_atoms_fallback"

    subset = atoms[selected].copy()
    subset.set_pbc(False)
    bonds: list[tuple[int, int]] = []
    if len(subset) > 1:
        cutoffs = [float(value) * float(cutoff_scale) for value in natural_cutoffs(subset)]
        nl = NeighborList(cutoffs, self_interaction=False, bothways=True)
        nl.update(subset)
        seen: set[tuple[int, int]] = set()
        for local_i, global_i in enumerate(selected):
            local_neighbors, _ = nl.get_neighbors(local_i)
            for local_j in local_neighbors:
                global_j = selected[int(local_j)]
                pair = tuple(sorted((int(global_i), int(global_j))))
                if pair not in seen:
                    seen.add(pair)
                    bonds.append(pair)

    graph: dict[int, set[int]] = {int(index): set() for index in selected}
    for i, j in bonds:
        graph[i].add(j)
        graph[j].add(i)
    fragments: list[list[int]] = []
    seen_nodes: set[int] = set()
    for index in selected:
        if index in seen_nodes:
            continue
        stack = [int(index)]
        seen_nodes.add(int(index))
        component: list[int] = []
        while stack:
            current = stack.pop()
            component.append(current)
            for nxt in sorted(graph[current]):
                if nxt not in seen_nodes:
                    seen_nodes.add(nxt)
                    stack.append(nxt)
        fragments.append(sorted(component))
    fragments.sort(key=lambda item: (len(item), item[0] if item else -1))

    return {
        "structure_id": structure_id or record.get("id") or record.get("structure_id"),
        "source": source,
        "selected_atoms": _bounded_indices(selected, max_indices=max_indices),
        "fragments": [
            {
                "id": f"fragment:{i}",
                "count": len(fragment),
                "formula": _formula_for_indices(atoms, fragment),
                "atom_indices": _bounded_indices(fragment, max_indices=max_indices),
            }
            for i, fragment in enumerate(fragments)
        ],
        "bonds": [
            {
                "atom_indices": [int(i), int(j)],
                "symbols": [atoms[int(i)].symbol, atoms[int(j)].symbol],
                "length": float(atoms.get_distance(int(i), int(j), mic=False)),
            }
            for i, j in bonds
        ],
        "cutoff_scale": float(cutoff_scale),
    }


def _metadata_indices(record: dict[str, Any] | None, atoms: Atoms) -> list[tuple[str, list[int]]]:
    record = record or {}
    out: list[tuple[str, list[int]]] = []

    source_site = record.get("source_site") or _json_info(atoms, "source_site_json", default=None)
    if isinstance(source_site, dict):
        values = source_site.get("surface_atom_indices") or []
        out.append(("source_site.surface_atom_indices", [int(v) for v in values]))

    ads_meta = record.get("adsorbate_metadata") or _json_info(atoms, "adsorbate_metadata_json", default=None)
    if isinstance(ads_meta, dict):
        values = ads_meta.get("atom_indices") or []
        out.append(("adsorbate_metadata.atom_indices", [int(v) for v in values]))

    site_map = record.get("site_map") or {}
    if isinstance(site_map, dict):
        sites = site_map.get("sites") or []
        for i, site in enumerate(sites):
            if isinstance(site, dict):
                values = site.get("surface_atom_indices") or []
                out.append((f"site_map.sites[{i}].surface_atom_indices", [int(v) for v in values]))
    return out


def validate_structure_packet(
    atoms: Atoms,
    *,
    record: dict[str, Any] | None = None,
    min_distance: float = 0.5,
    max_atoms: int = 200,
) -> dict[str, Any]:
    """Return pass/fail validation checks for a saved structure."""
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, message: str, **extra: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "message": message, **extra})

    cell = np.array(atoms.get_cell(), dtype=float)
    finite_cell = bool(np.all(np.isfinite(cell)))
    volume = float(abs(np.linalg.det(cell))) if finite_cell else 0.0
    lengths = [float(np.linalg.norm(cell[i])) for i in range(3)] if finite_cell else [0.0, 0.0, 0.0]
    add("cell_finite", finite_cell, "cell matrix is finite")
    add("cell_volume", volume > 1e-8, f"cell volume={volume:.6g} Å^3", volume=volume)
    add("cell_lengths", all(length > 1e-8 for length in lengths), "cell lengths are positive", lengths=lengths)

    check = check_min_distance(atoms, threshold=min_distance)
    add(
        "min_distance",
        check.passed,
        f"min distance {check.min_distance:.3f} Å >= {check.threshold:.3f} Å",
        min_distance=float(check.min_distance),
        threshold=float(check.threshold),
        pair=[check.atom_i, check.atom_j],
    )
    add("atom_count", len(atoms) <= max_atoms, f"{len(atoms)} atoms <= {max_atoms}", n_atoms=len(atoms), max_atoms=max_atoms)

    arrays = getattr(atoms, "arrays", {})
    if "tags" in arrays:
        add("tags_length", len(atoms.get_tags()) == len(atoms), "tags length matches atom count")
    else:
        has_fix_atoms = any(isinstance(constraint, FixAtoms) for constraint in atoms.constraints)
        record_kind = str((record or {}).get("kind") or "").strip().lower()
        clean_slab_like = record_kind == "slab" or (
            has_fix_atoms
            and not (record or {}).get("adsorbate_metadata")
            and not atoms.info.get("adsorbate_metadata_json")
            and not atoms.info.get("slab_atom_count")
        )
        add(
            "tags_present",
            clean_slab_like,
            (
                "tags array missing; allowed for clean slab with FixAtoms"
                if clean_slab_like
                else "tags array missing"
            ),
        )
    if "initial_magmoms" in arrays:
        add(
            "magmoms_length",
            len(atoms.get_initial_magnetic_moments()) == len(atoms),
            "initial_magmoms length matches atom count",
        )
    else:
        add("magmoms_present", True, "initial_magmoms absent; allowed")

    invalid_metadata: list[dict[str, Any]] = []
    for key, indices in _metadata_indices(record, atoms):
        bad = [index for index in indices if index < 0 or index >= len(atoms)]
        if bad:
            invalid_metadata.append({"field": key, "invalid_indices": bad})
    add(
        "metadata_indices",
        not invalid_metadata,
        "metadata atom indices are in range" if not invalid_metadata else "metadata contains out-of-range atom indices",
        invalid=invalid_metadata,
    )

    passed = all(item["passed"] for item in checks)
    return {
        "passed": bool(passed),
        "checks": checks,
    }
