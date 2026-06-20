"""
adsorption.py — Tool 4: Adsorption site identification and adsorbate placement.

Strategy:
    1. Identify adsorption sites with CatKit AdsorptionSites
       (topology-aware Voronoi + Delaunay), pymatgen AdsorbateSiteFinder,
       and ACAT when the slab chemistry is compatible with ACAT's adsorbate
       element conventions.
    2. Merge nearby candidates and retain per-site source metadata.
    3. Build an oriented adsorbate geometry.
    4. Place the adsorbate via direct ASE placement.
    5. Apply site priority rules from config.SITE_PRIORITY.

Supported adsorbates:
    Closed-shell examples: CO, H2O, NH3, CO2, CH4, N2, O2
    Radical / open-shell examples: O, N, C, S, H, OH, OOH, NO, SH, CH3, CH2
"""

from __future__ import annotations

import json
import contextlib
import io
import warnings
from dataclasses import dataclass, field, replace
from typing import Literal

import numpy as np
from ase import Atoms
from ase.build import molecule as ase_molecule
from ase.constraints import FixAtoms

from slabuilder.compat import apply_numpy_compat

apply_numpy_compat()

from slabuilder.structure_checks import check_min_distance
from slabuilder.config import (
    SITE_PRIORITY,
    ADSORBATE_BINDING_ATOMS,
    ADSORBATE_SMILES,
    AUTOADSORBATE_ATTACK_ATOMS,
    AUTOADSORBATE_CONFORMERS_PER_SITE_CAP,
    AUTOADSORBATE_CONFORMERS_TO_INITIALIZE,
    AUTOADSORBATE_FIRST_ADSORBATES,
    AUTOADSORBATE_OVERLAP_THRESHOLD,
    AUTOADSORBATE_SURFACE_ENABLED,
    AUTOADSORBATE_SURFACE_PRECISION,
    AUTOADSORBATE_TOUCH_SPHERE_SIZE,
    CLOSED_SHELL_ADSORBATES,
    DEFAULT_BOND_HEIGHT,
    MIN_PLACEMENT_DISTANCE,
    RADICAL_ADSORBATES,
)

SiteType = Literal["top", "bridge", "fcc_hollow", "hcp_hollow", "hollow"]
FIXED_SLAB_TAG = 0
RELAXABLE_SLAB_TAG = 1
ADSORBATE_TAG = 2
SITE_SOURCE_ORDER = ("catkit", "pymatgen", "acat", "autoadsorbate")
ACAT_DEFAULT_ADSORBATE_ELEMENTS = frozenset({"H", "C", "N", "O", "F", "S", "Cl", "X"})


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AdsorptionSite:
    """A candidate adsorption site on a slab surface.

    Attributes:
        site_type:         'top', 'bridge', 'fcc_hollow', 'hcp_hollow', 'hollow'.
        position:          Cartesian coordinates (x, y, z) in Å.
        surface_atom_idx:  Index/indices of underlying surface atoms.
        priority:          Lower = higher priority (from SITE_PRIORITY rules).
        placement_method:  Final placement method. Currently always 'ase_manual'.
        catkit_index:      CatKit internal site index (for Builder.add_adsorbate).
        sources:           Site detectors that found this site.
        validation_score:  Cross-backend confidence score in [0, 1].
        validation_notes:  Short provenance notes explaining the score.
    """
    site_type: str
    position: np.ndarray
    surface_atom_idx: list[int] = field(default_factory=list)
    priority: int = 99
    placement_method: str = "ase_manual"
    catkit_index: int = -1
    sources: list[str] = field(default_factory=list)
    validation_score: float = 0.0
    validation_notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Adsorbate classification
# ---------------------------------------------------------------------------

def _classify_adsorbate(adsorbate: str) -> str:
    """Return 'closed_shell' or 'radical' for a given adsorbate formula."""
    if adsorbate in CLOSED_SHELL_ADSORBATES:
        return "closed_shell"
    if adsorbate in RADICAL_ADSORBATES:
        return "radical"
    # Unknown: default to radical (safer: manual placement)
    warnings.warn(
        f"Adsorbate '{adsorbate}' not in known lists. Treating as radical. "
        "Please check CLOSED_SHELL_ADSORBATES and RADICAL_ADSORBATES in config.py.",
        stacklevel=3,
    )
    return "radical"


def _get_priority_for_site(adsorbate: str, site_type: str) -> int:
    """Return priority rank for (adsorbate, site_type) pair.
    Lower is better. Returns 99 if not in priority list."""
    preferred = SITE_PRIORITY.get(adsorbate, [])
    normalized = site_type
    for priority, pref_site in enumerate(preferred):
        if pref_site == normalized:
            return priority
        # Also match generic 'hollow' to fcc/hcp
        if pref_site == "hollow" and "hollow" in normalized:
            return priority
    return 99


# ---------------------------------------------------------------------------
# Site identification
# ---------------------------------------------------------------------------

def _detect_z_layers(z_coords: np.ndarray, gap: float = 0.8) -> list[list[int]]:
    """Return atom-index layers sorted bottom to top."""
    if len(z_coords) == 0:
        return []
    order = np.argsort(z_coords)
    layers: list[list[int]] = [[int(order[0])]]
    for idx in order[1:]:
        layer_z_min = z_coords[layers[-1][0]]
        if z_coords[idx] - layer_z_min > gap:
            layers.append([int(idx)])
        else:
            layers[-1].append(int(idx))
    return layers


def _classify_threefold_hollow(
    slab_atoms: Atoms,
    position: np.ndarray,
    subsurface_indices: list[int],
    xy_tolerance: float = 0.35,
) -> str:
    """Classify a 3-fold hollow as hcp if a first-subsurface atom is below it."""
    if not subsurface_indices:
        return "fcc_hollow"

    cell = slab_atoms.cell.array
    scaled = slab_atoms.get_scaled_positions(wrap=False)
    site_frac = np.linalg.solve(cell.T, position)

    min_dist = float("inf")
    for atom_idx in subsurface_indices:
        delta_xy = site_frac[:2] - scaled[atom_idx, :2]
        delta_xy -= np.round(delta_xy)
        vec = delta_xy[0] * cell[0] + delta_xy[1] * cell[1]
        min_dist = min(min_dist, float(np.linalg.norm(vec)))

    return "hcp_hollow" if min_dist <= xy_tolerance else "fcc_hollow"

def identify_adsorption_sites(
    slab_atoms: Atoms,
    adsorbate: str,
    backend: str = "auto",
) -> list[AdsorptionSite]:
    """Identify adsorption sites on a slab surface.

    Runs CatKit, pymatgen, and compatible ACAT site finders, then merges nearby
    candidates so the caller can see detector agreement in ``sources``. When a
    specific backend is requested, that detector is tried first and falls back
    to the merged auto detector if it fails or returns no sites.

    Args:
        slab_atoms:  ASE Atoms object of the slab (with FixAtoms constraint).
        adsorbate:   Adsorbate formula string (e.g., "CO", "O", "H2O").
        backend:     "auto", "acat", "catkit", or "pymatgen".

    Returns:
        List of AdsorptionSite objects, sorted by priority (ascending).
    """
    backend_name = str(backend or "auto").strip().lower()
    specific = {
        "acat": ("ACAT", _identify_sites_acat),
        "catkit": ("CatKit", _identify_sites_catkit),
        "pymatgen": ("pymatgen AdsorbateSiteFinder", _identify_sites_pymatgen),
    }.get(backend_name)
    if specific is not None:
        label, detector = specific
        try:
            sites = detector(slab_atoms, adsorbate)
            for site in sites:
                if not site.sources:
                    site.sources = [backend_name]
                _annotate_site_validation(site)
            sites.sort(key=lambda s: _site_sort_key(slab_atoms, s))
            if sites:
                return sites
            warnings.warn(
                f"{label} site identification returned no sites. Falling back to merged auto detection.",
                stacklevel=2,
            )
        except Exception as exc:
            warnings.warn(
                f"{label} site identification failed: {exc}. Falling back to merged auto detection.",
                stacklevel=2,
            )

    catkit_sites: list[AdsorptionSite] = []
    pymatgen_sites: list[AdsorptionSite] = []
    acat_sites: list[AdsorptionSite] = []

    try:
        catkit_sites = _identify_sites_catkit(slab_atoms, adsorbate)
    except ImportError:
        warnings.warn(
            "CatKit is not installed. Continuing with pymatgen AdsorbateSiteFinder.",
            stacklevel=2,
        )
    except Exception as exc:
        warnings.warn(
            f"CatKit site identification failed: {exc}. "
            "Continuing with pymatgen AdsorbateSiteFinder.",
            stacklevel=2,
        )

    try:
        pymatgen_sites = _identify_sites_pymatgen(slab_atoms, adsorbate)
    except Exception as exc:
        if not catkit_sites:
            raise
        warnings.warn(
            f"pymatgen AdsorbateSiteFinder failed: {exc}. Returning CatKit sites only.",
            stacklevel=2,
        )

    try:
        acat_sites = _identify_sites_acat(slab_atoms, adsorbate)
    except ImportError:
        warnings.warn(
            "ACAT is not installed. Continuing with CatKit/pymatgen site detection.",
            stacklevel=2,
        )
    except Exception as exc:
        warnings.warn(
            f"ACAT site identification failed: {exc}. "
            "Continuing with CatKit/pymatgen site detection.",
            stacklevel=2,
        )

    sites = _merge_adsorption_sites(slab_atoms, catkit_sites, pymatgen_sites, acat_sites)
    sites.sort(key=lambda s: _site_sort_key(slab_atoms, s))
    return sites


def _site_center_distance_xy(slab_atoms: Atoms, site: AdsorptionSite) -> float:
    """Return in-plane distance from the site's periodic image to cell center."""
    cell = slab_atoms.cell.array
    frac = np.linalg.solve(cell.T, np.array(site.position, dtype=float))
    delta_xy = (frac[:2] % 1.0) - np.array([0.5, 0.5])
    vec = delta_xy[0] * cell[0] + delta_xy[1] * cell[1]
    return float(np.linalg.norm(vec))


def _site_sort_key(slab_atoms: Atoms, site: AdsorptionSite) -> tuple:
    """Sort preferred chemistry first, then choose the most central image."""
    return (
        site.priority,
        site.site_type,
        _site_center_distance_xy(slab_atoms, site),
        float(site.position[2]),
    )


