"""Constants for TASK_REACTION_ENERGY_EVALUATION."""

from __future__ import annotations

import re
from typing import Any

TASK_ID = "TASK_REACTION_ENERGY_EVALUATION"
SKILL_NAME = "reaction_energy_evaluation"

DEFAULT_OER_TOTAL_FREE_ENERGY_EV = 4.92
OER_REVERSIBLE_POTENTIAL_V = 1.23

FORMULA_PATTERN = re.compile(r"\b(?:[A-Z][a-z]?\d*){2,}\b")
MEASUREMENT_PATTERN = re.compile(
    r"(?P<value>[+-]?\d+(?:\.\d+)?)\s*(?P<unit>mV|V|eV|K|C|M|mol/L|mA/cm2|mA cm-2|%)\b",
    re.IGNORECASE,
)
KEYWORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9+\-*/]{2,}")

SUBSCRIPT_TRANSLATION = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
SUPERSCRIPT_TRANSLATION = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")
ARROW_RE = re.compile(r"\s*(?:->|→|=>|⟶|⟹)\s*")

# Species-name map intentionally contains only high-confidence, common species.
# The fallback naming rule keeps the formula in generated names to avoid
# hallucinated systematic names.
SPECIES_COMMON_NAMES: dict[str, str] = {
    "H+": "proton",
    "H2": "hydrogen",
    "H2O": "water",
    "O2": "oxygen",
    "OH-": "hydroxide",
    "NO3-": "nitrate",
    "NO3": "nitrate",
    "NO2-": "nitrite",
    "NO2": "nitrite",
    "NO": "nitric oxide",
    "N2": "nitrogen",
    "NH3": "ammonia",
    "CO2": "carbon dioxide",
    "CO": "carbon monoxide",
    "CH4": "methane",
    "HCOO-": "formate",
    "HCOOH": "formic acid",
}

REACTION_SYNONYMS: dict[str, str] = {
    "HYDROGEN_EVOLUTION_REACTION": "HER",
    "HYDROGEN EVOLUTION REACTION": "HER",
    "HYDROGEN_EVOLUTION": "HER",
    "HYDROGEN EVOLUTION": "HER",
    "H2_EVOLUTION": "HER",
    "H2 EVOLUTION": "HER",
    "HER": "HER",
    "OXYGEN_EVOLUTION_REACTION": "OER",
    "OXYGEN EVOLUTION REACTION": "OER",
    "OXYGEN_EVOLUTION": "OER",
    "OXYGEN EVOLUTION": "OER",
    "OER": "OER",
    "OXYGEN_REDUCTION_REACTION": "ORR",
    "OXYGEN REDUCTION REACTION": "ORR",
    "ORR": "ORR",
    "NITRATE_REDUCTION_REACTION": "NO3RR",
    "NITRATE REDUCTION REACTION": "NO3RR",
    "NITRATE_REDUCTION": "NO3RR",
    "NITRATE REDUCTION": "NO3RR",
    "NO3RR": "NO3RR",
    "NO3-RR": "NO3RR",
    "NO3_RR": "NO3RR",
    "NO3−RR": "NO3RR",
    "NITRITE_REDUCTION_REACTION": "NO2RR",
    "NITRITE REDUCTION REACTION": "NO2RR",
    "NITRITE_REDUCTION": "NO2RR",
    "NITRITE REDUCTION": "NO2RR",
    "NO2RR": "NO2RR",
    "NO2-RR": "NO2RR",
    "NITROGEN_REDUCTION_REACTION": "NRR",
    "NITROGEN REDUCTION REACTION": "NRR",
    "NRR": "NRR",
    "CO2_REDUCTION_REACTION": "CO2RR",
    "CO2 REDUCTION REACTION": "CO2RR",
    "CARBON_DIOXIDE_REDUCTION_REACTION": "CO2RR",
    "CARBON DIOXIDE REDUCTION REACTION": "CO2RR",
    "CO2RR": "CO2RR",
    "CO2-RR": "CO2RR",
    "GENERIC": "GENERIC",
    "AUTO": "AUTO",
}

