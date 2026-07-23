"""Adsorption-site graph helpers used by structure inspection."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any

import numpy as np
from ase import Atoms
from ase.geometry import find_mic

from slabuilder.adsorption import AdsorptionSite, identify_adsorption_sites

DEFAULT_MAX_SITE_DISTANCE = 3.5


@dataclass(frozen=True)
class SiteRecord:
    """Serializable adsorption-site record."""

    id: str
    site_type: str
    position: tuple[float, float, float]
    surface_atom_indices: tuple[int, ...] = ()
    sources: tuple[str, ...] = ()
    validation_score: float = 0.0
    priority: int = 99
    validation_notes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SiteNeighbor:
    source_site_id: str
    target_site_id: str
    distance: float
    shell: int


@dataclass(frozen=True)
class SiteMap:
    sites: tuple[SiteRecord, ...]
    neighbors: tuple[SiteNeighbor, ...]

    def site_by_id(self, site_id: str) -> SiteRecord | None:
        for site in self.sites:
            if site.id == site_id:
                return site
        return None


def build_site_map(
    slab_atoms: Atoms,
    *,
    target_adsorbate: str = "H",
    max_site_distance: float = DEFAULT_MAX_SITE_DISTANCE,
    backend: str = "auto",
    weighted_alpha_config: object | None = None,
) -> SiteMap:
    """Build a local site map from the current slab geometry."""
    raw_sites = identify_adsorption_sites(
        slab_atoms,
        target_adsorbate,
        backend=backend,
        weighted_alpha_config=weighted_alpha_config,
    )
    sites = tuple(_site_record(site, idx) for idx, site in enumerate(raw_sites))
    neighbors: list[SiteNeighbor] = []
    for source in sites:
        distances: list[tuple[SiteRecord, float]] = []
        for target in sites:
            if source.id == target.id:
                continue
            distance = _site_distance(slab_atoms, source, target)
            if 0.35 < distance <= max_site_distance:
                distances.append((target, distance))
        distances.sort(key=lambda item: item[1])
        shells: list[float] = []
        for target, distance in distances:
            shell = _distance_shell(distance, shells)
            neighbors.append(SiteNeighbor(source.id, target.id, float(distance), shell))
    return SiteMap(sites=sites, neighbors=tuple(neighbors))


def site_map_to_jsonable(site_map: SiteMap) -> dict:
    sites = [_site_to_jsonable(site) for site in site_map.sites]
    weighted_runs: list[dict[str, Any]] = []
    for site in sites:
        metadata = site.get("metadata")
        weighted = metadata.get("weighted_alpha") if isinstance(metadata, dict) else None
        run = weighted.get("run") if isinstance(weighted, dict) else None
        if isinstance(run, dict):
            weighted_runs.append(run)
    common_run = None
    if sites and len(weighted_runs) == len(sites) and all(
        run == weighted_runs[0] for run in weighted_runs[1:]
    ):
        common_run = weighted_runs[0]
        for site in sites:
            weighted = site["metadata"]["weighted_alpha"]
            weighted.pop("run", None)
            weighted["run_ref"] = "site_map.metadata.weighted_alpha_run"
    result = {
        "sites": sites,
        "neighbors": [
            {
                "source_site_id": neighbor.source_site_id,
                "target_site_id": neighbor.target_site_id,
                "distance": neighbor.distance,
                "shell": neighbor.shell,
            }
            for neighbor in site_map.neighbors
        ],
    }
    if common_run is not None:
        result["metadata"] = {"weighted_alpha_run": common_run}
    return result


def _site_record(site: AdsorptionSite, index: int) -> SiteRecord:
    return SiteRecord(
        id=f"site:{index}",
        site_type=site.site_type,
        position=tuple(float(v) for v in np.array(site.position, dtype=float).tolist()),
        surface_atom_indices=tuple(int(idx) for idx in site.surface_atom_idx),
        sources=tuple(str(source) for source in site.sources),
        validation_score=float(site.validation_score),
        priority=int(site.priority),
        validation_notes=tuple(str(note) for note in site.validation_notes),
        metadata=dict(site.metadata),
    )


def _site_distance(atoms: Atoms, a: SiteRecord, b: SiteRecord) -> float:
    vector_fn = (
        _weighted_mic_vector
        if "weighted_alpha" in a.sources or "weighted_alpha" in b.sources
        else _mic_vector
    )
    return float(np.linalg.norm(vector_fn(atoms, np.array(a.position), np.array(b.position))))


def _mic_vector(atoms: Atoms, start: np.ndarray, end: np.ndarray) -> np.ndarray:
    """Legacy component-wise fractional MIC retained for compatibility."""
    cell = atoms.cell.array
    vector = np.array(end, dtype=float) - np.array(start, dtype=float)
    if abs(np.linalg.det(cell)) < 1e-12:
        return vector
    frac = np.linalg.solve(cell.T, vector)
    for axis, periodic in enumerate(atoms.pbc):
        if periodic:
            frac[axis] -= np.round(frac[axis])
    return frac @ cell


def _weighted_mic_vector(atoms: Atoms, start: np.ndarray, end: np.ndarray) -> np.ndarray:
    """True closest-lattice-vector MIC for explicit weighted-alpha records."""
    vector = np.array(end, dtype=float) - np.array(start, dtype=float)
    cell = np.asarray(atoms.cell.array, dtype=float)
    if abs(float(np.linalg.det(cell))) < 1.0e-12:
        return vector
    mic, _ = find_mic(vector, cell=cell, pbc=np.asarray(atoms.pbc, dtype=bool))
    return np.asarray(mic, dtype=float)


def _distance_shell(distance: float, shells: list[float], *, tolerance: float = 0.25) -> int:
    for index, existing in enumerate(shells, start=1):
        if abs(distance - existing) <= tolerance:
            return index
    shells.append(float(distance))
    return len(shells)


def _site_to_jsonable(site: SiteRecord) -> dict:
    result = {
        "id": site.id,
        "site_type": site.site_type,
        "position": [float(v) for v in site.position],
        "surface_atom_indices": [int(idx) for idx in site.surface_atom_indices],
        "sources": list(site.sources),
        "validation_score": float(site.validation_score),
        "priority": int(site.priority),
    }
    if "weighted_alpha" in site.sources and site.validation_notes:
        result["validation_notes"] = list(site.validation_notes)
    if site.metadata:
        result["metadata"] = _json_safe(site.metadata)
    return result


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_json_safe(item) for item in value), key=lambda item: repr(item))
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("metadata contains a nonfinite number")
        return value
    if value is None or isinstance(value, (str, bool, int)):
        return value
    return str(value)