def _shift_site_fractional_xy(
    atoms: Atoms,
    site: AdsorptionSite,
    delta_xy: np.ndarray,
) -> AdsorptionSite:
    """Return a copy of ``site`` shifted by fractional xy ``delta_xy``."""
    cell = atoms.cell.array
    frac = np.linalg.solve(cell.T, np.array(site.position, dtype=float))
    frac[:2] = (frac[:2] + delta_xy) % 1.0
    cart = frac @ cell
    return replace(site, position=np.array(cart, dtype=float))


def _center_site_image_xy(
    atoms: Atoms,
    site: AdsorptionSite,
    *,
    target_xy: tuple[float, float] = (0.5, 0.5),
) -> tuple[Atoms, AdsorptionSite]:
    """Shift a periodic slab image so the selected site appears near cell center.

    Site detectors often return one representative site close to the unit-cell
    boundary. Translating the whole periodic slab is physically equivalent, but
    makes the generated adsorbate structure easier to inspect and edit.
    """
    centered = atoms.copy()
    cell = centered.cell.array
    frac = np.linalg.solve(cell.T, np.array(site.position, dtype=float))
    delta_xy = np.array(target_xy, dtype=float) - (frac[:2] % 1.0)

    scaled = centered.get_scaled_positions(wrap=False)
    scaled[:, :2] = (scaled[:, :2] + delta_xy) % 1.0
    centered.set_scaled_positions(scaled)

    return centered, _shift_site_fractional_xy(centered, site, delta_xy)


def _center_placed_structure_xy(
    atoms: Atoms,
    site: AdsorptionSite,
    *,
    target_xy: tuple[float, float] = (0.5, 0.5),
) -> tuple[Atoms, AdsorptionSite]:
    """Shift an already populated slab+adsorbate so the site is central."""
    centered, centered_site = _center_site_image_xy(atoms, site, target_xy=target_xy)
    centered.info["site_centering_target_frac_json"] = json.dumps(list(target_xy))
    return centered, centered_site


def _identify_sites_catkit(
    slab_atoms: Atoms,
    adsorbate: str,
) -> list[AdsorptionSite]:
    """Use CatKit AdsorptionSites for topology-aware site identification."""
    sites: list[AdsorptionSite] = []

    from catkit.gen.adsorption import AdsorptionSites as CatKitSites
    from catkit.gratoms import Gratoms

    # Wrap slab atoms to [0,1) fractional before CatKit so that Voronoi
    # tessellation produces sites inside the cell (pymatgen/surfaxe slabs
    # often have unwrapped atom positions that push sites outside the cell).
    slab_wrapped = slab_atoms.copy()
    slab_wrapped.set_pbc([True, True, False])
    slab_wrapped.wrap()

    # Gratoms requires edges list (bonding graph); pass empty list for slab
    gratoms = Gratoms(
        numbers=slab_wrapped.numbers,
        positions=slab_wrapped.positions,
        cell=slab_wrapped.cell,
        pbc=slab_wrapped.pbc,
        edges=[],
    )

    # CatKit requires surface_atoms to be explicitly set. When converting
    # from pymatgen/ASE this array is missing, so identify the top layer
    # directly and keep the first subsurface layer for fcc/hcp distinction.
    z = gratoms.positions[:, 2]
    layers = _detect_z_layers(z)
    top_indices = layers[-1] if layers else []
    subsurface_indices = layers[-2] if len(layers) >= 2 else []

    gratoms.set_surface_atoms(top=top_indices)

    catkit_sites = CatKitSites(gratoms)
    selection = catkit_sites.get_symmetric_sites()
    coordinates = catkit_sites.coordinates[selection]
    connectivity = catkit_sites.connectivity[selection]

    # Map CatKit coordination number → site type
    for catkit_index, coord, conn in zip(selection, coordinates, connectivity):
        if conn == 1:
            st = "top"
        elif conn == 2:
            st = "bridge"
        elif conn == 3:
            st = _classify_threefold_hollow(
                gratoms,
                np.array(coord, dtype=float),
                subsurface_indices,
            )
        else:
            st = "hollow"

        surface_atom_idx = [
            int(i)
            for i in np.atleast_1d(
                catkit_sites.index[catkit_sites.r1_topology[int(catkit_index)]]
            ).tolist()
        ]

        site = AdsorptionSite(
            site_type=st,
            position=np.array(coord),
            surface_atom_idx=surface_atom_idx,
            priority=_get_priority_for_site(adsorbate, st),
            placement_method="ase_manual",
            catkit_index=int(catkit_index),
            sources=["catkit"],
        )
        sites.append(site)

    return sites


def _identify_sites_pymatgen(
    slab_atoms: Atoms,
    adsorbate: str,
) -> list[AdsorptionSite]:
    """Use pymatgen AdsorbateSiteFinder for site identification."""
    from pymatgen.analysis.adsorption import AdsorbateSiteFinder
    from slabuilder.utils import ase_to_pymatgen

    pm_slab = ase_to_pymatgen(slab_atoms)
    asf = AdsorbateSiteFinder(pm_slab)
    # The returned coordinates include the requested adsorbate height along the
    # surface normal. Store detector site positions on the surface itself;
    # placement height is applied later by ASE.
    site_list = asf.find_adsorption_sites(distance=0.0)

    # site_list keys: 'ontop', 'bridge', 'hollow', 'all' (combined)
    # Skip 'all' — it's a merged list, not a site type
    pm_type_map = {
        "ontop": "top",
        "bridge": "bridge",
        "hollow": "hollow",
    }
    sites: list[AdsorptionSite] = []
    for pm_type, positions in site_list.items():
        if pm_type not in pm_type_map:
            continue   # skip 'all' and any unknown keys
        st = pm_type_map[pm_type]
        for pos in positions:
            site = AdsorptionSite(
                site_type=st,
                position=np.array(pos),
                priority=_get_priority_for_site(adsorbate, st),
                placement_method="ase_manual",
                catkit_index=-1,
                sources=["pymatgen"],
            )
            sites.append(site)
    return sites


def _is_acat_compatible_clean_slab(slab_atoms: Atoms) -> bool:
    """Return True when ACAT will not confuse slab atoms with adsorbates."""
    return not any(symbol in ACAT_DEFAULT_ADSORBATE_ELEMENTS for symbol in slab_atoms.get_chemical_symbols())


def _acat_site_type(
    slab_atoms: Atoms,
    site: dict,
) -> str:
    """Map an ACAT site dictionary into slabuilder site types."""
    site_type = str(site.get("site", ""))
    position = np.array(site.get("position", site.get("coordinates", [0.0, 0.0, 0.0])), dtype=float)
    if site_type == "ontop":
        return "top"
    if site_type in {"bridge", "longbridge", "shortbridge"}:
        return "bridge"
    if site_type == "fcc":
        return "fcc_hollow"
    if site_type == "hcp":
        return "hcp_hollow"
    if site_type in {"3fold", "4fold", "5fold", "6fold"}:
        layers = _detect_z_layers(np.array(slab_atoms.positions[:, 2], dtype=float))
        subsurface_indices = layers[-2] if len(layers) >= 2 else []
        if site_type == "3fold":
            return _classify_threefold_hollow(slab_atoms, position, subsurface_indices)
        return "hollow"
    return "hollow"


def _identify_sites_acat(
    slab_atoms: Atoms,
    adsorbate: str,
) -> list[AdsorptionSite]:
    """Use ACAT for an independent site detector when its conventions fit."""
    if not _is_acat_compatible_clean_slab(slab_atoms):
        return []

    from acat.adsorption_sites import SlabAdsorptionSites
    from acat.settings import CustomSurface

    slab_wrapped = slab_atoms.copy()
    slab_wrapped.set_pbc([True, True, False])
    slab_wrapped.wrap()

    surface = CustomSurface(slab_wrapped, n_layers=None)
    acat_sites = SlabAdsorptionSites(
        slab_wrapped,
        surface=surface,
        composition_effect=False,
        label_sites=False,
    )

    sites: list[AdsorptionSite] = []
    for raw_site in acat_sites.get_unique_sites():
        position = np.array(raw_site.get("position", raw_site.get("coordinates", [0.0, 0.0, 0.0])), dtype=float)
        surface_atom_idx = [int(idx) for idx in raw_site.get("indices", [])]
        site_type = _acat_site_type(slab_wrapped, raw_site)
        sites.append(
            AdsorptionSite(
                site_type=site_type,
                position=position,
                surface_atom_idx=surface_atom_idx,
                priority=_get_priority_for_site(adsorbate, site_type),
                placement_method="ase_manual",
                catkit_index=-1,
                sources=["acat"],
            )
        )
    return sites


def _site_xy_distance(slab_atoms: Atoms, a: AdsorptionSite, b: AdsorptionSite) -> float:
    """Minimum-image xy distance between two site positions."""
    cell = slab_atoms.cell.array
    a_frac = np.linalg.solve(cell.T, np.array(a.position, dtype=float))
    b_frac = np.linalg.solve(cell.T, np.array(b.position, dtype=float))
    delta_xy = a_frac[:2] - b_frac[:2]
    delta_xy -= np.round(delta_xy)
    vec = delta_xy[0] * cell[0] + delta_xy[1] * cell[1]
    return float(np.linalg.norm(vec))


def _site_type_family(site_type: str) -> str:
    """Coarse type used when merging detector results."""
    lowered = site_type.lower()
    if "bridge" in lowered:
        return "bridge"
    if "hollow" in lowered or lowered in {"fcc", "hcp", "3fold", "4fold", "5fold", "6fold"}:
        return "hollow"
    if lowered in {"top", "ontop"}:
        return "top"
    return lowered


def _site_types_compatible(a: AdsorptionSite, b: AdsorptionSite) -> bool:
    """Only merge detector candidates that represent the same site family."""
    return _site_type_family(a.site_type) == _site_type_family(b.site_type)