REACTION_METADATA: dict[str, dict[str, Any]] = {
    "HER": {
        "canonical_name": "hydrogen evolution reaction",
        "abbreviation": "HER",
        "reaction_class": "evolution",
        "direction": "reduction",
        "primary_descriptor": "dG_H*",
        "common_competing_reactions": [],
        "expected_labels": ["*", "*H"],
    },
    "OER": {
        "canonical_name": "oxygen evolution reaction",
        "abbreviation": "OER",
        "reaction_class": "evolution",
        "direction": "oxidation",
        "primary_descriptor": "max_dG_step_minus_1.23V",
        "common_competing_reactions": ["catalyst oxidation/dissolution", "electrolyte oxidation"],
        "expected_labels": ["*", "*OH", "*O", "*OOH"],
    },
    "ORR": {
        "canonical_name": "oxygen reduction reaction",
        "abbreviation": "ORR",
        "reaction_class": "reduction",
        "direction": "reduction",
        "primary_descriptor": "largest_uphill_pcet_step",
        "common_competing_reactions": ["HER"],
        "expected_labels": ["O2", "*OOH", "*O", "*OH", "*"],
    },
    "NO3RR": {
        "canonical_name": "nitrate reduction reaction",
        "abbreviation": "NO3RR",
        "reaction_class": "reduction",
        "direction": "reduction",
        "reactant": "NO3-",
        "product": "NH3",
        "primary_descriptor": "largest_uphill_electrochemical_step",
        "common_competing_reactions": ["HER", "nitrite formation", "NOx by-product formation"],
        "expected_labels": ["NO3-", "*NO3", "*NO2", "*NO", "*N", "*NH", "*NH2", "*NH3", "NH3"],
    },
    "NO2RR": {
        "canonical_name": "nitrite reduction reaction",
        "abbreviation": "NO2RR",
        "reaction_class": "reduction",
        "direction": "reduction",
        "reactant": "NO2-",
        "product": "NH3",
        "primary_descriptor": "largest_uphill_electrochemical_step",
        "common_competing_reactions": ["HER", "NOx by-product formation"],
        "expected_labels": ["NO2-", "*NO2", "*NO", "*N", "*NH", "*NH2", "*NH3", "NH3"],
    },
    "NRR": {
        "canonical_name": "nitrogen reduction reaction",
        "abbreviation": "NRR",
        "reaction_class": "reduction",
        "direction": "reduction",
        "reactant": "N2",
        "product": "NH3",
        "primary_descriptor": "largest_uphill_electrochemical_step",
        "common_competing_reactions": ["HER"],
        "expected_labels": ["N2", "*N2", "*NNH", "*NHNH", "*NH2NH2", "*NH3", "NH3"],
    },
    "CO2RR": {
        "canonical_name": "carbon dioxide reduction reaction",
        "abbreviation": "CO2RR",
        "reaction_class": "reduction",
        "direction": "reduction",
        "reactant": "CO2",
        "product": None,
        "primary_descriptor": "largest_uphill_electrochemical_step",
        "common_competing_reactions": ["HER"],
        "expected_labels": ["CO2", "*CO2", "*COOH", "*CO", "CO"],
    },
    "GENERIC": {
        "canonical_name": "generic reaction energy evaluation",
        "abbreviation": "GENERIC",
        "reaction_class": "generic",
        "direction": "unknown",
        "primary_descriptor": "largest_uphill_step",
        "common_competing_reactions": [],
        "expected_labels": [],
    },
}

METADATA_COLUMNS = {
    "site",
    "note",
    "notes",
    "source",
    "phase",
    "charge",
    "spin",
    "pathway",
    "reaction",
    "reaction_type",
    "description",
    "comment",
    "comments",
}

STEP_COLUMN_CANDIDATES = ["step", "intermediate", "state", "species", "label", "reaction_coordinate"]
