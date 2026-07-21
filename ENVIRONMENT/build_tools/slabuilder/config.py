"""Default constants and rule tables for the skill-backed slabuilder engine."""

from __future__ import annotations

# Slab generation defaults.
DEFAULT_VACUUM_ANGSTROM: float = 15.0
TARGET_LATERAL_SIZE_ANGSTROM: float = 7.5
LATERAL_TOLERANCE_ANGSTROM: float = 2.0
TARGET_SLAB_THICKNESS_ANGSTROM: float = 8.0
TARGET_ATOM_COUNT: int = 70
ATOM_COUNT_TOLERANCE: int = 40

BACKEND_OXIDE_NITRIDE: str = "surfaxe"
BACKEND_DEFAULT: str = "catkit"
BACKEND_SYMMETRY: str = "pymatgen"

# Adsorbate classification and chemistry defaults.
CLOSED_SHELL_ADSORBATES: frozenset[str] = frozenset(
    ["CO", "H2", "H2O", "CO2", "CH4", "NH3", "N2", "O2",
     # CO2RR closed-shell intermediates
     "HCOOH", "CH2O", "H2CO", "CH3OH", "C2H5OH",
     # NRR / NOXRR closed-shell
     "N2H4", "NH2OH", "N2O", "HNO3",
     # ORR
     "H2O2", "HOOH",
     # AOR
     "CH3CHO", "CH3COOH",
     ]
)
RADICAL_ADSORBATES: frozenset[str] = frozenset(
    ["O", "N", "C", "S", "H", "OH", "OOH", "SH", "NO", "CH", "NH", "CH2", "CH3",
     # --- NRR intermediates ---
     "NH2",           # amino radical
     "NNH",           # diazenyl (N2H), *N=NH
     "NNH2",          # *N=NH2
     "NHNH",          # diazene, HN=NH
     "NHNH2",         # *NH-NH2
     "NH2NH2",        # hydrazine on surface (*NH2-NH2)
     # --- NOXRR intermediates ---
     "NO2",           # nitrogen dioxide
     "NO3",           # nitrate
     "NOH",           # *N-OH (isomer of HNO)
     "HNO",           # nitroxyl *NH=O
     "NHOH",          # *NH-OH
     "ONO",           # *O-N=O (nitrite, O-bound)
     # --- CO2RR intermediates ---
     "COOH",          # carboxyl *C(=O)OH
     "OCHO",          # formate *O-CH=O (O-bound)
     "CHO",           # formyl *CH=O
     "COH",           # *C-OH (C-bound)
     "CHOH",          # *CH-OH
     "CH2OH",         # hydroxymethyl *CH2-OH
     "OCH3",          # methoxy *O-CH3
     "CH3O",          # methoxy alias
     # --- C2 CO2RR intermediates ---
     "OCCO",          # *OC-CO* (oxalate-like, C-bound)
     "OCCOH",         # *OC-COH
     "COCOH",         # *CO-COH
     "COCHO",         # *CO-CHO (glyoxal-like)
     # --- AOR intermediates ---
     "CH3CO",         # acetyl *C(=O)CH3
     ]
)

ADSORBATE_SMILES: dict[str, str] = {
    # --- original ---
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
    # --- NRR intermediates ---
    "NNH": "[N]=[NH]",
    "NNH2": "[N]=[NH2]",
    "NHNH": "[NH]=[NH]",
    "NHNH2": "[NH][NH2]",
    "N2H4": "NN",
    # --- NOXRR intermediates ---
    "NO2": "[O][N]=O",
    "NO3": "[O][N](=O)=O",
    "NOH": "[N][OH]",
    "HNO": "[NH]=O",
    "NHOH": "[NH][OH]",
    "NH2OH": "N[OH]",
    "N2O": "[N-]=[N+]=O",
    "ONO": "[O][N]=O",
    "HNO3": "[O][N+](=O)[O-]",
    # --- CO2RR intermediates ---
    "COOH": "[C](=O)[OH]",
    "OCHO": "[O][CH]=O",
    "CHO": "[CH]=O",
    "COH": "[C][OH]",
    "HCOOH": "OC=O",
    "CH2O": "C=O",
    "H2CO": "C=O",
    "CHOH": "[CH][OH]",
    "CH2OH": "[CH2][OH]",
    "OCH3": "[O]C",
    "CH3O": "[O]C",
    # --- C2 CO2RR intermediates ---
    "OCCO": "O=[C][C]=O",
    "OCCOH": "O=[C][C]([OH])",
    "COCOH": "O=[C][C]([OH])",
    "COCHO": "O=[C][CH]=O",
    # --- ORR / OER ---
    "H2O2": "OO",
    "HOOH": "OO",
    # --- AOR intermediates ---
    "CH3CHO": "CC=O",
    "CH3CO": "C[C]=O",
    "CH3COOH": "CC(=O)O",
}

