"""Experiment-computation comparison and competing-reaction summaries."""

from __future__ import annotations

from typing import Any

from .nomenclature import normalise_requested_reaction
from .utils import is_number


def compare_experiment(results: dict[str, Any], experiment: Any, reaction_type: str) -> dict[str, Any]:
    if not isinstance(experiment, dict):
        return {}
    comparison: dict[str, Any] = {}
    for catalyst, raw_value in experiment.items():
        if catalyst not in results:
            comparison[catalyst] = {"error": "catalyst not found"}
            continue
        experimental = float(raw_value)
        if reaction_type == "HER":
            calculated = results[catalyst]["delta_g_h_ev"]
        else:
            calculated = results[catalyst].get("eta_calc_v", results[catalyst].get("score", 0.0))
        comparison[catalyst] = {
            "calculated": calculated,
            "experimental": experimental,
            "difference": calculated - experimental,
            "absolute_difference_mv": abs(calculated - experimental) * 1000,
        }
    return comparison


def evaluate_competing_reactions(input_data: dict[str, Any], primary_results: dict[str, Any]) -> dict[str, Any]:
    """Summarise optional competing reaction descriptors.

    Competing reactions are often provided as lightweight descriptors, for
    example {"HER": {"Ni": 0.05, "Co": 0.30}} where values are ΔG_H* in eV.
    This function records them as selectivity warnings, not definitive
    selectivity predictions.
    """
    competing = input_data.get("competing_reactions") or input_data.get("competing_descriptors")
    if not isinstance(competing, dict):
        return {}
    output: dict[str, Any] = {}
    for reaction_name, descriptor_map in competing.items():
        reaction_key = normalise_requested_reaction(reaction_name)
        if not isinstance(descriptor_map, dict):
            output[reaction_name] = {"error": "descriptor map must be a catalyst->value dictionary"}
            continue
        rows: dict[str, Any] = {}
        for catalyst, value in descriptor_map.items():
            if not is_number(value):
                rows[catalyst] = {"error": f"non-numeric descriptor {value!r}"}
                continue
            descriptor = float(value)
            if reaction_key == "HER":
                rows[catalyst] = {
                    "descriptor": "dG_H*",
                    "value_ev": descriptor,
                    "selectivity_note": "HER is more competitive when |dG_H*| is near 0 eV and the target reduction is sluggish.",
                    "primary_target_score": primary_results.get(catalyst, {}).get("score"),
                }
            else:
                rows[catalyst] = {
                    "descriptor": "user_provided",
                    "value": descriptor,
                    "selectivity_note": "Compare only with matching experimental conditions and reaction definitions.",
                    "primary_target_score": primary_results.get(catalyst, {}).get("score"),
                }
        output[reaction_key] = rows
    return output
