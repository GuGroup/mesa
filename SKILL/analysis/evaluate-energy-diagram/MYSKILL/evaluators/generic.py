"""Generic reaction-coordinate evaluator."""

from __future__ import annotations

from typing import Any

from ..electrochemistry import largest_positive_transition, transitions


def evaluate_generic(
    catalysts: list[str],
    steps: list[str],
    values: dict[str, list[float]],
    metadata: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    results: dict[str, Any] = {}
    for catalyst in catalysts:
        transition_rows = transitions(steps, values[catalyst])
        limiting = largest_positive_transition(transition_rows)
        score = float(limiting["delta_g_ev"]) if limiting else 0.0
        results[catalyst] = {
            "mode": "GENERIC",
            "reaction_name": metadata.get("canonical_name", "generic reaction energy evaluation"),
            "limiting_uphill_step": limiting["label"] if limiting else None,
            "max_uphill_delta_g_ev": score,
            "score": score,
            "transitions": transition_rows,
        }
    ranking = sorted(
        [
            {
                "catalyst": catalyst,
                "metric": "max_uphill_delta_g_ev",
                "score": results[catalyst]["score"],
                "limiting_step": results[catalyst]["limiting_uphill_step"],
            }
            for catalyst in catalysts
        ],
        key=lambda item: item["score"],
    )
    return results, ranking, []
