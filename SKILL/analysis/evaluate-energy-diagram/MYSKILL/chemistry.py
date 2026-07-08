"""Chemistry label normalization helpers."""

from __future__ import annotations

import re
from typing import Any

from .constants import SPECIES_COMMON_NAMES, SUBSCRIPT_TRANSLATION, SUPERSCRIPT_TRANSLATION
from .utils import safe_string


def normalise_charge_text(text: str) -> str:
    text = text.translate(SUBSCRIPT_TRANSLATION).translate(SUPERSCRIPT_TRANSLATION)
    replacements = {
        "−": "-",
        "–": "-",
        "—": "-",
        "﹣": "-",
        "＋": "+",
        "·": "",
        " ": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\^([+-])", r"\1", text)
    text = re.sub(r"\(([a-zA-Z])\)$", "", text)  # remove simple phase label: O2(g)
    text = text.replace("aq", "") if text.endswith("aq") else text
    return text


def canonical_label(label: Any) -> str:
    """Canonicalise a reaction-coordinate label without changing chemistry.

    The internal representation uses a leading star for adsorbates: NO3* and
    *NO3 are both represented as *NO3. Charge and unicode variants are also
    normalized.  Original labels should be preserved upstream if exact display
    text matters.
    """
    raw = safe_string(label)
    if not raw:
        return ""
    raw = normalise_charge_text(raw)
    if raw.lower() in {"slab", "surface", "clean", "clean_surface", "bare", "bare_surface"}:
        return "*"
    if raw == "*":
        return raw
    if raw.endswith("*") and not raw.startswith("*"):
        raw = "*" + raw[:-1]
    if raw.startswith("ads_"):
        raw = "*" + raw[4:]
    return raw


def species_without_adsorption(label: str) -> str:
    label = canonical_label(label)
    if label.startswith("*"):
        return label[1:]
    return label


def species_core(label: str) -> str:
    """Species formula without adsorption mark or terminal charge."""
    bare = species_without_adsorption(label)
    return re.sub(r"[+-]+$", "", bare)


def formula_for_abbreviation(species: str) -> str:
    formula = species_without_adsorption(species)
    formula = normalise_charge_text(formula)
    formula = re.sub(r"[+-]+$", "", formula)
    formula = re.sub(r"[^A-Za-z0-9]", "", formula)
    return formula.upper() if formula.lower() in {"co2", "no3", "no2"} else formula


def species_common_name(species: str) -> str:
    species = canonical_label(species)
    bare = species_without_adsorption(species)
    return SPECIES_COMMON_NAMES.get(bare, bare)


def element_count(label: str, element: str) -> int:
    bare = species_without_adsorption(label)
    pattern = re.compile(rf"{re.escape(element)}(\d*)")
    total = 0
    for match in pattern.finditer(bare):
        count = match.group(1)
        total += int(count) if count else 1
    return total


def hydrogen_count(label: str) -> int:
    return element_count(label, "H")


def oxygen_count(label: str) -> int:
    return element_count(label, "O")
