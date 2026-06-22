"""
slabuilder — slab + adsorbate structure construction.

Trimmed to the surface the build_tools skills use:
    fetch_bulk  — Materials Project bulk structure retrieval
    slab_gen    — clean slab generation (metals and oxides/nitrides)
    adsorption  — adsorption site identification and adsorbate placement

Structure inspection helpers live in ``slabuilder.structure_understanding`` and
file I/O in ``slabuilder.utils``; import those submodules directly.
"""

import os as _os
import tempfile as _tempfile
from slabuilder.compat import apply_numpy_compat as _apply_numpy_compat

_os.environ.setdefault("MPLCONFIGDIR", str(_tempfile.gettempdir()))
_apply_numpy_compat()

from slabuilder.fetch_bulk import fetch_bulk_structures, BulkEntry
from slabuilder.slab_gen import SlabResult, generate_slab
from slabuilder.adsorption import build_adsorbate_atoms, generate_all_adsorption_structures

__all__ = [
    "fetch_bulk_structures",
    "BulkEntry",
    "SlabResult",
    "generate_slab",
    "build_adsorbate_atoms",
    "generate_all_adsorption_structures",
]