def _merge_adsorption_sites(
    slab_atoms: Atoms,
    catkit_sites: list[AdsorptionSite],
    pymatgen_sites: list[AdsorptionSite],
    acat_sites: list[AdsorptionSite] | None = None,
    distance_tolerance: float = 0.35,
) -> list[AdsorptionSite]:
    """Merge nearby site-detector candidates, preserving source metadata."""
    for site in catkit_sites:
        if not site.sources:
            site.sources = ["catkit"]
    for site in pymatgen_sites:
        if not site.sources:
            site.sources = ["pymatgen"]
    for site in acat_sites or []:
        if not site.sources:
            site.sources = ["acat"]

    merged = [site for site in catkit_sites]
    for candidate in [*pymatgen_sites, *(acat_sites or [])]:
        match = None
        for site in merged:
            if (
                _site_types_compatible(site, candidate)
                and _site_xy_distance(slab_atoms, site, candidate) <= distance_tolerance
            ):
                match = site
                break
        if match is None:
            merged.append(candidate)
            continue

        for source in candidate.sources:
            if source not in match.sources:
                match.sources.append(source)
        match.priority = min(match.priority, candidate.priority)
        if not match.surface_atom_idx and candidate.surface_atom_idx:
            match.surface_atom_idx = candidate.surface_atom_idx

    for site in merged:
        site.sources = sorted(
            set(site.sources),
            key=lambda source: SITE_SOURCE_ORDER.index(source)
            if source in SITE_SOURCE_ORDER
            else 99,
        )
        _annotate_site_validation(site)
    return merged


def _annotate_site_validation(site: AdsorptionSite) -> AdsorptionSite:
    """Attach simple cross-backend confidence metadata to a site candidate."""
    sources = set(site.sources)
    notes: list[str] = []

    detector_sources = sources.intersection({"catkit", "pymatgen", "acat"})
    if len(detector_sources) >= 3:
        score = 1.0
        notes.append("catkit+pymatgen+acat_agree")
    elif {"catkit", "pymatgen"} <= sources:
        score = 1.0
        notes.append("catkit+pymatgen_agree")
    elif len(detector_sources) == 2:
        score = 0.90
        notes.append("+".join(sorted(detector_sources, key=SITE_SOURCE_ORDER.index)) + "_agree")
    elif "catkit" in sources:
        score = 0.72
        notes.append("catkit_only")
    elif "pymatgen" in sources:
        score = 0.68
        notes.append("pymatgen_only")
    elif "acat" in sources:
        score = 0.70
        notes.append("acat_only")
    elif "autoadsorbate" in sources:
        score = 0.80
        notes.append("autoadsorbate_surface_sample")
    else:
        score = 0.50
        notes.append("unknown_site_source")

    if site.site_type == "hollow":
        notes.append("generic_hollow")
    elif site.site_type in {"fcc_hollow", "hcp_hollow"}:
        notes.append("subsurface_classified_hollow")

    site.validation_score = score
    site.validation_notes = notes
    return site


# ---------------------------------------------------------------------------
# Adsorbate geometry library
# ---------------------------------------------------------------------------

def _orient_binding_atom_down(mol: Atoms) -> Atoms:
    """Reorient a molecule so the binding atom (index 0) faces the surface.

    Translates the binding atom to the origin, then rigidly rotates the
    molecule so the sum of unit vectors toward the binding atom's BONDED
    neighbors points along +z. Pointing the bonded framework up is the
    lone-pair-down heuristic: for methanol-O the C and H neighbors tilt up
    symmetrically (a plain centroid rotation leaves the hydroxyl H ~0.3 A
    below the oxygen); for NH3-N the hydrogens form the upright umbrella; for
    diatomics the bond aligns exactly with z. When the neighbor sum is
    degenerate (linear symmetric CO2 bound through the central C) the
    molecular axis is laid flat instead, so no terminal atom points into the
    surface. The old z-flip-only logic let tilted RDKit conformers put the
    wrong atom closest to the surface.
    """
    mol = mol.copy()
    mol.positions -= mol.positions[0].copy()
    if len(mol) == 1:
        return mol

    from ase.data import covalent_radii

    radii = covalent_radii[mol.numbers]
    deltas = mol.positions[1:]
    distances = np.linalg.norm(deltas, axis=1)
    cutoffs = 1.25 * (radii[0] + radii[1:]) + 1e-6
    bonded = deltas[(distances > 1e-3) & (distances <= cutoffs)]
    if len(bonded) == 0:
        bonded = deltas  # no covalent neighbor found: fall back to all atoms

    direction = (bonded / np.linalg.norm(bonded, axis=1)[:, None]).sum(axis=0)
    norm = float(np.linalg.norm(direction))
    if norm > 0.05:
        mol.rotate(direction, (0.0, 0.0, 1.0), center=(0.0, 0.0, 0.0))
    else:
        # Symmetric/linear about the binding atom: lay the long axis in-plane.
        extents = np.linalg.norm(deltas, axis=1)
        axis = deltas[int(np.argmax(extents))]
        if float(np.linalg.norm(axis)) > 1e-3:
            mol.rotate(axis, (1.0, 0.0, 0.0), center=(0.0, 0.0, 0.0))
    return mol


def _expected_binding_element(adsorbate: str) -> str | None:
    """Configured binding element for a known adsorbate label, if any."""
    token = str(adsorbate or "").strip()
    for key in (token, token.upper(), token.lower()):
        if key in ADSORBATE_BINDING_ATOMS:
            return str(ADSORBATE_BINDING_ATOMS[key])
    return None


def _ensure_binding_atom_first(mol: Atoms, expected: str | None) -> Atoms:
    """Permute the molecule so the expected binding element sits at index 0.

    Index 0 is the binding-atom contract used by every placement path. When a
    builder returns a different leading element (e.g. an O-marked surrogate for
    NO, which must bind N-down), move the first atom of the expected element to
    the front and re-orient. No-op when already correct or when the expected
    element is absent.
    """
    if not expected or len(mol) == 0 or mol[0].symbol == expected:
        return mol
    symbols = mol.get_chemical_symbols()
    try:
        target = symbols.index(expected)
    except ValueError:
        return mol
    order = [target] + [i for i in range(len(mol)) if i != target]
    reordered = mol[order]
    reordered.info.update(mol.info)
    reordered.info["binding_atom_reordered"] = True
    return _orient_binding_atom_down(reordered)


ADSORBATE_BUILD_INFO_KEYS = (
    "adsorbate_builder",
    "adsorbate_input",
    "adsorbate_smiles",
    "adsorbate_smiles_source",
    "adsorbate_surrogate_smiles",
    "adsorbate_fallback_reason",
    # Backward-compatible aliases used by older tests and notebooks.
    "smiles",
    "surrogate_smiles",
)


def _set_adsorbate_build_info(
    atoms: Atoms,
    *,
    builder: str,
    adsorbate_input: str | None = None,
    smiles: str | None = None,
    smiles_source: str | None = None,
    surrogate_smiles: str | None = None,
    fallback_reason: str | None = None,
) -> Atoms:
    """Attach builder provenance to an adsorbate geometry."""
    atoms = atoms.copy()
    atoms.info["adsorbate_builder"] = builder
    if adsorbate_input:
        atoms.info["adsorbate_input"] = adsorbate_input
    if smiles:
        atoms.info["adsorbate_smiles"] = smiles
        atoms.info["smiles"] = smiles
    if smiles_source:
        atoms.info["adsorbate_smiles_source"] = smiles_source
    if surrogate_smiles:
        atoms.info["adsorbate_surrogate_smiles"] = surrogate_smiles
        atoms.info["surrogate_smiles"] = surrogate_smiles
    if fallback_reason:
        atoms.info["adsorbate_fallback_reason"] = fallback_reason
    return atoms


def _copy_adsorbate_build_info(result_atoms: Atoms, ads_atoms: Atoms) -> Atoms:
    """Copy adsorbate builder provenance onto the placed slab+adsorbate structure."""
    for key in ADSORBATE_BUILD_INFO_KEYS:
        if key in ads_atoms.info:
            result_atoms.info[key] = ads_atoms.info[key]
    result_atoms.info.setdefault("adsorbate_builder", ads_atoms.info.get("adsorbate_builder", "unknown"))
    return result_atoms


def _normalize_ase_adsorbate_info(atoms: Atoms) -> Atoms:
    """Convert ASE's nested adsorbate_info dict to extxyz-safe JSON metadata."""
    raw = atoms.info.pop("adsorbate_info", None)
    if raw is not None:
        atoms.info["ase_adsorbate_info_json"] = json.dumps(_safe_jsonable(raw), sort_keys=True, default=str)
    return atoms


def _source_site_metadata(site: AdsorptionSite, placed_site: AdsorptionSite | None = None) -> dict:
    metadata = {
        "site_type": site.site_type,
        "position": [float(v) for v in np.array(site.position, dtype=float).tolist()],
        "surface_atom_indices": [int(idx) for idx in site.surface_atom_idx],
        "sources": list(site.sources),
        "validation_score": float(site.validation_score),
        "validation_notes": list(site.validation_notes),
        "priority": int(site.priority),
    }
    if placed_site is not None:
        metadata["placed_position"] = [
            float(v) for v in np.array(placed_site.position, dtype=float).tolist()
        ]
    return metadata


def _annotate_adsorption_metadata(
    atoms: Atoms,
    *,
    n_slab: int,
    adsorbate: str,
    site: AdsorptionSite,
    placed_site: AdsorptionSite | None = None,
) -> Atoms:
    """Store compact site/adsorbate metadata using ASE atom indices."""
    adsorbate_indices = list(range(n_slab, len(atoms)))
    anchor_index = adsorbate_indices[0] if adsorbate_indices else None
    source_site = _source_site_metadata(site, placed_site=placed_site)
    atoms.info["source_site_json"] = json.dumps(source_site, sort_keys=True)
    atoms.info["source_site_type"] = site.site_type
    atoms.info["source_site_position_json"] = json.dumps(source_site["position"])
    atoms.info["source_site_surface_atom_indices_json"] = json.dumps(source_site["surface_atom_indices"])
    atoms.info["source_site_sources_json"] = json.dumps(source_site["sources"])
    atoms.info["source_site_validation_score"] = float(site.validation_score)
    atoms.info.setdefault("adsorbate_input", adsorbate)
    atoms.info["adsorbate_atom_indices_json"] = json.dumps(adsorbate_indices)
    if anchor_index is not None:
        atoms.info["adsorbate_anchor_index"] = int(anchor_index)
    atoms.info["adsorbate_metadata_json"] = json.dumps(
        {
            "atom_indices": adsorbate_indices,
            "anchor_index": anchor_index,
            "formula": atoms[adsorbate_indices].get_chemical_formula() if adsorbate_indices else "",
            "input": adsorbate,
            "builder": atoms.info.get("adsorbate_builder"),
            "smiles": atoms.info.get("adsorbate_smiles"),
            "smiles_source": atoms.info.get("adsorbate_smiles_source"),
        },
        sort_keys=True,
        default=str,
    )
    return atoms


