"""Schema-based evaluator for NO3RR, NO2RR, NRR, CO2RR, ORR, and similar paths."""

from __future__ import annotations

from typing import Any

from ..electrochemistry import (
    CHEMICAL_ONLY_CLASSES,
    ELECTROCHEMICAL_PDS_CLASSES,
    find_step_index,
    largest_positive_transition,
    transitions,
)
from .downhill import analyze_downhill_profile, downhill_ranking_record


def _screening_record_from_analysis(catalyst: str, analysis: dict[str, Any]) -> dict[str, Any]:
    """Use the same low-confidence fallback metric for every catalyst in a mixed case."""
    raw_score = analysis.get("least_favorable_delta_g_at_input_ev")
    return {
        "catalyst": catalyst,
        "metric": "least_favorable_step_at_input_ev_screening_only",
        "score": float(raw_score) if raw_score is not None else 0.0,
        "pds": None,
        "least_favorable_step": analysis.get("least_favorable_step_at_input"),
        "eta_calc_v": None,
        "limiting_potential_v": None,
        "ranking_status": "secondary_screening_only_incomparable_potential_metadata",
        "thermodynamic_ranking_resolved": False,
        "performance_ranking_definitive": False,
        "ranking_confidence": "low",
    }


def evaluate_schema_reduction(
    catalysts: list[str],
    steps: list[str],
    values: dict[str, list[float]],
    metadata: dict[str, Any],
    input_data: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    input_data = input_data or {}
    warnings: list[str] = []
    expected_labels = metadata.get("expected_labels") or []
    missing = [label for label in expected_labels if find_step_index(steps, label) is None]
    if missing:
        warnings.append(f"{metadata['abbreviation']} expected labels missing: {', '.join(missing)}")

    results: dict[str, Any] = {}
    analyses: dict[str, dict[str, Any]] = {}
    for catalyst in catalysts:
        transition_rows = transitions(steps, values[catalyst])
        downhill_analysis, downhill_warnings = analyze_downhill_profile(
            catalyst,
            steps,
            values[catalyst],
            transition_rows,
            metadata,
            input_data,
        )
        warnings.extend(downhill_warnings)
        analyses[catalyst] = downhill_analysis

        # Conventional input-potential PDS: only an uphill electrochemical/unknown
        # step is called an uphill PDS here.  All-downhill profiles are handled
        # separately below and must not be forced to score zero.
        electrochemical_uphill = [
            transition
            for transition in transition_rows
            if transition["delta_g_ev"] > 0
            and transition["classification"] in ELECTROCHEMICAL_PDS_CLASSES
        ]
        uphill_pds = max(electrochemical_uphill, key=lambda item: item["delta_g_ev"], default=None)
        chemical_limiting = largest_positive_transition(
            transition_rows,
            include_classifications=CHEMICAL_ONLY_CLASSES,
        )
        delta_pds = float(uphill_pds["delta_g_ev"]) if uphill_pds else 0.0

        results[catalyst] = {
            "mode": metadata["abbreviation"],
            "reaction_name": metadata["canonical_name"],
            "reaction_direction": metadata.get("direction"),
            "pds": uphill_pds["label"] if uphill_pds else None,
            "delta_g_pds_ev": delta_pds if uphill_pds else None,
            "limiting_potential_v": -delta_pds if uphill_pds and metadata.get("direction") == "reduction" else None,
            "eta_calc_v": delta_pds if uphill_pds else None,
            "score": delta_pds if uphill_pds else None,
            "chemical_limiting_step": chemical_limiting["label"] if chemical_limiting else None,
            "chemical_limiting_delta_g_ev": chemical_limiting["delta_g_ev"] if chemical_limiting else None,
            "transitions": transition_rows,
            "all_downhill_analysis": downhill_analysis,
            "note": (
                "Adsorption/desorption-only steps are reported separately and are not labeled as electrochemical "
                "overpotential. All-downhill profiles are re-evaluated with the dedicated downhill/potential logic."
            ),
        }

    all_downhill = bool(catalysts) and all(
        analyses[catalyst]["all_downhill_electrochemical_steps"] for catalyst in catalysts
    )

    if all_downhill:
        candidate_rows = [downhill_ranking_record(catalyst, analyses[catalyst]) for catalyst in catalysts]
        statuses = {row["ranking_status"] for row in candidate_rows}
        if len(statuses) == 1:
            ranking = sorted(candidate_rows, key=lambda item: item["score"])
        else:
            # Comparing eta, limiting-potential-only, and raw-slope metrics in a
            # single list would be dimensionally and scientifically invalid.
            ranking = sorted(
                [_screening_record_from_analysis(catalyst, analyses[catalyst]) for catalyst in catalysts],
                key=lambda item: item["score"],
            )
            warnings.append(
                "All catalysts are downhill, but their potential-analysis metadata are not mutually comparable. "
                "The displayed order is secondary screening only, not a thermodynamic performance ranking."
            )

        for row in ranking:
            catalyst = row["catalyst"]
            result = results[catalyst]
            analysis = analyses[catalyst]
            potential = analysis["potential_analysis"]
            result.update(
                {
                    "evaluation_mode": analysis["evaluation_mode"],
                    "ranking_status": row["ranking_status"],
                    "ranking_confidence": row["ranking_confidence"],
                    "thermodynamic_ranking_resolved": row["thermodynamic_ranking_resolved"],
                    "performance_ranking_definitive": False,
                    "pds": row.get("pds"),
                    "score": row["score"],
                    "limiting_potential_v": row.get("limiting_potential_v"),
                    "eta_calc_v": row.get("eta_calc_v"),
                    "delta_g_pds_ev": potential.get("max_residual_uphill_delta_g_ev"),
                }
            )
        if ranking and ranking[0].get("thermodynamic_ranking_resolved"):
            warnings.append(
                "All-downhill catalysts were compared at the supplied common equilibrium potential. "
                "This resolves only the thermodynamic limiting-potential/overpotential ordering; kinetics, selectivity, "
                "desorption, coverage, and stability can change the experimental order."
            )
        else:
            warnings.append(
                "All catalysts are downhill at the input potential. Do not select the catalyst with the steeper raw "
                "slope as intrinsically superior. Provide equilibrium_potential_v, energy_reference_potential_v, and "
                "step_electron_counts or state_electron_counts for a potential-based comparison."
            )
        return results, ranking, warnings

    # Backward-compatible conventional ranking when at least one catalyst has an
    # uphill step at the input potential.  A downhill catalyst receives zero
    # input-potential uphill penalty, but its result still carries the dedicated
    # diagnostics and confidence fields.
    ranking = []
    for catalyst in catalysts:
        result = results[catalyst]
        analysis = analyses[catalyst]
        uphill_score = result["score"] if result["score"] is not None else 0.0
        ranking.append(
            {
                "catalyst": catalyst,
                "metric": "largest_uphill_electrochemical_step_ev_at_input_potential",
                "score": uphill_score,
                "pds": result["pds"],
                "eta_calc_v": result["eta_calc_v"],
                "limiting_potential_v": result["limiting_potential_v"],
                "ranking_status": "input_potential_uphill_screening",
                "thermodynamic_ranking_resolved": False,
                "performance_ranking_definitive": False,
                "ranking_confidence": analysis["ranking_confidence"],
            }
        )
        result["evaluation_mode"] = analysis["evaluation_mode"]
        result["ranking_status"] = "input_potential_uphill_screening"
        result["ranking_confidence"] = analysis["ranking_confidence"]
        result["thermodynamic_ranking_resolved"] = False
        result["performance_ranking_definitive"] = False
    ranking.sort(key=lambda item: item["score"])
    return results, ranking, warnings
