"""Reaction detection and conservative reaction naming rules."""

from __future__ import annotations

import re
from typing import Any, Sequence

from .chemistry import canonical_label, formula_for_abbreviation, species_common_name, species_without_adsorption
from .constants import REACTION_METADATA, REACTION_SYNONYMS
from .errors import MesaValidationError
from .utils import safe_string


def reaction_type_key(text: str) -> str:
    cleaned = safe_string(text).upper().replace("−", "-").replace("–", "-")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def normalise_requested_reaction(requested: Any) -> str:
    key = reaction_type_key(safe_string(requested) or "AUTO")
    if key in REACTION_SYNONYMS:
        return REACTION_SYNONYMS[key]
    underscored = key.replace(" ", "_")
    if underscored in REACTION_SYNONYMS:
        return REACTION_SYNONYMS[underscored]
    compact = key.replace(" ", "").replace("_", "")
    if compact in REACTION_SYNONYMS:
        return REACTION_SYNONYMS[compact]
    return key


def infer_reaction_name(reaction_type: str, steps: Sequence[str]) -> dict[str, Any]:
    """Return deterministic reaction naming metadata.

    Known electrocatalysis abbreviations return curated names. Unknown paths use
    a conservative first-species formula-based fallback rather than guessing an
    unsupported IUPAC-style name.
    """
    reaction_type = normalise_requested_reaction(reaction_type)
    if reaction_type in REACTION_METADATA and reaction_type != "GENERIC":
        metadata = dict(REACTION_METADATA[reaction_type])
        metadata["naming_confidence"] = "curated_common_electrocatalysis_name"
        return metadata

    canonical_steps = [canonical_label(step) for step in steps]
    first_solution_species = next(
        (
            step
            for step in canonical_steps
            if step and not step.startswith("*") and step not in {"H2O", "H+", "OH-"}
        ),
        None,
    )
    last_solution_species = next(
        (
            step
            for step in reversed(canonical_steps)
            if step and not step.startswith("*") and step not in {"H2O", "H+", "OH-"}
        ),
        None,
    )

    direction = "unknown"
    if first_solution_species and first_solution_species != last_solution_species:
        direction = "reduction" if looks_like_reduction_path(canonical_steps) else "reaction"

    if first_solution_species and direction == "reduction":
        species_name = species_common_name(first_solution_species)
        abbreviation = f"{formula_for_abbreviation(first_solution_species)}RR"
        return {
            "canonical_name": f"{species_name} reduction reaction",
            "abbreviation": abbreviation,
            "reaction_class": "reduction",
            "direction": "reduction",
            "reactant": first_solution_species,
            "product": last_solution_species,
            "primary_descriptor": "largest_uphill_electrochemical_step",
            "common_competing_reactions": ["HER"],
            "expected_labels": [],
            "naming_confidence": "formula_based_rule",
        }

    return {
        "canonical_name": "generic reaction energy evaluation",
        "abbreviation": "GENERIC",
        "reaction_class": "generic",
        "direction": "unknown",
        "reactant": first_solution_species,
        "product": last_solution_species,
        "primary_descriptor": "largest_uphill_step",
        "common_competing_reactions": [],
        "expected_labels": [],
        "naming_confidence": "generic_fallback",
    }


def looks_like_reduction_path(steps: Sequence[str]) -> bool:
    bare = [species_without_adsorption(step) for step in steps]
    joined = " ".join(bare)
    if any(token in joined for token in ["NH3", "NH2", "NH", "CO", "CH4", "HCOO"]):
        return True
    if any(step in bare for step in ["NO3-", "NO2-", "N2", "CO2", "O2"]):
        return True
    return False


def detect_reaction_type(requested: str, steps: list[str]) -> tuple[str, list[str], dict[str, Any]]:
    warnings: list[str] = []
    requested_type = normalise_requested_reaction(requested)
    step_set = set(steps)
    if requested_type != "AUTO":
        if requested_type not in REACTION_METADATA and not requested_type.endswith("RR"):
            raise MesaValidationError(f"Unsupported reaction_type: {requested}")
        metadata = infer_reaction_name(requested_type, steps)
        return metadata["abbreviation"], warnings, metadata

    # Detection order matters: NOx and CO2 reduction paths can contain *H or O-containing labels.
    if step_set.intersection({"NO3-", "*NO3"}) or any("NO3" in step for step in step_set):
        reaction_type = "NO3RR"
    elif step_set.intersection({"NO2-", "*NO2"}) and any("NO" in step for step in step_set):
        reaction_type = "NO2RR"
    elif step_set.intersection({"CO2", "*CO2", "*COOH"}) or any("CO2" in step for step in step_set):
        reaction_type = "CO2RR"
    elif "N2" in step_set or "*N2" in step_set:
        reaction_type = "NRR"
    elif {"*OH", "*O", "*OOH"}.issubset(step_set) or {"*OH", "*OOH"}.issubset(step_set):
        first = steps[0] if steps else ""
        reaction_type = "ORR" if first == "O2" else "OER"
    elif "*H" in step_set or "H+" in step_set or "H2" in step_set:
        reaction_type = "HER"
    else:
        reaction_type = "GENERIC"
        warnings.append("Could not detect a known electrochemical reaction; using generic uphill-step ranking.")

    metadata = infer_reaction_name(reaction_type, steps)
    return reaction_type, warnings, metadata