def _check_post_placement_distance(atoms: Atoms) -> Atoms:
    check = check_min_distance(atoms, threshold=MIN_PLACEMENT_DISTANCE)
    atoms.info["min_distance"] = float(check.min_distance)
    atoms.info["min_distance_threshold"] = float(check.threshold)
    atoms.info["min_distance_passed"] = bool(check.passed)
    if not check.passed:
        raise ValueError(
            f"close atomic contact detected after adsorbate placement: "
            f"{check.min_distance:.3f} Å between atoms {check.atom_i}-{check.atom_j} "
            f"(< {check.threshold:.2f} Å)"
        )
    return atoms


_BINDING_CONTACT_TOLERANCE_A = 0.25


def _annotate_binding_contact(atoms: Atoms, n_slab: int, adsorbate: str) -> Atoms:
    """Verify the intended binding atom is what actually touches the surface.

    The min-distance guard only catches overlaps; it lets a tilted conformer
    whose methyl hydrogen sits below the binding oxygen pass silently. This gate
    finds the adsorbate atom closest to the slab (MIC) and records whether it is
    the anchor (index ``n_slab``), the expected binding element, or within a
    small tolerance of the anchor's own surface distance. Mismatches are
    annotated as a warning — not rejected, since the geometry may still be a
    usable relaxation starting point — so the harness/agent can see and report
    them instead of silently shipping a wrong-atom-down structure.
    """
    n_total = len(atoms)
    if not (0 < n_slab < n_total):
        return atoms
    expected = _expected_binding_element(adsorbate) or atoms[n_slab].symbol
    slab_indices = list(range(n_slab))
    anchor_distance: float | None = None
    closest_index = n_slab
    closest_distance = float("inf")
    for index in range(n_slab, n_total):
        distance = float(np.min(atoms.get_distances(index, slab_indices, mic=True)))
        if index == n_slab:
            anchor_distance = distance
        if distance < closest_distance:
            closest_distance = distance
            closest_index = index
    closest_element = atoms[closest_index].symbol
    # A flat-lying molecule on a hollow site (CO2) legitimately has a terminal
    # atom laterally nearer to a surface atom than the anchor over the hollow
    # center; height, not 3D proximity, decides mis-orientation. The anchor
    # being (near-)lowest in z therefore also counts as correct.
    ads_z = atoms.positions[n_slab:, 2]
    anchor_is_lowest = bool(ads_z[0] <= ads_z.min() + 0.15)
    ok = (
        closest_index == n_slab
        or closest_element == expected
        or anchor_is_lowest
        or (anchor_distance is not None
            and anchor_distance - closest_distance <= _BINDING_CONTACT_TOLERANCE_A)
    )
    atoms.info["binding_expected_element"] = expected
    atoms.info["binding_contact_index"] = int(closest_index)
    atoms.info["binding_contact_element"] = closest_element
    atoms.info["binding_contact_distance"] = round(closest_distance, 4)
    atoms.info["binding_anchor_distance"] = round(float(anchor_distance or 0.0), 4)
    atoms.info["binding_contact_ok"] = bool(ok)
    if not ok:
        atoms.info["binding_contact_warning"] = (
            f"closest surface contact is {closest_element} (atom {closest_index}, "
            f"{closest_distance:.2f} Å) instead of the intended binding atom "
            f"{expected} (anchor at {anchor_distance:.2f} Å); the adsorbate may "
            "be mis-oriented."
        )
    return atoms


def _initial_magmoms_or_none(atoms: Atoms) -> list[float] | None:
    if "initial_magmoms" not in getattr(atoms, "arrays", {}):
        return None
    values = atoms.get_initial_magnetic_moments()
    if len(values) != len(atoms):
        return None
    return [float(v) for v in values]


def _preserve_slab_magmoms_zero_adsorbate(
    result_atoms: Atoms,
    slab_atoms: Atoms,
    n_slab: int,
) -> Atoms:
    """Keep slab initial magmoms and force adsorbate initial magmoms to zero."""
    if n_slab < 0 or n_slab > len(result_atoms):
        return result_atoms

    slab_magmoms = _initial_magmoms_or_none(slab_atoms)
    result_magmoms = _initial_magmoms_or_none(result_atoms)
    if slab_magmoms is None and result_magmoms is None:
        return result_atoms

    values = np.zeros(len(result_atoms), dtype=float)
    if slab_magmoms is not None and len(slab_magmoms) >= n_slab:
        values[:n_slab] = slab_magmoms[:n_slab]
    elif result_magmoms is not None and len(result_magmoms) >= n_slab:
        values[:n_slab] = result_magmoms[:n_slab]

    result_atoms.set_initial_magnetic_moments(values)
    return result_atoms


def _fixed_slab_indices_from_constraints(atoms: Atoms, n_slab: int) -> set[int]:
    fixed: set[int] = set()
    for constraint in atoms.constraints:
        if isinstance(constraint, FixAtoms):
            fixed.update(
                int(idx)
                for idx in constraint.get_indices()
                if 0 <= int(idx) < n_slab
            )
    return fixed


def tag_slab_and_adsorbate(
    atoms: Atoms,
    n_slab: int,
    site_indices: list[int] | None = None,
) -> Atoms:
    """Tag combined slab+adsorbate structures for downstream relaxation policy.

    Tag convention:
      - 0: fixed slab atoms
      - 1: relaxable slab atoms
      - 2: adsorbate atoms

    Adsorption-site anchor atoms are stored separately in metadata because
    overloading tags with a site marker would erase fixed/relaxable slab state.
    """
    if n_slab < 0 or n_slab > len(atoms):
        raise ValueError(f"n_slab={n_slab} outside atom range 0..{len(atoms)}")

    tags = np.full(len(atoms), ADSORBATE_TAG, dtype=int)
    tags[:n_slab] = RELAXABLE_SLAB_TAG
    for idx in _fixed_slab_indices_from_constraints(atoms, n_slab):
        tags[idx] = FIXED_SLAB_TAG
    atoms.set_tags(tags)
    atoms.info["fixed_slab_tag"] = FIXED_SLAB_TAG
    atoms.info["relaxable_slab_tag"] = RELAXABLE_SLAB_TAG
    atoms.info["adsorbate_tag"] = ADSORBATE_TAG
    atoms.info["slab_atom_count"] = int(n_slab)
    atoms.info["adsorbate_atom_count"] = int(len(atoms) - n_slab)
    if site_indices is not None:
        clean_site_indices = sorted({int(idx) for idx in site_indices if 0 <= int(idx) < n_slab})
        atoms.info["adsorption_site_indices"] = ",".join(str(idx) for idx in clean_site_indices)
        atoms.info["adsorption_site_atom_count"] = len(clean_site_indices)
    return atoms


def _serialize_acat_site(site: dict) -> dict:
    """Return compact JSON-safe ACAT coverage metadata."""
    keep_keys = (
        "site",
        "morphology",
        "position",
        "indices",
        "bonding_index",
        "bond_length",
        "adsorbate",
        "fragment",
        "adsorbate_indices",
        "fragment_indices",
        "occupied",
        "dentate",
    )
    return {key: _safe_jsonable(site.get(key)) for key in keep_keys if key in site}


def _annotate_acat_coverage(
    atoms: Atoms,
    n_slab: int,
    *,
    dmax: float = 3.0,
) -> Atoms:
    """Annotate placed structures with ACAT coverage recognition metadata."""
    if n_slab <= 0 or n_slab >= len(atoms):
        return atoms

    slab_atoms = atoms[:n_slab].copy()
    slab_atoms.set_pbc([True, True, False])
    if not _is_acat_compatible_clean_slab(slab_atoms):
        return atoms

    try:
        from acat.adsorbate_coverage import SlabAdsorbateCoverage
        from acat.adsorption_sites import SlabAdsorptionSites
        from acat.settings import CustomSurface

        surface = CustomSurface(slab_atoms, n_layers=None)
        adsorption_sites = SlabAdsorptionSites(
            slab_atoms,
            surface=surface,
            composition_effect=False,
            label_sites=False,
        )
        adsorbate_indices = adsorbate_indices_from_tags(atoms)
        if not adsorbate_indices:
            adsorbate_indices = list(range(n_slab, len(atoms)))
        coverage = SlabAdsorbateCoverage(
            atoms,
            adsorption_sites=adsorption_sites,
            adsorbate_indices=adsorbate_indices,
            dmax=dmax,
        )
        occupied_sites = coverage.get_sites(occupied=True)
        atoms.info["acat_coverage_status"] = "ok"
        atoms.info["acat_coverage"] = float(coverage.get_coverage())
        atoms.info["acat_occupied_site_count"] = int(len(occupied_sites))
        atoms.info["acat_adsorbate_count"] = int(len(coverage.get_adsorbates()))
        atoms.info["acat_occupied_sites_json"] = json.dumps(
            [_serialize_acat_site(site) for site in occupied_sites],
            sort_keys=True,
            default=str,
        )
        atoms.info["acat_adsorbates_json"] = json.dumps(
            _safe_jsonable(coverage.get_adsorbates()),
            sort_keys=True,
            default=str,
        )
    except Exception as exc:
        atoms.info["acat_coverage_status"] = "failed"
        atoms.info["acat_coverage_error"] = str(exc)
    return atoms


def adsorbate_indices_from_tags(atoms: Atoms) -> list[int]:
    """Return atom indices tagged as adsorbate atoms."""
    return np.where(atoms.get_tags() == ADSORBATE_TAG)[0].astype(int).tolist()


def _site_type_from_connectivity(
    slab_atoms: Atoms,
    position: np.ndarray,
    topology: list[int],
    connectivity: int,
) -> str:
    if connectivity == 1:
        return "top"
    if connectivity == 2:
        return "bridge"
    if connectivity == 3:
        layers = _detect_z_layers(np.array(slab_atoms.positions[:, 2], dtype=float))
        subsurface_indices = layers[-2] if len(layers) >= 2 else []
        return _classify_threefold_hollow(slab_atoms, position, subsurface_indices)
    return "hollow"


def _safe_jsonable(value):
    if isinstance(value, np.ndarray):
        return [_safe_jsonable(v) for v in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(k): _safe_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_jsonable(v) for v in value]
    return value


