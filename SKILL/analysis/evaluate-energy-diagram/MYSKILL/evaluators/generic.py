"""Generic reaction-coordinate evaluator with explicit all-downhill handling."""

from __future__ import annotations

from typing import Any

from ..electrochemistry import largest_positive_transition, transitions
from .downhill import analyze_downhill_profile, downhill_ranking_record


def evaluate_generic(
    catalysts: list[str],
    steps: list[str],
    values: dict[str, list[float]],
    metadata: dict[str, Any],
    input_data: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    input_data = input_data or {}
    warnings: list[str] = []
    results: dict[str, Any] = {}
    analyses: dict[str, dict[str, Any]] = {}

    for catalyst in catalysts:
        transition_rows = transitions(steps, values[catalyst])
        analysis, analysis_warnings = analyze_downhill_profile(
            catalyst,
            steps,
            values[catalyst],
            transition_rows,
            metadata,
            input_data,
        )
        warnings.extend(analysis_warnings)
        analyses[catalyst] = analysis
        limiting = largest_positive_transition(transition_rows)
        score = float(limiting["delta_g_ev"]) if limiting else None
        results[catalyst] = {
            "mode": "GENERIC",
            "reaction_name": metadata.get("canonical_name", "generic reaction energy evaluation"),
            "limiting_uphill_step": limiting["label"] if limiting else None,
            "max_uphill_delta_g_ev": score,
            "score": score,
            "transitions": transition_rows,
            "all_downhill_analysis": analysis,
            "evaluation_mode": analysis["evaluation_mode"],
            "performance_ranking_definitive": False,
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
            ranking = []
            for catalyst in catalysts:
                analysis = analyses[catalyst]
                score = float(analysis.get("least_favorable_delta_g_at_input_ev") or 0.0)
                ranking.append(
                    {
                        "catalyst": catalyst,
                        "metric": "least_favorable_downhill_step_ev_screening_only",
                        "score": score,
                        "pds": None,
                        "least_favorable_step": analysis.get("least_favorable_step_at_input"),
                        "eta_calc_v": None,
                        "limiting_potential_v": None,
                        "ranking_status": "secondary_screening_only_incomparable_potential_metadata",
                        "thermodynamic_ranking_resolved": False,
                        "performance_ranking_definitive": False,
                        "ranking_confidence": "low",
                    }
                )
            ranking.sort(key=lambda item: item["score"])
            warnings.append(
                "Generic all-downhill profiles do not share comparable potential metadata; the displayed order is screening only."
            )

        for row in ranking:
            result = results[row["catalyst"]]
            result.update(
                {
                    "score": row["score"],
                    "pds": row.get("pds"),
                    "limiting_potential_v": row.get("limiting_potential_v"),
                    "eta_calc_v": row.get("eta_calc_v"),
                    "ranking_status": row["ranking_status"],
                    "ranking_confidence": row["ranking_confidence"],
                    "thermodynamic_ranking_resolved": row["thermodynamic_ranking_resolved"],
                }
            )
        warnings.append(
            "All generic profiles are downhill at the input potential. Raw slope alone is not a validated activity metric; "
            "use a common equilibrium potential and explicit electron counts when the reaction is electrochemical."
        )
        return results, ranking, warnings

    ranking = sorted(
        [
            {
                "catalyst": catalyst,
                "metric": "max_uphill_delta_g_ev",
                "score": results[catalyst]["score"] if results[catalyst]["score"] is not None else 0.0,
                "limiting_step": results[catalyst]["limiting_uphill_step"],
                "ranking_status": "input_potential_uphill_screening",
                "thermodynamic_ranking_resolved": False,
                "performance_ranking_definitive": False,
                "ranking_confidence": analyses[catalyst]["ranking_confidence"],
            }
            for catalyst in catalysts
        ],
        key=lambda item: item["score"],
    )
    return results, ranking, warnings
