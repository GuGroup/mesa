"""OER algorithmic evaluator."""

from __future__ import annotations

from typing import Any

from ..constants import DEFAULT_OER_TOTAL_FREE_ENERGY_EV, OER_REVERSIBLE_POTENTIAL_V
from ..electrochemistry import find_step_index, largest_positive_transition, series_value, transitions


def evaluate_oer(
    catalysts: list[str],
    steps: list[str],
    values: dict[str, list[float]],
    metadata: dict[str, Any],
    input_data: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    missing = [label for label in ["*", "*OH", "*O", "*OOH"] if find_step_index(steps, label) is None]
    if missing:
        warnings.append(
            f"OER expected labels missing: {', '.join(missing)}. Falling back to generic ranking for affected catalyst(s)."
        )

    overall_free_energy = float(input_data.get("oer_total_free_energy_ev", DEFAULT_OER_TOTAL_FREE_ENERGY_EV))
    reversible_potential = float(input_data.get("oer_reversible_potential_v", OER_REVERSIBLE_POTENTIAL_V))
    results: dict[str, Any] = {}

    for catalyst in catalysts:
        series = values[catalyst]
        transition_rows = transitions(steps, series)
        g_clean = series_value(series, steps, "*")
        g_oh = series_value(series, steps, "*OH", "OH*")
        g_o = series_value(series, steps, "*O", "O*")
        g_ooh = series_value(series, steps, "*OOH", "OOH*")
        g_o2 = series_value(series, steps, "O2", "O2(g)")

        if None in {g_clean, g_oh, g_o, g_ooh}:
            limiting = largest_positive_transition(transition_rows)
            score = float(limiting["delta_g_ev"]) if limiting else 0.0
            results[catalyst] = {
                "mode": "OER_GENERIC_FALLBACK",
                "reaction_name": metadata["canonical_name"],
                "pds": limiting["label"] if limiting else None,
                "max_uphill_delta_g_ev": score,
                "score": score,
                "transitions": transition_rows,
            }
            continue

        assert g_clean is not None and g_oh is not None and g_o is not None and g_ooh is not None
        d_g_steps = [
            {"label": "* -> *OH", "start": "*", "end": "*OH", "delta_g_ev": g_oh - g_clean},
            {"label": "*OH -> *O", "start": "*OH", "end": "*O", "delta_g_ev": g_o - g_oh},
            {"label": "*O -> *OOH", "start": "*O", "end": "*OOH", "delta_g_ev": g_ooh - g_o},
        ]
        if g_o2 is not None:
            d_g4 = g_o2 - g_ooh
            final_reference = "provided O2 row"
        else:
            d_g4 = overall_free_energy - (g_ooh - g_clean)
            final_reference = f"overall OER free energy {overall_free_energy:.2f} eV"
        d_g_steps.append({"label": "*OOH -> O2 + *", "start": "*OOH", "end": "O2 + *", "delta_g_ev": d_g4})

        for step in d_g_steps:
            step["classification"] = "electrochemical"
            step["included_for_pds"] = True

        pds = max(d_g_steps, key=lambda item: item["delta_g_ev"])
        limiting_potential = float(pds["delta_g_ev"])
        overpotential = limiting_potential - reversible_potential
        results[catalyst] = {
            "mode": "OER",
            "reaction_name": metadata["canonical_name"],
            "descriptor": "max(ΔG1..ΔG4) - 1.23 V",
            "pds": pds["label"],
            "delta_g_pds_ev": limiting_potential,
            "limiting_potential_v": limiting_potential,
            "eta_calc_v": overpotential,
            "score": max(0.0, overpotential),
            "reversible_potential_v": reversible_potential,
            "final_reference": final_reference,
            "oer_steps": d_g_steps,
            "transitions": transition_rows,
        }

    ranking = sorted(
        [
            {
                "catalyst": catalyst,
                "metric": "eta_OER_calc_v",
                "score": results[catalyst]["score"],
                "pds": results[catalyst].get("pds"),
                "eta_calc_v": results[catalyst].get("eta_calc_v", results[catalyst].get("score")),
                "limiting_potential_v": results[catalyst].get("limiting_potential_v"),
            }
            for catalyst in catalysts
        ],
        key=lambda item: item["score"],
    )
    return results, ranking, warnings
