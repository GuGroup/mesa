"""
fetch_bulk.py — Tool 2: Retrieve bulk structures from the Materials Project.

Uses the official mp-api client. API key is read from the MP_API_KEY or
PMG_MAPI_KEY environment variable (also picked up from a .env file via
python-dotenv).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv
from pymatgen.core import Composition, Element, Structure

from slabuilder.utils import get_space_group

# Load .env from the project root (or any parent directory)
load_dotenv()


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

def _normalize_elements(query: str | list[str]) -> list[str]:
    """Return validated element symbols preserving user order when possible."""
    if isinstance(query, str):
        text = query.strip()
        if not text:
            raise ValueError("Chemical system query is empty.")
        if re.search(r"[-,\s*]", text):
            raw = [part for part in re.split(r"[-,\s*]+", text) if part]
        else:
            raw = [el.symbol for el in Composition(text).elements]
    else:
        raw = list(query)

    elements: list[str] = []
    for item in raw:
        symbol = Element(str(item).strip()).symbol
        if symbol not in elements:
            elements.append(symbol)
    if not elements:
        raise ValueError("No valid elements found in chemical system query.")
    return elements


def _chemsys_string(elements: list[str]) -> str:
    return "-".join(elements)


@dataclass
class BulkEntry:
    """A single bulk structure retrieved from the Materials Project.

    Attributes:
        mpid:                Materials Project identifier (e.g., "mp-126").
        formula:             Reduced formula string (e.g., "Pt", "Fe2O3").
        structure:           pymatgen Structure object.
        energy_above_hull:   eV/atom above the convex hull (0 = stable).
        formation_energy:    Formation energy in eV/atom.
        space_group_number:  Space group number.
        space_group_symbol:  Space group Hermann-Mauguin symbol.
        n_sites:             Number of atoms in the unit cell.
        theoretical:         True if structure is theoretical (no ICSD entry).
        initial_magmoms:     MP-provided per-site magnetic moments when present.
    """
    mpid: str
    formula: str
    structure: Structure
    energy_above_hull: float
    formation_energy: float
    space_group_number: int
    space_group_symbol: str
    n_sites: int
    theoretical: bool = True
    initial_magmoms: list[float] | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_bulk_structures(
    formula: str,
    mp_api_key: str | None = None,
    max_results: int = 10,
    sort_by: str = "energy_above_hull",
    search_mode: str = "formula",
) -> list[BulkEntry]:
    """Fetch bulk structures from the Materials Project API.

    Args:
        formula:      Chemical formula to search for (e.g., "Pt", "Fe2O3", "TiO2").
                      Supports reduced formulas and element-only queries.
        mp_api_key:   Materials Project API key. If None, reads from the
                      MP_API_KEY or PMG_MAPI_KEY environment variable (also
                      loaded from .env).
        max_results:  Maximum number of structures to return.
        sort_by:      Sorting criterion — 'energy_above_hull' (default) or
                      'formation_energy'.
        search_mode:  'formula' for formula/anonymized/wildcard search,
                      'material_id' for a specific MP-ID, 'chemsys' for all entries in the closed chemical system
                      and its subsystems (e.g. Mg-H, Mg, H), or 'elements' for
                      materials containing the requested elements, including
                      possible additional elements.

    Returns:
        List of BulkEntry objects sorted by the specified criterion (ascending).

    Raises:
        ValueError:   If the API key is not found.
        RuntimeError: If the API query fails.
    """
    api_key = mp_api_key or os.environ.get("MP_API_KEY") or os.environ.get("PMG_MAPI_KEY")
    if not api_key:
        raise ValueError(
            "Materials Project API key not found. "
            "Set MP_API_KEY or PMG_MAPI_KEY as an environment variable or in a "
            ".env file, or pass it directly."
        )

    entries: list[BulkEntry] = []

    try:
        from mp_api.client import MPRester
    except ImportError:
        raise ImportError("mp-api is required. Install with: uv add mp-api")

    fields = [
        "material_id",
        "formula_pretty",
        "structure",
        "energy_above_hull",
        "formation_energy_per_atom",
        "nsites",
        "theoretical",
    ]

    with MPRester(api_key) as mpr:
        if search_mode == "formula":
            docs = mpr.summary.search(formula=formula, fields=fields)
        elif search_mode == "material_id":
            match = re.search(r"\bmp-\d+\b", formula, flags=re.IGNORECASE)
            material_id = match.group(0).lower() if match else formula
            docs = mpr.summary.search(material_ids=material_id, fields=fields)
        elif search_mode == "chemsys":
            elements = _normalize_elements(formula)
            docs = mpr.summary.search(chemsys=_chemsys_string(elements), fields=fields)
        elif search_mode == "elements":
            elements = _normalize_elements(formula)
            docs = mpr.summary.search(elements=elements, fields=fields)
        else:
            raise ValueError(
                "Unknown search_mode: {!r}. Use 'formula', 'material_id', 'chemsys', or 'elements'.".format(search_mode)
            )

    if not docs:
        return []

    # Sort
    reverse = False
    if sort_by == "energy_above_hull":
        key = lambda d: (d.energy_above_hull or 0.0)
    elif sort_by == "formation_energy":
        key = lambda d: (d.formation_energy_per_atom or 0.0)
    else:
        raise ValueError(f"Unknown sort_by: {sort_by!r}. Use 'energy_above_hull' or 'formation_energy'.")

    docs = sorted(docs, key=key, reverse=reverse)[:max_results]

    for doc in docs:
        struct = doc.structure
        sg_num, sg_sym = get_space_group(struct)
        raw_magmoms = struct.site_properties.get("magmom") if struct is not None else None
        initial_magmoms = (
            [float(m) for m in raw_magmoms]
            if raw_magmoms is not None and len(raw_magmoms) == len(struct)
            else None
        )

        entry = BulkEntry(
            mpid=str(doc.material_id),
            formula=doc.formula_pretty,
            structure=struct,
            energy_above_hull=doc.energy_above_hull or 0.0,
            formation_energy=doc.formation_energy_per_atom or 0.0,
            space_group_number=sg_num,
            space_group_symbol=sg_sym,
            n_sites=doc.nsites,
            theoretical=bool(getattr(doc, 'theoretical', True)),
            initial_magmoms=initial_magmoms,
        )

        entries.append(entry)

    return entries
