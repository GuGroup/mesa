"""Adsorption-site graph helpers used by structure inspection."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from ase import Atoms

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
) -> SiteMap:
    """Build a local site map from the current slab geometry."""
    raw_sites = identify_adsorption_sites(slab_atoms, target_adsorbate, backend=backend)
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
    return {
        "sites": [_site_to_jsonable(site) for site in site_map.sites],
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


def _site_record(site: AdsorptionSite, index: int) -> SiteRecord:
    return SiteRecord(
        id=f"site:{index}",
        site_type=site.site_type,
        position=tuple(float(v) for v in np.array(site.position, dtype=float).tolist()),
        surface_atom_indices=tuple(int(idx) for idx in site.surface_atom_idx),
        sources=tuple(str(source) for source in site.sources),
        validation_score=float(site.validation_score),
        priority=int(site.priority),
    )


def _site_distance(atoms: Atoms, a: SiteRecord, b: SiteRecord) -> float:
    return float(np.linalg.norm(_mic_vector(atoms, np.array(a.position), np.array(b.position))))


def _mic_vector(atoms: Atoms, start: np.ndarray, end: np.ndarray) -> np.ndarray:
    cell = atoms.cell.array
    vector = np.array(end, dtype=float) - np.array(start, dtype=float)
    if abs(np.linalg.det(cell)) < 1e-12:
        return vector
    frac = np.linalg.solve(cell.T, vector)
    for axis, periodic in enumerate(atoms.pbc):
        if periodic:
            frac[axis] -= np.round(frac[axis])
    return frac @ cell


def _distance_shell(distance: float, shells: list[float], *, tolerance: float = 0.25) -> int:
    for index, existing in enumerate(shells, start=1):
        if abs(distance - existing) <= tolerance:
            return index
    shells.append(float(distance))
    return len(shells)


def _site_to_jsonable(site: SiteRecord) -> dict:
    return {
        "id": site.id,
        "site_type": site.site_type,
        "position": [float(v) for v in site.position],
        "surface_atom_indices": [int(idx) for idx in site.surface_atom_indices],
        "sources": list(site.sources),
        "validation_score": float(site.validation_score),
        "priority": int(site.priority),
    }