def _prepare_autoadsorbate_surface_candidate(
    atoms: Atoms,
    slab_atoms: Atoms,
    *,
    adsorbate_input: str,
    smiles: str,
    smiles_source: str | None,
    surrogate_smiles: str,
) -> tuple[AdsorptionSite, Atoms]:
    """Normalize an AutoAdsorbate populated structure into app conventions."""
    result = atoms.copy()
    fragments = np.array(result.arrays.get("fragments", []), dtype=int)
    n_slab = len(slab_atoms)
    if fragments.size == len(result) and fragments.max(initial=0) > 0:
        ads_fragment = int(fragments.max())
        ads_indices = np.where(fragments == ads_fragment)[0].astype(int).tolist()
        slab_indices = [idx for idx in range(len(result)) if idx not in set(ads_indices)]
        if slab_indices != list(range(len(slab_indices))) or len(slab_indices) != n_slab:
            result = result[slab_indices + ads_indices]
            n_slab = len(slab_indices)

    result.set_cell(slab_atoms.cell)
    result.set_pbc(slab_atoms.pbc)
    result.set_constraint(slab_atoms.constraints)
    _preserve_slab_magmoms_zero_adsorbate(result, slab_atoms, n_slab)

    ads_info = _safe_jsonable(result.info.pop("adsorbate_info", {}) or {})
    site_info = ads_info.get("site", {}) if isinstance(ads_info, dict) else {}
    position = np.array(site_info.get("coordinates", [0.0, 0.0, 0.0]), dtype=float)
    topology = [int(idx) for idx in site_info.get("topology", []) if int(idx) < n_slab]
    connectivity = int(site_info.get("connectivity", len(topology) or 1))
    site_type = _site_type_from_connectivity(slab_atoms, position, topology, connectivity)

    site = AdsorptionSite(
        site_type=site_type,
        position=position,
        surface_atom_idx=topology,
        priority=_get_priority_for_site(adsorbate_input, site_type),
        placement_method="autoadsorbate_surface",
        catkit_index=-1,
        sources=["autoadsorbate"],
    )
    _annotate_site_validation(site)

    result.info["adsorbate_builder"] = "autoadsorbate_surface"
    result.info["adsorbate_input"] = adsorbate_input
    result.info["adsorbate_smiles"] = smiles
    result.info["smiles"] = smiles
    if smiles_source:
        result.info["adsorbate_smiles_source"] = smiles_source
    result.info["adsorbate_surrogate_smiles"] = surrogate_smiles
    result.info["surrogate_smiles"] = surrogate_smiles
    result.info["adsorbate_placement_backend"] = "autoadsorbate_surface"
    result.info["autoadsorbate_mdf"] = float(ads_info.get("mdf", 0.0) or 0.0)
    result.info["autoadsorbate_site_connectivity"] = connectivity
    result.info["autoadsorbate_sampled_smiles"] = ads_info.get("smiles", surrogate_smiles)
    result.info["autoadsorbate_adsorbate_formula"] = ads_info.get("adsorbate_formula")
    result.info["autoadsorbate_adsorbate_info_json"] = json.dumps(ads_info, sort_keys=True, default=str)

    source_site = site
    result, placed_site = _center_placed_structure_xy(result, source_site)
    tag_slab_and_adsorbate(result, n_slab, source_site.surface_atom_idx)
    _annotate_adsorption_metadata(
        result,
        n_slab=n_slab,
        adsorbate=adsorbate_input,
        site=source_site,
        placed_site=placed_site,
    )
    result = _wrap_adsorbate_into_cell(result, n_slab)
    result = _annotate_binding_contact(result, n_slab, adsorbate_input)
    result = _annotate_acat_coverage(result, n_slab)
    return source_site, _check_post_placement_distance(result)