ADSORBATE_BINDING_ATOMS: dict[str, str] = {
    # --- original ---
    "CO": "C",
    "NO": "N",
    "CO2": "C",
    "N2": "N",
    "H2": "H",
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
    # --- NRR ---
    "NH2": "N",
    "NNH": "N",       # terminal N binds
    "NNH2": "N",      # terminal N binds
    "NHNH": "N",      # one N binds (η¹)
    "NHNH2": "N",     # NH-end binds
    "NH2NH2": "N",    # one N binds
    "N2H4": "N",
    # --- NOXRR ---
    "NO2": "N",
    "NO3": "N",
    "NOH": "N",
    "HNO": "N",
    "NHOH": "N",
    "NH2OH": "N",
    "N2O": "N",
    "ONO": "O",       # O-bound nitrite
    "HNO3": "N",
    # --- CO2RR ---
    "COOH": "C",
    "OCHO": "O",      # formate O-bound
    "CHO": "C",
    "COH": "C",
    "HCOOH": "C",
    "CH2O": "C",
    "H2CO": "C",
    "CHOH": "C",
    "CH2OH": "C",
    "OCH3": "O",      # methoxy O-bound
    "CH3O": "O",
    # --- C2 CO2RR ---
    "OCCO": "C",
    "OCCOH": "C",
    "COCOH": "C",
    "COCHO": "C",
    # --- ORR ---
    "H2O2": "O",
    "HOOH": "O",
    # --- AOR ---
    "CH3CHO": "C",
    "CH3CO": "C",
    "CH3COOH": "C",
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
    # --- original ---
    "O": ["fcc_hollow", "hcp_hollow", "bridge", "top"],
    "N": ["fcc_hollow", "hcp_hollow", "bridge", "top"],
    "C": ["fcc_hollow", "hcp_hollow", "bridge", "top"],
    "S": ["fcc_hollow", "hcp_hollow", "bridge", "top"],
    "H": ["top", "bridge", "fcc_hollow"],
    "H2": ["top", "bridge", "fcc_hollow"],
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
    # --- NRR ---
    "NH2": ["top", "bridge"],
    "NNH": ["top", "bridge", "fcc_hollow"],
    "NNH2": ["top", "bridge"],
    "NHNH": ["top", "bridge"],
    "NHNH2": ["top", "bridge"],
    "NH2NH2": ["top"],
    "N2H4": ["top"],
    # --- NOXRR ---
    "NO2": ["top", "bridge"],
    "NO3": ["top", "bridge"],
    "NOH": ["top", "bridge", "fcc_hollow"],
    "HNO": ["top", "bridge"],
    "NHOH": ["top", "bridge"],
    "NH2OH": ["top"],
    "N2O": ["top"],
    "ONO": ["top", "bridge"],
    "HNO3": ["top"],
    # --- CO2RR ---
    "COOH": ["top", "bridge"],
    "OCHO": ["top", "bridge"],
    "CHO": ["top", "bridge"],
    "COH": ["top", "fcc_hollow", "hcp_hollow"],
    "HCOOH": ["top"],
    "CH2O": ["top", "bridge"],
    "H2CO": ["top", "bridge"],
    "CHOH": ["top", "bridge"],
    "CH2OH": ["top", "bridge"],
    "OCH3": ["top", "bridge"],
    "CH3O": ["top", "bridge"],
    # --- C2 CO2RR ---
    "OCCO": ["bridge", "top"],
    "OCCOH": ["bridge", "top"],
    "COCOH": ["bridge", "top"],
    "COCHO": ["bridge", "top"],
    # --- ORR ---
    "H2O2": ["top"],
    "HOOH": ["top"],
    # --- AOR ---
    "CH3CHO": ["top"],
    "CH3CO": ["top", "bridge"],
    "CH3COOH": ["top"],
}

DEFAULT_BOND_HEIGHT: dict[str, float] = {
    # --- original ---
    "O": 1.8,
    "N": 1.8,
    "C": 2.0,
    "S": 2.2,
    "H": 1.6,
    "H2": 1.6,
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
    # --- NRR ---
    "NH2": 1.9,
    "NNH": 1.9,
    "NNH2": 1.9,
    "NHNH": 1.9,
    "NHNH2": 1.9,
    "NH2NH2": 2.0,
    "N2H4": 2.0,
    # --- NOXRR ---
    "NO2": 2.0,
    "NO3": 2.0,
    "NOH": 1.9,
    "HNO": 1.9,
    "NHOH": 1.9,
    "NH2OH": 2.0,
    "N2O": 2.0,
    "ONO": 1.9,
    "HNO3": 2.0,
    # --- CO2RR ---
    "COOH": 2.0,
    "OCHO": 2.0,
    "CHO": 2.0,
    "COH": 2.0,
    "HCOOH": 2.0,
    "CH2O": 2.0,
    "H2CO": 2.0,
    "CHOH": 2.0,
    "CH2OH": 2.0,
    "OCH3": 1.9,
    "CH3O": 1.9,
    # --- C2 CO2RR ---
    "OCCO": 2.0,
    "OCCOH": 2.0,
    "COCOH": 2.0,
    "COCHO": 2.0,
    # --- ORR ---
    "H2O2": 2.0,
    "HOOH": 2.0,
    # --- AOR ---
    "CH3CHO": 2.0,
    "CH3CO": 2.0,
    "CH3COOH": 2.0,
}
