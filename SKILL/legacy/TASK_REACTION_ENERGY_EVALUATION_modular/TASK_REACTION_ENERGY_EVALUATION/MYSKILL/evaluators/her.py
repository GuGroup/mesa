"""HER algorithmic evaluator."""

from __future__ import annotations

from typing import Any

from ..electrochemistry import find_step_index, series_value, transitions


def evaluate_her(
    catalysts: list[str],
    steps: list[str],
    values: dict[str, list[float]],
    metadata: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    if find_step_index(steps, "*H", "H*") is None:
        warnings.append("HER descriptor could not find *H/H* label; fallback may be used.")

    results: dict[str, Any] = {}
    for catalyst in catalysts:
        series = values[catalyst]
        transition_rows = transitions(steps, series)
        g_clean = series_value(series, steps, "*")
        g_h = series_value(series, steps, "*H", "H*")
        if g_clean is not None and g_h is not None:
            delta_h = g_h - g_clean
            descriptor_source = "G(*H)-G(*)"
        else:
            h_transition = next((item for item in transition_rows if item["end"] == "*H"), None)
            if h_transition is None and transition_rows:
                h_transition = transition_rows[0]
                warnings.append(f"{catalyst}: using first transition as HER descriptor fallback.")
            delta_h = float(h_transition["delta_g_ev"]) if h_transition else 0.0
            descriptor_source = "transition fallback"
        results[catalyst] = {
            "mode": "HER",
            "reaction_name": metadata["canonical_name"],
            "descriptor": "dG_H*",
            "descriptor_source": descriptor_source,
            "delta_g_h_ev": delta_h,
            "score": abs(delta_h),
            "interpretation": "closer_to_zero_is_better",
            "limiting_potential_v": None,
            "transitions": transition_rows,
        }

    ranking = sorted(
        [
            {
                "catalyst": catalyst,
                "metric": "abs_dG_H*",
                "score": results[catalyst]["score"],
                "delta_g_h_ev": results[catalyst]["delta_g_h_ev"],
            }
            for catalyst in catalysts
        ],
        key=lambda item: item["score"],
    )
    return results, ranking, warnings