def _generate_autoadsorbate_surface_structures(
    slab_atoms: Atoms,
    adsorbate: str,
    *,
    max_structures: int | None,
    height: float | None,
) -> list[tuple[AdsorptionSite, Atoms]]:
    """Use AutoAdsorbate Surface/Fragment to sample sites, conformers, rotations."""
    smiles_resolution = resolve_adsorbate_smiles(adsorbate)
    smiles = smiles_resolution.smiles
    if not _should_try_autoadsorbate_surface(adsorbate, smiles, height):
        return []

    from autoadsorbate import Fragment, Surface

    slab_for_auto = slab_atoms.copy()
    slab_for_auto.set_pbc([True, True, False])
    slab_for_auto.wrap()

    candidates: list[tuple[AdsorptionSite, Atoms]] = []
    seen_keys: set[tuple] = set()
    binding_element = _expected_binding_element(adsorbate)
    for surrogate_smiles in _marked_smiles_candidates(smiles or ""):
        with contextlib.redirect_stdout(io.StringIO()):
            fragment = Fragment(
                input=surrogate_smiles,
                to_initialize=AUTOADSORBATE_CONFORMERS_TO_INITIALIZE,
                random_seed=2104,
                sort_conformers=True,
                prune_rms_thresh=0.5,
            )
        if binding_element:
            # Skip surrogates that bind through the wrong end (e.g. O-marked
            # NO). If every candidate mismatches, this path yields nothing and
            # the caller falls back to classic placement, where the central
            # binding-atom normalization enforces the configured element.
            try:
                probe = _strip_surrogate_markers(fragment.get_conformer(0))
                if probe[0].symbol != binding_element:
                    continue
            except Exception:
                pass
        surface = Surface(
            slab_for_auto,
            precision=AUTOADSORBATE_SURFACE_PRECISION,
            touch_sphere_size=AUTOADSORBATE_TOUCH_SPHERE_SIZE,
            mode="slab",
        )
        try:
            surface.sym_reduce()
        except Exception:
            # Keep AutoAdsorbate's raw shrinkwrap sites if ASE symmetry
            # comparison fails for a low-symmetry or unusual slab.
            pass
        with contextlib.redirect_stdout(io.StringIO()):
            populated = surface.get_populated_sites(
                fragment,
                site_index="all",
                sample_rotation=True,
                mode="heuristic",
                conformers_per_site_cap=AUTOADSORBATE_CONFORMERS_PER_SITE_CAP,
                overlap_thr=AUTOADSORBATE_OVERLAP_THRESHOLD,
                verbose=False,
            )
        for atoms in populated:
            site, normalized = _prepare_autoadsorbate_surface_candidate(
                atoms,
                slab_for_auto,
                adsorbate_input=adsorbate,
                smiles=smiles or surrogate_smiles,
                smiles_source=smiles_resolution.source,
                surrogate_smiles=surrogate_smiles,
            )
            key = (
                site.site_type,
                tuple(round(float(v), 3) for v in site.position[:2]),
                tuple(normalized.get_chemical_symbols()[len(slab_for_auto):]),
                round(float(normalized.info.get("autoadsorbate_mdf", 0.0)), 3),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            candidates.append((site, normalized))

    candidates.sort(
        key=lambda item: (
            item[0].priority,
            -float(item[1].info.get("autoadsorbate_mdf", 0.0)),
            item[0].site_type,
            float(item[0].position[2]),
        )
    )
    return candidates[:max_structures] if max_structures is not None else candidates


@dataclass(frozen=True)
class SmilesResolution:
    smiles: str | None
    source: str | None = None
    error: str | None = None


def resolve_adsorbate_smiles(adsorbate: str) -> SmilesResolution:
    """Resolve an adsorbate label, raw SMILES, or OPSIN name to SMILES.

    Resolution order:
    1. Explicit ``smiles:<SMILES>`` input.
    2. Local aliases from ``config.ADSORBATE_SMILES``.
    3. Raw RDKit-parseable SMILES.
    4. OPSIN/py2opsin chemical-name conversion.
    """
    token = adsorbate.strip()
    if not token:
        return SmilesResolution(None)

    if token.lower().startswith("smiles:"):
        smiles = token.split(":", 1)[1].strip()
        return SmilesResolution(smiles or None, "input_smiles" if smiles else None)

    for key in (token, token.upper(), token.lower()):
        if key in ADSORBATE_SMILES:
            return SmilesResolution(ADSORBATE_SMILES[key], "configured_alias")

    try:
        from rdkit import Chem
        from rdkit import RDLogger
    except ImportError:
        Chem = None

    if Chem is not None:
        RDLogger.DisableLog("rdApp.error")
        try:
            mol = Chem.MolFromSmiles(token)
        finally:
            RDLogger.EnableLog("rdApp.error")
        if mol is not None:
            return SmilesResolution(Chem.MolToSmiles(mol), "raw_smiles")

    try:
        from slabuilder.opsin import name_to_smiles
    except Exception as exc:
        return SmilesResolution(None, error=f"OPSIN unavailable: {exc}")

    smiles, error = name_to_smiles(token)
    if smiles:
        return SmilesResolution(smiles, "opsin")

    return SmilesResolution(None, error=error)


def adsorbate_to_smiles(adsorbate: str) -> str | None:
    """Return only the SMILES string from ``resolve_adsorbate_smiles``."""
    return resolve_adsorbate_smiles(adsorbate).smiles


def _has_known_smiles_label(adsorbate: str) -> bool:
    """Return True if adsorbate is a configured SMILES alias."""
    token = adsorbate.strip()
    return any(key in ADSORBATE_SMILES for key in (token, token.upper(), token.lower()))


def _should_try_autoadsorbate_first(adsorbate: str, smiles: str | None) -> bool:
    """Decide whether to prefer AutoAdsorbate over ASE/manual geometry tables."""
    if not smiles:
        return False

    token = adsorbate.strip()
    if token.lower().startswith("smiles:"):
        return True

    if any(key in AUTOADSORBATE_FIRST_ADSORBATES for key in (token, token.upper(), token.lower())):
        return True

    # Raw RDKit-parseable SMILES, not a configured label.
    return not _has_known_smiles_label(adsorbate)


def _marked_smiles_candidates(smiles: str) -> list[str]:
    """Return AutoAdsorbate-compatible surrogate-SMILES candidates."""
    if smiles.startswith("Cl") or smiles.startswith("S1S"):
        return [smiles]

    candidates: list[str] = []
    try:
        from autoadsorbate import get_marked_smiles
        candidates = get_marked_smiles([smiles], attack_atoms=list(AUTOADSORBATE_ATTACK_ATOMS))
    except Exception:
        candidates = []

    # AutoAdsorbate can still build an unmarked SMILES. In that case the
    # first atom becomes the fallback binding atom.
    unique: list[str] = []
    for candidate in candidates or [smiles]:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def _should_try_autoadsorbate_surface(
    adsorbate: str,
    smiles: str | None,
    height: float | None,
) -> bool:
    """Return True when AutoAdsorbate surface population can be tried safely."""
    if not AUTOADSORBATE_SURFACE_ENABLED or height is not None or not smiles:
        return False

    token = adsorbate.strip()
    # Binding-override species (CO, NO) must keep their hand-tuned geometry:
    # RDKit reads "CO" as methanol and get_marked_smiles mangles "N=O" to "O"
    # (water), so the SMILES surface path is wrong for them by construction.
    if _build_binding_override_adsorbate(token.upper()) is not None:
        return False

    # Keep simple atomic/radical labels on deterministic local geometries.
    if token in RADICAL_ADSORBATES and not _has_known_smiles_label(token):
        return False

    return _should_try_autoadsorbate_first(adsorbate, smiles)


def _strip_surrogate_markers(atoms: Atoms) -> Atoms:
    """Remove AutoAdsorbate marker atoms while keeping the binding atom first."""
    if len(atoms) >= 1 and atoms[0].symbol == "Cl":
        stripped = atoms[1:].copy()
    elif len(atoms) >= 2 and atoms[0].symbol == "S" and atoms[1].symbol == "S":
        stripped = atoms[2:].copy()
    else:
        stripped = atoms.copy()

    if len(stripped) == 0:
        raise ValueError("Surrogate SMILES did not leave any real adsorbate atoms.")

    # Same centroid-up orientation as every other builder, so a tilted RDKit
    # conformer cannot leave a non-binding atom below the binding atom.
    return _orient_binding_atom_down(stripped)


def _heavy_atom_formula(symbols) -> dict[str, int]:
    """Element counts excluding hydrogen (conformer H counts are RDKit's job)."""
    counts: dict[str, int] = {}
    for symbol in symbols:
        if symbol != "H":
            counts[symbol] = counts.get(symbol, 0) + 1
    return counts


def _smiles_heavy_atom_formula(smiles: str) -> dict[str, int] | None:
    """Heavy-atom composition implied by a SMILES string, or None if unparsable."""
    try:
        from rdkit import Chem
    except ImportError:
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return _heavy_atom_formula(atom.GetSymbol() for atom in mol.GetAtoms())


def _build_adsorbate_atoms_from_smiles(
    smiles: str,
    *,
    adsorbate_input: str | None = None,
    smiles_source: str | None = None,
    binding_element: str | None = None,
) -> Atoms:
    """Build an adsorbate from SMILES through AutoAdsorbate/RDKit.

    Surrogate candidates are tried in marker order, but when a
    ``binding_element`` is configured (e.g. NO must bind N-down) the first
    candidate whose stripped binding atom matches that element wins. The global
    ``attack_atoms`` priority alone picks the wrong end for such species (its
    O-before-N order would bind NO through oxygen). When no candidate matches,
    the first buildable one is used and the mismatch recorded as
    ``fallback_reason``.
    """
    try:
        from autoadsorbate import Fragment
    except ImportError as exc:
        raise ImportError(
            "SMILES-based adsorbate generation requires autoadsorbate and rdkit."
        ) from exc

    expected_formula = _smiles_heavy_atom_formula(smiles)
    last_error: Exception | None = None
    fallback: tuple[Atoms, str] | None = None
    for surrogate_smiles in _marked_smiles_candidates(smiles):
        try:
            fragment = Fragment(
                input=surrogate_smiles,
                to_initialize=10,
                random_seed=2104,
                prune_rms_thresh=0.5,
            )
            atoms = _strip_surrogate_markers(fragment.get_conformer(0))
        except Exception as exc:
            last_error = exc
            continue
        if expected_formula is not None:
            built = _heavy_atom_formula(atoms.get_chemical_symbols())
            if built != expected_formula:
                # Surrogate marking mangled the species (e.g. "N=O" -> "O"
                # rebuilt as water). Never return a different molecule.
                last_error = ValueError(
                    f"surrogate {surrogate_smiles!r} built {built}, expected "
                    f"{expected_formula} from SMILES {smiles!r}"
                )
                continue
        if binding_element and atoms[0].symbol != binding_element:
            if fallback is None:
                fallback = (atoms, surrogate_smiles)
            continue
        return _set_adsorbate_build_info(
            atoms,
            builder="autoadsorbate",
            adsorbate_input=adsorbate_input,
            smiles=smiles,
            smiles_source=smiles_source,
            surrogate_smiles=surrogate_smiles,
        )

    if fallback is not None:
        atoms, surrogate_smiles = fallback
        return _set_adsorbate_build_info(
            atoms,
            builder="autoadsorbate",
            adsorbate_input=adsorbate_input,
            smiles=smiles,
            smiles_source=smiles_source,
            surrogate_smiles=surrogate_smiles,
            fallback_reason=(
                f"no surrogate candidate bound through configured element "
                f"{binding_element!r}; using {atoms[0].symbol!r}"
            ),
        )

    raise ValueError(f"Could not build adsorbate from SMILES {smiles!r}: {last_error}")


def _try_build_adsorbate_atoms_from_smiles(
    smiles: str,
    *,
    adsorbate_input: str | None = None,
    smiles_source: str | None = None,
    binding_element: str | None = None,
) -> tuple[Atoms | None, str | None]:
    """Try AutoAdsorbate and return ``(atoms, error_reason)`` without raising."""
    try:
        return _build_adsorbate_atoms_from_smiles(
            smiles,
            adsorbate_input=adsorbate_input,
            smiles_source=smiles_source,
            binding_element=binding_element,
        ), None
    except Exception as exc:
        return None, str(exc)


def _build_single_atom_adsorbate(adsorbate: str) -> Atoms | None:
    # Single atoms
    single_atoms = {"O", "N", "C", "S", "H"}
    if adsorbate in single_atoms:
        return _set_adsorbate_build_info(
            Atoms(adsorbate, positions=[[0, 0, 0]]),
            builder="manual",
            adsorbate_input=adsorbate,
        )
    return None


def _build_binding_override_adsorbate(adsorbate: str) -> Atoms | None:
    # Molecules where ASE's atom ordering doesn't put the binding atom first.
    # Explicitly define the correct geometry (binding atom at index 0, z=0).
    binding_overrides: dict[str, Atoms] = {
        # C-down convention: C (index 0) binds to surface, O points up.
        # ASE molecule("CO") has O at index 0, which is wrong for C-down.
        "CO": Atoms("CO", positions=[[0, 0, 0], [0, 0, 1.15]]),
        # N-down convention. The SMILES path cannot be trusted here:
        # autoadsorbate's get_marked_smiles("N=O") collapses to "O", which
        # silently builds WATER instead of nitric oxide.
        "NO": Atoms("NO", positions=[[0, 0, 0], [0, 0, 1.154]]),
    }
    if adsorbate in binding_overrides:
        return _set_adsorbate_build_info(
            binding_overrides[adsorbate],
            builder="manual",
            adsorbate_input=adsorbate,
        )
    return None


def _build_ase_adsorbate(
    adsorbate: str,
    smiles: str | None = None,
    smiles_source: str | None = None,
    fallback_reason: str | None = None,
) -> Atoms | None:
    # Try ASE molecule database first
    ase_known = {
        "H2O": "H2O",
        "NH3": "NH3",
        "CO2": "CO2",
        "CH4": "CH4",
        "N2": "N2",
        "O2": "O2",
        "NO": "NO",
        "CH": "CH",
        "NH": "NH",
        "H2S": "SH2",  # g2 names hydrogen sulfide SH2 (S first, the binding atom)
    }
    if adsorbate in ase_known:
        try:
            mol = ase_molecule(ase_known[adsorbate])
            # Ensure binding atom (index 0) points toward the surface:
            # translate so it is at origin, flip z if other atoms are below it.
            return _set_adsorbate_build_info(
                _orient_binding_atom_down(mol),
                builder="ase",
                adsorbate_input=adsorbate,
                smiles=smiles,
                smiles_source=smiles_source,
                fallback_reason=fallback_reason,
            )
        except Exception:
            pass
    return None


def _build_manual_molecular_adsorbate(
    adsorbate: str,
    smiles: str | None = None,
    smiles_source: str | None = None,
    fallback_reason: str | None = None,
) -> Atoms | None:
    # Manual construction for radicals
    manual_geometries: dict[str, Atoms] = {
        # --- Original ---
        "OH": Atoms("OH", positions=[[0, 0, 0], [0, 0, 0.97]]),
        "OOH": Atoms("OOH", positions=[[0, 0, 0], [0, 0, 1.33], [0.95, 0, 1.85]]),
        "SH": Atoms("SH", positions=[[0, 0, 0], [0, 0, 1.34]]),
        "CH3": Atoms("CH3", positions=[
            [0.0, 0.0, 0.0],   # C (binding)
            [0.0, 1.03, 0.63],
            [0.89, -0.51, 0.63],
            [-0.89, -0.51, 0.63],
        ]),
        "CH2": Atoms("CH2", positions=[[0, 0, 0], [0.63, 0, 0.88], [-0.63, 0, 0.88]]),
        # --- NRR intermediates ---
        # NH2: amino radical, N binds, 2H up (sp3-like, ~107° H-N-H)
        "NH2": Atoms("NH2", positions=[
            [0.0, 0.0, 0.0],    # N (binding)
            [0.48, 0.0, 0.84],  # H
            [-0.48, 0.0, 0.84], # H
        ]),
        # NNH: diazenyl radical *N=N-H, terminal N binds, N=N 1.25 Å, N-H 1.02 Å
        "NNH": Atoms("NNH", positions=[
            [0.0, 0.0, 0.0],    # N (binding, terminal)
            [0.0, 0.0, 1.25],   # N
            [0.0, 0.87, 1.72],  # H
        ]),
        # NNH2: *N=NH2, terminal N binds, N=N 1.25 Å
        "NNH2": Atoms("NNH2", positions=[
            [0.0, 0.0, 0.0],     # N (binding, terminal)
            [0.0, 0.0, 1.25],    # N
            [0.48, 0.0, 1.85],   # H
            [-0.48, 0.0, 1.85],  # H
        ]),
        # NHNH: diazene HN=NH, one N binds (η¹), N=N 1.25 Å, N-H 1.02 Å
        "NHNH": Atoms("NHNH", positions=[
            [0.0, 0.0, 0.0],     # N (binding)
            [0.0, 0.0, 1.25],    # N
            [-0.87, 0.0, -0.47], # H on binding N (pointing down/away)
            [0.87, 0.0, 1.72],   # H on remote N
        ]),
        # NHNH2: *NH-NH2, N-N 1.45 Å (single bond)
        "NHNH2": Atoms("NHNH2", positions=[
            [0.0, 0.0, 0.0],     # N (binding, NH end)
            [0.0, 0.0, 1.45],    # N (NH2)
            [-0.87, 0.0, -0.47], # H on binding N
            [0.48, 0.0, 2.09],   # H on NH2
            [-0.48, 0.0, 2.09],  # H on NH2
        ]),
        # NH2NH2: hydrazine *NH2-NH2, N-N 1.45 Å
        "NH2NH2": Atoms("NH2NH2", positions=[
            [0.0, 0.0, 0.0],     # N (binding)
            [0.0, 0.0, 1.45],    # N
            [0.48, 0.83, -0.36], # H on binding N
            [-0.48, -0.83, -0.36], # H on binding N
            [0.48, 0.83, 1.81],  # H on remote N
            [-0.48, -0.83, 1.81],  # H on remote N
        ]),
        # --- NOXRR intermediates ---
        # NO2: nitrogen dioxide, N binds, N=O 1.20 Å, O-N-O ~134°
        "NO2": Atoms("NO2", positions=[
            [0.0, 0.0, 0.0],    # N (binding)
            [0.98, 0.0, 0.72],  # O
            [-0.98, 0.0, 0.72], # O
        ]),
        # NO3: nitrate, N binds, N-O ~1.26 Å, planar
        "NO3": Atoms("NO3", positions=[
            [0.0, 0.0, 0.0],     # N (binding)
            [0.0, 1.09, 0.63],   # O
            [0.95, -0.55, 0.63], # O
            [-0.95, -0.55, 0.63],# O
        ]),
        # NOH: *N-OH, N binds, N-O 1.40 Å, O-H 0.97 Å
        "NOH": Atoms("NOH", positions=[
            [0.0, 0.0, 0.0],    # N (binding)
            [0.0, 0.0, 1.40],   # O
            [0.0, 0.78, 1.87],  # H
        ]),
        # HNO: nitroxyl *NH=O, N binds, N=O 1.21 Å, N-H 1.06 Å
        "HNO": Atoms("HNO", positions=[
            [0.0, 0.0, 0.0],    # N (binding)
            [0.97, 0.0, 0.70],  # O
            [-0.53, 0.0, -0.87],# H (pointing down)
        ]),
        # NHOH: *NH-OH, N binds, N-O 1.40 Å
        "NHOH": Atoms("NHOH", positions=[
            [0.0, 0.0, 0.0],    # N (binding)
            [0.0, 0.0, 1.40],   # O
            [-0.87, 0.0, -0.47],# H on N
            [0.78, 0.0, 1.87],  # H on O
        ]),
        # ONO: O-bound nitrite *O-N=O, O binds
        "ONO": Atoms("ONO", positions=[
            [0.0, 0.0, 0.0],    # O (binding)
            [0.0, 0.0, 1.40],   # N
            [0.0, 0.98, 2.12],  # O
        ]),
        # --- CO2RR intermediates ---
        # COOH: carboxyl *C(=O)OH, C binds, C=O 1.21 Å, C-O 1.36 Å
        "COOH": Atoms("COOH", positions=[
            [0.0, 0.0, 0.0],     # C (binding)
            [-0.87, 0.0, 0.70],  # O (=O)
            [0.87, 0.0, 0.70],   # O (-OH)
            [1.50, 0.0, 1.30],   # H
        ]),
        # OCHO: formate *O-CH=O (O-bound), O binds
        "OCHO": Atoms("OCHO", positions=[
            [0.0, 0.0, 0.0],    # O (binding)
            [0.0, 0.0, 1.36],   # C
            [0.0, 0.94, 1.95],  # H on C
            [0.0, -0.87, 2.06], # O (=O)
        ]),
        # CHO: formyl *CH=O, C binds, C=O 1.21 Å, C-H 1.10 Å
        "CHO": Atoms("CHO", positions=[
            [0.0, 0.0, 0.0],    # C (binding)
            [0.87, 0.0, 0.70],  # O
            [-0.55, 0.0, -0.87],# H
        ]),
        # COH: *C-OH, C binds, C-O 1.36 Å
        "COH": Atoms("COH", positions=[
            [0.0, 0.0, 0.0],    # C (binding)
            [0.0, 0.0, 1.36],   # O
            [0.0, 0.78, 1.87],  # H
        ]),
        # CHOH: *CH-OH, C binds
        "CHOH": Atoms("CHOH", positions=[
            [0.0, 0.0, 0.0],    # C (binding)
            [-0.60, 0.0, -0.87],# H on C
            [0.68, 0.0, 1.16],  # O
            [1.30, 0.0, 1.76],  # H on O
        ]),
        # CH2OH: hydroxymethyl *CH2-OH, C binds
        "CH2OH": Atoms("CH2OH", positions=[
            [0.0, 0.0, 0.0],     # C (binding)
            [0.52, 0.89, -0.36], # H
            [0.52, -0.89, -0.36],# H
            [0.0, 0.0, 1.43],    # O
            [0.0, 0.78, 1.90],   # H on O
        ]),
        # OCH3: methoxy *O-CH3, O binds, O-C 1.43 Å
        "OCH3": Atoms("OCH3", positions=[
            [0.0, 0.0, 0.0],    # O (binding)
            [0.0, 0.0, 1.43],   # C
            [0.0, 1.03, 1.93],  # H
            [0.89, -0.51, 1.93],# H
            [-0.89, -0.51, 1.93],# H
        ]),
        # CH3O: methoxy alias (same geometry as OCH3)
        "CH3O": Atoms("OCH3", positions=[
            [0.0, 0.0, 0.0],    # O (binding)
            [0.0, 0.0, 1.43],   # C
            [0.0, 1.03, 1.93],  # H
            [0.89, -0.51, 1.93],# H
            [-0.89, -0.51, 1.93],# H
        ]),
        # --- C2 CO2RR intermediates ---
        # OCCO: *OC-CO* (C-bound, oxalate-like), C-C 1.54 Å, C=O 1.21 Å
        "OCCO": Atoms("OCCO", positions=[
            [0.0, 0.0, 0.0],    # C (binding)
            [0.0, 0.0, 1.54],   # C
            [-0.87, 0.0, -0.70],# O on C1
            [0.87, 0.0, 2.24],  # O on C2
        ]),
        # OCCOH: *OC-C(OH), C-bound
        "OCCOH": Atoms("OCCOH", positions=[
            [0.0, 0.0, 0.0],     # C (binding)
            [0.0, 0.0, 1.54],    # C
            [-0.87, 0.0, -0.70], # O on C1 (=O)
            [0.87, 0.0, 2.07],   # O on C2 (-OH)
            [1.50, 0.0, 2.67],   # H on OH
        ]),
        # COCHO: *CO-CHO (glyoxal-like), C-bound
        "COCHO": Atoms("COCHO", positions=[
            [0.0, 0.0, 0.0],     # C (binding)
            [0.0, 0.0, 1.54],    # C
            [-0.87, 0.0, -0.70], # O on C1 (=O)
            [0.87, 0.0, 2.24],   # O on C2 (=O)
            [-0.55, 0.0, 2.41],  # H on C2
        ]),
        # --- AOR intermediates ---
        # CH3CO: acetyl *C(=O)CH3, C binds
        "CH3CO": Atoms("CH3CO", positions=[
            [0.0, 0.0, 0.0],     # C (binding, carbonyl)
            [0.87, 0.0, 0.70],   # O (=O)
            [0.0, 0.0, -1.54],   # C (methyl)
            [0.0, 1.03, -2.04],  # H
            [0.89, -0.51, -2.04],# H
            [-0.89, -0.51, -2.04],# H
        ]),
    }
    if adsorbate in manual_geometries:
        return _set_adsorbate_build_info(
            manual_geometries[adsorbate],
            builder="manual",
            adsorbate_input=adsorbate,
            smiles=smiles,
            smiles_source=smiles_source,
            fallback_reason=fallback_reason,
        )
    return None


def _build_adsorbate_atoms(adsorbate: str) -> Atoms:
    """Build an ASE Atoms object for the adsorbate (binding atom at index 0).

    Thin wrapper that applies the configured per-molecule binding-atom contract
    on top of whichever builder produced the geometry: if the leading atom is
    not the configured binding element (adsorption.binding_atoms), the molecule
    is permuted and re-oriented so the chemically correct atom faces the
    surface. This is the single enforcement point for the index-0 convention.
    """
    expected = _expected_binding_element(adsorbate)
    mol = _build_adsorbate_atoms_impl(adsorbate, expected)
    return _ensure_binding_atom_first(mol, expected)


def _build_adsorbate_atoms_impl(adsorbate: str, binding_element: str | None) -> Atoms:
    """Build an ASE Atoms object for the adsorbate molecule/atom.

    AutoAdsorbate is preferred for SMILES-backed molecules because it handles
    RDKit conformer generation and binding-atom surrogate markers. Hand-tuned
    geometries remain authoritative for single atoms and critical simple
    species such as C-down CO.
    """
    single_atom = _build_single_atom_adsorbate(adsorbate)
    if single_atom is not None:
        return single_atom

    binding_override = _build_binding_override_adsorbate(adsorbate)
    if binding_override is not None:
        return binding_override

    if adsorbate in RADICAL_ADSORBATES and not _has_known_smiles_label(adsorbate):
        # Known short radical labels such as CH/NH/OH already have local
        # geometries. Avoid sending them through OPSIN as if they were names.
        ase_atoms = _build_ase_adsorbate(adsorbate)
        if ase_atoms is not None:
            return ase_atoms

        manual_atoms = _build_manual_molecular_adsorbate(adsorbate)
        if manual_atoms is not None:
            return manual_atoms

    smiles_resolution = resolve_adsorbate_smiles(adsorbate)
    smiles = smiles_resolution.smiles
    smiles_source = smiles_resolution.source
    autoadsorbate_error: str | None = None
    if _should_try_autoadsorbate_first(adsorbate, smiles):
        atoms, autoadsorbate_error = _try_build_adsorbate_atoms_from_smiles(
            smiles or "",
            binding_element=binding_element,
            adsorbate_input=adsorbate,
            smiles_source=smiles_source,
        )
        if atoms is not None:
            return atoms

    ase_atoms = _build_ase_adsorbate(
        adsorbate,
        smiles=smiles,
        smiles_source=smiles_source,
        fallback_reason=autoadsorbate_error,
    )
    if ase_atoms is not None:
        return ase_atoms

    manual_atoms = _build_manual_molecular_adsorbate(
        adsorbate,
        smiles=smiles,
        smiles_source=smiles_source,
        fallback_reason=autoadsorbate_error,
    )
    if manual_atoms is not None:
        return manual_atoms

    if smiles:
        atoms, autoadsorbate_error = _try_build_adsorbate_atoms_from_smiles(
            smiles,
            adsorbate_input=adsorbate,
            smiles_source=smiles_source,
            binding_element=binding_element,
        )
        if atoms is not None:
            return atoms
        raise ValueError(
            f"Could not build adsorbate {adsorbate!r} from SMILES {smiles!r}: "
            f"{autoadsorbate_error}"
        )

    raise ValueError(
        f"Unknown adsorbate: {adsorbate!r}. "
        "Add it to _build_adsorbate_atoms(), config.ADSORBATE_SMILES, "
        "pass a SMILES string as 'smiles:<SMILES>', or install/configure "
        f"OPSIN name resolution. Last OPSIN error: {smiles_resolution.error!r}."
    )


# ---------------------------------------------------------------------------
# Adsorbate placement
# ---------------------------------------------------------------------------

def add_adsorbate_to_slab(
    slab_atoms: Atoms,
    adsorbate: str,
    site: AdsorptionSite,
    height: float | None = None,
) -> Atoms:
    """Place an adsorbate on a slab at the specified adsorption site.

    CatKit is used for site geometry, but final placement is deliberately ASE-based
    for all adsorbates so the binding atom orientation and cell wrapping are
    controlled consistently across catkit, pymatgen, and surfaxe slabs.

    Args:
        slab_atoms: ASE Atoms of the slab (constraints preserved).
        adsorbate:  Adsorbate formula string.
        site:       AdsorptionSite object from identify_adsorption_sites().
        height:     Height (Å) of the binding atom above the surface plane.
                    If None, uses DEFAULT_BOND_HEIGHT from config.

    Returns:
        New ASE Atoms object with adsorbate placed (constraints preserved).
    """
    h = height if height is not None else DEFAULT_BOND_HEIGHT.get(adsorbate, 2.0)
    # Always use ASE placement: site position is explicitly wrapped to [0,1)
    # before placement, so adsorbate lands inside the cell regardless of which
    # backend generated the slab. CatKit Builder tilts multi-atom adsorbates
    # which can place non-binding atoms outside the cell for boundary sites.
    return _place_with_ase(slab_atoms, adsorbate, site, h)


def _place_with_catkit(
    slab_atoms: Atoms,
    adsorbate: str,
    site: AdsorptionSite,
    height: float,
) -> Atoms:
    """Place adsorbate using CatKit Builder."""
    from catkit.gen.adsorption import Builder
    from catkit.gratoms import Gratoms

    # Wrap slab to [0,1) fractional so Builder places adsorbate inside cell
    slab_wrapped = slab_atoms.copy()
    slab_wrapped.wrap()

    gratoms_slab = Gratoms(
        numbers=slab_wrapped.numbers,
        positions=slab_wrapped.positions,
        cell=slab_wrapped.cell,
        pbc=slab_wrapped.pbc,
        edges=[],
    )

    # Builder calls get_surface_atoms() internally; must be set explicitly
    # when slab comes from pymatgen/ASE rather than CatKit's own SlabFactory.
    z = gratoms_slab.positions[:, 2]
    top_indices = np.where(z >= z.max() - 1.5)[0].tolist()
    gratoms_slab.set_surface_atoms(top=top_indices)

    ads_atoms = _build_adsorbate_atoms(adsorbate)
    ads_gratoms = Gratoms(
        numbers=ads_atoms.numbers,
        positions=ads_atoms.positions,
    )
    # Tag binding atom
    tags = [-1] + [0] * (len(ads_gratoms) - 1)
    ads_gratoms.set_tags(tags)

    builder = Builder(gratoms_slab)
    builder_site_index = site.catkit_index
    symmetric_sites = np.asarray(builder.get_symmetric_sites(), dtype=int)
    if builder_site_index < 0:
        builder_site_index = 0
    elif builder_site_index >= len(symmetric_sites):
        matches = np.where(symmetric_sites == int(site.catkit_index))[0]
        builder_site_index = int(matches[0]) if len(matches) else 0

    result_gratoms = builder.add_adsorbate(
        ads_gratoms,
        bonds=[0],       # binding atom index in adsorbate
        index=builder_site_index,
    )

    result_atoms = Atoms(
        numbers=result_gratoms.numbers,
        positions=result_gratoms.positions,
        cell=result_gratoms.cell,
        pbc=result_gratoms.pbc,
    )
    # Restore slab constraints
    result_atoms.set_constraint(slab_atoms.constraints)
    _preserve_slab_magmoms_zero_adsorbate(result_atoms, slab_atoms, len(slab_atoms))
    _copy_adsorbate_build_info(result_atoms, ads_atoms)
    tag_slab_and_adsorbate(result_atoms, len(slab_atoms), site.surface_atom_idx)
    _annotate_adsorption_metadata(result_atoms, n_slab=len(slab_atoms), adsorbate=adsorbate, site=site)
    result_atoms = _wrap_adsorbate_into_cell(result_atoms, len(slab_atoms))
    result_atoms = _annotate_binding_contact(result_atoms, len(slab_atoms), adsorbate)
    result_atoms = _annotate_acat_coverage(result_atoms, len(slab_atoms))
    return _check_post_placement_distance(result_atoms)


def _place_with_ase(
    slab_atoms: Atoms,
    adsorbate: str,
    site: AdsorptionSite,
    height: float,
) -> Atoms:
    """Place adsorbate manually using ASE Atoms arithmetic."""
    from ase.build import add_adsorbate as ase_add_adsorbate

    ads_atoms = _build_adsorbate_atoms(adsorbate)

    source_site = site
    slab_copy = slab_atoms.copy()
    slab_copy.set_pbc([True, True, False])
    slab_copy.wrap()   # ensure slab atoms are in [0,1) before placement
    slab_copy, placed_site = _center_site_image_xy(slab_copy, source_site)
    old_constraints = slab_atoms.constraints

    # Wrap the centered site position to [0,1) fractional before placing.
    cell = slab_copy.cell.array
    frac = np.linalg.solve(cell.T, np.array(placed_site.position, dtype=float))
    frac[:2] %= 1.0
    site_cart = frac @ cell

    ase_add_adsorbate(
        slab=slab_copy,
        adsorbate=ads_atoms,
        height=height,
        position=(float(site_cart[0]), float(site_cart[1])),
        mol_index=0,
    )

    slab_copy.set_constraint(old_constraints)
    _normalize_ase_adsorbate_info(slab_copy)
    _preserve_slab_magmoms_zero_adsorbate(slab_copy, slab_atoms, len(slab_atoms))
    _copy_adsorbate_build_info(slab_copy, ads_atoms)
    tag_slab_and_adsorbate(slab_copy, len(slab_atoms), source_site.surface_atom_idx)
    _annotate_adsorption_metadata(
        slab_copy,
        n_slab=len(slab_atoms),
        adsorbate=adsorbate,
        site=source_site,
        placed_site=placed_site,
    )
    slab_copy = _wrap_adsorbate_into_cell(slab_copy, len(slab_atoms))
    slab_copy = _annotate_binding_contact(slab_copy, len(slab_atoms), adsorbate)
    slab_copy = _annotate_acat_coverage(slab_copy, len(slab_atoms))
    return _check_post_placement_distance(slab_copy)


def _wrap_adsorbate_into_cell(atoms: Atoms, n_slab: int) -> Atoms:
    """Shift adsorbate atoms as a rigid body into the [0,1) fractional cell.

    Uses the centroid of the adsorbate in fractional xy to determine the
    integer shift, then applies it to all adsorbate atoms. Works for any
    displacement magnitude — not limited to ±1 unit cell.
    """
    if n_slab >= len(atoms):
        return atoms

    scaled = atoms.get_scaled_positions(wrap=False)
    centroid_xy = scaled[n_slab:, :2].mean(axis=0)
    shift = np.floor(centroid_xy).astype(int)

    if np.any(shift != 0):
        scaled[n_slab:, 0] -= shift[0]
        scaled[n_slab:, 1] -= shift[1]
        atoms.set_scaled_positions(scaled)

    return atoms


# ---------------------------------------------------------------------------
# Batch generation
# ---------------------------------------------------------------------------

def generate_all_adsorption_structures(
    slab_atoms: Atoms,
    adsorbate: str,
    max_sites: int | None = None,
    height: float | None = None,
    backend: str = "auto",
) -> list[tuple[AdsorptionSite, Atoms]]:
    """Generate structures with adsorbate placed at all unique sites.

    Args:
        slab_atoms: ASE Atoms of the slab.
        adsorbate:  Adsorbate formula string.
        max_sites:  Maximum number of sites to process (None = all).
                    Sites are ordered by priority, so top-priority sites
                    are always included.
        height:     Binding-atom height above surface in Å (None = use
                    DEFAULT_BOND_HEIGHT for this adsorbate, fallback 2.0 Å).
        backend:    Site detector backend. "auto" tries AutoAdsorbate first,
                    then merged CatKit/pymatgen/ACAT; specific detector names
                    skip AutoAdsorbate and use that detector with fallback.

    Returns:
        List of (AdsorptionSite, Atoms) tuples, sorted by site priority.
    """
    results: list[tuple[AdsorptionSite, Atoms]] = []
    backend_name = str(backend or "auto").strip().lower()
    if backend_name == "auto":
        try:
            results.extend(
                _generate_autoadsorbate_surface_structures(
                    slab_atoms,
                    adsorbate,
                    max_structures=max_sites,
                    height=height,
                )
            )
        except Exception as exc:
            warnings.warn(
                f"AutoAdsorbate surface population failed for {adsorbate}: {exc}. "
                "Falling back to CatKit/pymatgen site detection with ASE placement.",
                stacklevel=2,
            )

    remaining = None if max_sites is None else max(max_sites - len(results), 0)
    if remaining == 0:
        return results

    sites = identify_adsorption_sites(slab_atoms, adsorbate, backend=backend_name)

    if results:
        auto_sites = [site for site, _ in results]
        sites = [
            site
            for site in sites
            if all(_site_xy_distance(slab_atoms, site, auto_site) > 0.35 for auto_site in auto_sites)
        ]

    if remaining is not None:
        sites = sites[:remaining]
    elif max_sites is not None:
        sites = sites[:max_sites]

    for site in sites:
        try:
            struct = add_adsorbate_to_slab(slab_atoms, adsorbate, site, height=height)
            results.append((site, struct))
        except Exception as exc:
            warnings.warn(
                f"Failed to place {adsorbate} at {site.site_type} site: {exc}",
                stacklevel=2,
            )

    return results[:max_sites] if max_sites is not None else results
