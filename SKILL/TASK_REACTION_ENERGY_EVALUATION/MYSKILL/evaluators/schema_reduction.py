"""Schema-based evaluator for NO3RR, NO2RR, NRR, CO2RR, ORR, and similar paths."""

from __future__ import annotations

from typing import Any

from ..electrochemistry import CHEMICAL_ONLY_CLASSES, ELECTROCHEMICAL_PDS_CLASSES, find_step_index, largest_positive_transition, transitions


def evaluate_schema_reduction(
    catalysts: list[str],
    steps: list[str],
    values: dict[str, list[float]],
    metadata: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    expected_labels = metadata.get("expected_labels") or []
    missing = [label for label in expected_labels if find_step_index(steps, label) is None]
    if missing:
        warnings.append(f"{metadata['abbreviation']} expected labels missing: {', '.join(missing)}")

    results: dict[str, Any] = {}
    for catalyst in catalysts:
        transition_rows = transitions(steps, values[catalyst])
        electrochemical_candidates = [
            transition
            for transition in transition_rows
            if transition["delta_g_ev"] > 0 and transition["classification"] in ELECTROCHEMICAL_PDS_CLASSES
        ]
        pds = max(electrochemical_candidates, key=lambda item: item["delta_g_ev"], default=None)
        chemical_limiting = largest_positive_transition(transition_rows, include_classifications=CHEMICAL_ONLY_CLASSES)
        delta_pds = float(pds["delta_g_ev"]) if pds else 0.0
        results[catalyst] = {
            "mode": metadata["abbreviation"],
            "reaction_name": metadata["canonical_name"],
            "reaction_direction": metadata.get("direction"),
            "pds": pds["label"] if pds else None,
            "delta_g_pds_ev": delta_pds,
            "limiting_potential_v": -delta_pds if metadata.get("direction") == "reduction" else delta_pds,
            "eta_calc_v": delta_pds,
            "score": delta_pds,
            "chemical_limiting_step": chemical_limiting["label"] if chemical_limiting else None,
            "chemical_limiting_delta_g_ev": chemical_limiting["delta_g_ev"] if chemical_limiting else None,
            "transitions": transition_rows,
            "note": "Adsorption/desorption-only steps are reported separately and are not labeled as electrochemical overpotential.",
        }

    ranking = sorted(
        [
            {
                "catalyst": catalyst,
                "metric": "largest_uphill_electrochemical_step_ev",
                "score": results[catalyst]["score"],
                "pds": results[catalyst]["pds"],
                "eta_calc_v": results[catalyst]["eta_calc_v"],
                "limiting_potential_v": results[catalyst]["limiting_potential_v"],
            }
            for catalyst in catalysts
        ],
        key=lambda item: item["score"],
    )
    return results, ranking, warnings
