"""Default constants and rule tables for the skill-backed slabuilder engine."""

from __future__ import annotations

# Slab generation defaults.
DEFAULT_VACUUM_ANGSTROM: float = 15.0
TARGET_LATERAL_SIZE_ANGSTROM: float = 10.0
LATERAL_TOLERANCE_ANGSTROM: float = 2.0
TARGET_SLAB_THICKNESS_ANGSTROM: float = 8.0
TARGET_ATOM_COUNT: int = 100
ATOM_COUNT_TOLERANCE: int = 100

BACKEND_OXIDE_NITRIDE: str = "surfaxe"
BACKEND_DEFAULT: str = "catkit"
BACKEND_SYMMETRY: str = "pymatgen"

# Adsorbate classification and chemistry defaults.
CLOSED_SHELL_ADSORBATES: frozenset[str] = frozenset(
    ["CO", "H2O", "CO2", "CH4", "NH3", "N2", "O2"]
)
RADICAL_ADSORBATES: frozenset[str] = frozenset(
    ["O", "N", "C", "S", "H", "OH", "OOH", "SH", "NO", "CH", "NH", "CH2", "CH3"]
)

ADSORBATE_SMILES: dict[str, str] = {
    "H2O": "O",
    "NH3": "N",
    "CH4": "C",
    "CO2": "O=C=O",
    "N2": "N#N",
    "O2": "O=O",
    "NO": "N=O",
    "methanol": "CO",
    "MeOH": "CO",
    "MEOH": "CO",
    "CH3OH": "CO",
    "ethanol": "CCO",
    "EtOH": "CCO",
    "ETOH": "CCO",
    "C2H5OH": "CCO",
}

ADSORBATE_BINDING_ATOMS: dict[str, str] = {
    "CO": "C",
    "NO": "N",
    "CO2": "C",
    "N2": "N",
    "O2": "O",
    "H2O": "O",
    "NH3": "N",
    "CH4": "C",
    "H2S": "S",
    "OH": "O",
    "OOH": "O",
    "SH": "S",
    "CH3": "C",
    "CH2": "C",
    "CH": "C",
    "NH": "N",
    "methanol": "O",
    "MeOH": "O",
    "MEOH": "O",
    "CH3OH": "O",
    "ethanol": "O",
    "EtOH": "O",
    "ETOH": "O",
    "C2H5OH": "O",
}

AUTOADSORBATE_FIRST_ADSORBATES: frozenset[str] = frozenset(ADSORBATE_SMILES.keys())
AUTOADSORBATE_ATTACK_ATOMS: tuple[str, ...] = ("O", "N", "S", "C")
AUTOADSORBATE_SURFACE_ENABLED: bool = True
AUTOADSORBATE_SURFACE_PRECISION: float = 0.5
AUTOADSORBATE_TOUCH_SPHERE_SIZE: float = 3.0
AUTOADSORBATE_CONFORMERS_TO_INITIALIZE: int = 10
AUTOADSORBATE_CONFORMERS_PER_SITE_CAP: int = 2
AUTOADSORBATE_OVERLAP_THRESHOLD: float = 1.5
MIN_PLACEMENT_DISTANCE: float = 0.5

SITE_PRIORITY: dict[str, list[str]] = {
    "O": ["fcc_hollow", "hcp_hollow", "bridge", "top"],
    "N": ["fcc_hollow", "hcp_hollow", "bridge", "top"],
    "C": ["fcc_hollow", "hcp_hollow", "bridge", "top"],
    "S": ["fcc_hollow", "hcp_hollow", "bridge", "top"],
    "H": ["top", "bridge", "fcc_hollow"],
    "CO": ["top", "bridge"],
    "H2O": ["top"],
    "NH3": ["top"],
    "CO2": ["top"],
    "CH4": ["top"],
    "OH": ["top", "bridge"],
    "OOH": ["top"],
    "SH": ["top", "bridge"],
    "NO": ["top", "fcc_hollow"],
    "CH": ["fcc_hollow", "hcp_hollow", "bridge", "top"],
    "NH": ["bridge", "fcc_hollow", "hcp_hollow", "top"],
    "CH3": ["top", "bridge"],
    "CH2": ["bridge", "hollow"],
}

DEFAULT_BOND_HEIGHT: dict[str, float] = {
    "O": 1.8,
    "N": 1.8,
    "C": 2.0,
    "S": 2.2,
    "H": 1.6,
    "CO": 2.0,
    "H2O": 2.0,
    "OH": 1.9,
    "OOH": 2.0,
    "NO": 2.0,
    "CH": 2.0,
    "NH": 1.9,
    "NH3": 2.0,
    "CO2": 2.0,
    "SH": 2.2,
    "CH3": 2.1,
    "CH4": 2.2,
}
