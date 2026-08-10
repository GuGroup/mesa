"""Conditional routing from energy-diagram evaluation to Sabatier analysis.

This module does not execute another Codex skill from Python. Instead, it emits
a deterministic, machine-readable handoff when a comparative energy diagram
does not identify one unique thermodynamic best catalyst. The host agent reads
the handoff, opens ``SKILL/figure/plot-sabatier-volcano/SKILL.md``, and invokes
the skill declared there.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Sequence

from .electrochemistry import ELECTROCHEMICAL_PDS_CLASSES
from .errors import MesaValidationError
from .utils import is_number, safe_string

# The directory name intentionally follows the repository path supplied by the
# project. Keep the path authoritative even though "Sabatier" and "volcano"
# are misspelled in the directory name.
TARGET_SKILL = "plot-sabatier-volcano"
TARGET_SKILL_DISPLAY_NAME = "plot-sabatier-volcano"
TARGET_SKILL_PATH = "SKILL/figure/plot-sabatier-volcano"
TARGET_SKILL_INVOCATION = "$plot-sabatier-volcano"
DEFAULT_DOWNHILL_TOLERANCE_EV = 1.0e-9
DEFAULT_TRIGGER_SCOPE = "all_steps"
VALID_TRIGGER_SCOPES = {"all_steps", "electrochemical"}


def _handoff_enabled(input_data: dict[str, Any]) -> tuple[bool, str]:
    """Resolve the new switch while preserving the former input alias."""
    if "enable_unresolved_volcano_handoff" in input_data:
        return bool(input_data["enable_unresolved_volcano_handoff"]), "enable_unresolved_volcano_handoff"
    if "enable_downhill_volcano_handoff" in input_data:
        return bool(input_data["enable_downhill_volcano_handoff"]), "enable_downhill_volcano_handoff"
    return True, "default"


def _tolerance(input_data: dict[str, Any]) -> float:
    value = input_data.get("downhill_tolerance_ev", DEFAULT_DOWNHILL_TOLERANCE_EV)
    if not is_number(value):
        raise MesaValidationError(f"downhill_tolerance_ev must be numeric, got {value!r}.")
    return abs(float(value))


def _trigger_scope(input_data: dict[str, Any]) -> str:
    scope = safe_string(input_data.get("downhill_trigger_scope") or DEFAULT_TRIGGER_SCOPE).lower()
    if scope not in VALID_TRIGGER_SCOPES:
        raise MesaValidationError(
            "downhill_trigger_scope must be 'all_steps' or 'electrochemical', "
            f"got {scope!r}."
        )
    return scope


def _has_equilibrium_rows(result: dict[str, Any]) -> bool:
    analysis = result.get("all_downhill_analysis") or {}
    potential = analysis.get("potential_analysis") or {}
    rows = potential.get("equilibrium_steps")
    if not isinstance(rows, list) or not rows:
        return False
    return all(row.get("delta_g_at_equilibrium_ev") is not None for row in rows)


def _common_comparison_basis(results: dict[str, Any], catalysts: Sequence[str]) -> str:
    """Choose one basis for every catalyst; never mix equilibrium and raw rows."""
    if catalysts and all(_has_equilibrium_rows(results.get(catalyst, {})) for catalyst in catalysts):
        return "equilibrium_potential_profile"
    if catalysts and all(isinstance(results.get(catalyst, {}).get("oer_steps"), list) for catalyst in catalysts):
        return "algorithmic_oer_profile"
    return "input_profile"


def _raw_rows(result: dict[str, Any], basis: str) -> list[dict[str, Any]]:
    if basis == "equilibrium_potential_profile":
        analysis = result.get("all_downhill_analysis") or {}
        potential = analysis.get("potential_analysis") or {}
        output: list[dict[str, Any]] = []
        for row in potential.get("equilibrium_steps") or []:
            output.append(
                {
                    "label": row.get("label"),
                    "classification": row.get("classification") or "unknown",
                    "electron_count": row.get("electron_count"),
                    "delta_g_ev": row.get("delta_g_at_equilibrium_ev"),
                }
            )
        return output
    if basis == "algorithmic_oer_profile":
        return [dict(row) for row in result.get("oer_steps") or []]
    return [dict(row) for row in result.get("transitions") or []]


def _eligible_rows(rows: Sequence[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    eligible: list[dict[str, Any]] = []
    for row in rows:
        if row.get("classification") == "duplicate":
            continue
        if row.get("delta_g_ev") is None or not is_number(row.get("delta_g_ev")):
            continue
        if scope == "electrochemical":
            classification = row.get("classification") or "unknown"
            electron_count = row.get("electron_count")
            potential_coupled = bool(is_number(electron_count) and float(electron_count) > 0)
            if classification not in ELECTROCHEMICAL_PDS_CLASSES and not potential_coupled:
                continue
        eligible.append(row)
    return eligible


def _profile_diagnostic(result: dict[str, Any], basis: str, scope: str, tolerance: float) -> dict[str, Any]:
    rows = _eligible_rows(_raw_rows(result, basis), scope)
    if not rows:
        return {
            "all_downhill": False,
            "evaluable": False,
            "basis": basis,
            "scope": scope,
            "transition_count": 0,
            "reason": "No eligible reaction transitions were available for the downhill trigger.",
            "transitions": [],
        }
    least_favorable = max(rows, key=lambda row: float(row["delta_g_ev"]))
    all_downhill = all(float(row["delta_g_ev"]) <= tolerance for row in rows)
    return {
        "all_downhill": all_downhill,
        "evaluable": True,
        "basis": basis,
        "scope": scope,
        "transition_count": len(rows),
        "least_favorable_step": least_favorable.get("label"),
        "least_favorable_delta_g_ev": float(least_favorable["delta_g_ev"]),
        "max_delta_g_ev": float(least_favorable["delta_g_ev"]),
        "transitions": [
            {
                "label": row.get("label"),
                "classification": row.get("classification"),
                "electron_count": row.get("electron_count"),
                "delta_g_ev": float(row["delta_g_ev"]),
            }
            for row in rows
        ],
    }


def _energy_csv_text(steps: Sequence[str], catalysts: Sequence[str], values: dict[str, list[float]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["step", *catalysts])
    for index, step in enumerate(steps):
        writer.writerow([step, *[values[catalyst][index] for catalyst in catalysts]])
    return buffer.getvalue()


def _descriptor_candidates(result: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    if is_number(result.get("delta_g_h_ev")):
        output["dG_H_star_ev"] = float(result["delta_g_h_ev"])
    analysis = result.get("all_downhill_analysis") or {}
    secondary = analysis.get("secondary_metrics") or {}
    for key in (
        "deepest_intermediate",
        "deepest_intermediate_energy_ev",
        "energy_well_depth_from_initial_ev",
        "escape_energy_from_deepest_to_final_ev",
        "largest_desorption_delta_g_ev",
        "overall_driving_force_ev",
    ):
        if key in secondary:
            output[key] = secondary[key]
    return output


def _ranking_resolution(
    ranking: Sequence[dict[str, Any]], tolerance: float
) -> dict[str, Any]:
    """Determine whether the evaluator identified exactly one thermodynamic best.

    Ranking rows are already ordered by the reaction-specific evaluator. A
    unique best requires a resolved ranking, a numerical top score, and no
    second catalyst tied with that score within the configured tolerance.
    """
    if len(ranking) < 2:
        return {
            "evaluable": False,
            "unique_best": False,
            "reason_code": "fewer_than_two_ranked_catalysts",
            "top_score": None,
            "top_candidates": [],
        }

    top_score = ranking[0].get("score")
    if not is_number(top_score):
        return {
            "evaluable": False,
            "unique_best": False,
            "reason_code": "top_score_not_numeric",
            "top_score": None,
            "top_candidates": [],
        }

    resolved = all(row.get("thermodynamic_ranking_resolved", True) for row in ranking)
    top_score_value = float(top_score)
    top_candidates = [
        safe_string(row.get("catalyst"))
        for row in ranking
        if is_number(row.get("score"))
        and abs(float(row["score"]) - top_score_value) <= tolerance
    ]
    if not resolved:
        reason_code = "thermodynamic_ranking_unresolved"
    elif len(top_candidates) != 1:
        reason_code = "top_score_tie"
    else:
        reason_code = "unique_thermodynamic_best_identified"
    return {
        "evaluable": True,
        "unique_best": resolved and len(top_candidates) == 1,
        "thermodynamic_ranking_resolved": resolved,
        "reason_code": reason_code,
        "top_score": top_score_value,
        "top_candidates": top_candidates,
    }


def build_volcano_handoff(
    input_data: dict[str, Any],
    reaction_type: str,
    reaction_metadata: dict[str, Any],
    steps: list[str],
    catalysts: list[str],
    values: dict[str, list[float]],
    results: dict[str, Any],
    ranking: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a conditional handoff to the configured Sabatier-volcano skill.

    Trigger when at least two catalyst profiles and ranking rows are evaluable,
    but the thermodynamic evaluation does not identify one unique best
    catalyst. Uphill steps remain part of the diagnostics and no longer block
    the handoff. If an equilibrium-potential profile is available for every
    catalyst, that basis takes precedence over the raw input profile.
    """
    enabled, enabled_source = _handoff_enabled(input_data)
    tolerance = _tolerance(input_data)
    scope = _trigger_scope(input_data)
    basis = _common_comparison_basis(results, catalysts)
    diagnostics = {
        catalyst: _profile_diagnostic(results.get(catalyst, {}), basis, scope, tolerance)
        for catalyst in catalysts
    }
    enough_catalysts = len(catalysts) >= 2
    all_evaluable = bool(catalysts) and all(row["evaluable"] for row in diagnostics.values())
    all_downhill = all_evaluable and all(row["all_downhill"] for row in diagnostics.values())
    ranking_resolution = _ranking_resolution(ranking, tolerance)
    triggered = (
        enabled
        and enough_catalysts
        and all_evaluable
        and ranking_resolution["evaluable"]
        and not ranking_resolution["unique_best"]
    )

    raw_diagnostics = {
        catalyst: _profile_diagnostic(results.get(catalyst, {}), "input_profile", scope, tolerance)
        for catalyst in catalysts
    }
    raw_all_downhill = bool(catalysts) and all(
        row["evaluable"] and row["all_downhill"] for row in raw_diagnostics.values()
    )

    if not enabled:
        reason = "The unresolved-ranking-to-volcano handoff was disabled by input."
    elif not enough_catalysts:
        reason = "At least two catalysts are required for comparative Sabatier-volcano routing."
    elif not all_evaluable:
        reason = "At least one catalyst had no eligible transitions for comparative routing."
    elif not ranking_resolution["evaluable"]:
        reason = "At least two numerical catalyst ranking rows are required for comparative Sabatier-volcano routing."
    elif not ranking_resolution["unique_best"]:
        reason = (
            "The energy-diagram evaluation did not identify one unique thermodynamic best catalyst "
            f"({ranking_resolution['reason_code']}). Continue with Sabatier-volcano analysis; "
            "uphill steps remain screening evidence but do not block this handoff."
        )
    else:
        reason = "The energy-diagram evaluation identified one unique thermodynamic best catalyst; no automatic volcano handoff is required."

    handoff_payload: dict[str, Any] | None = None
    if triggered:
        handoff_payload = {
            "schema_version": "1.0",
            "source_skill": "evaluate-energy-diagram",
            "source_trigger": ranking_resolution["reason_code"],
            "target_skill": TARGET_SKILL,
            "target_skill_display_name": TARGET_SKILL_DISPLAY_NAME,
            "target_skill_path": TARGET_SKILL_PATH,
            "target_skill_resolution": (
                "Read the target SKILL.md at target_skill_path and invoke the name declared in its front matter. "
                "Use the provided invocation as the fallback when the declared name matches the directory name."
            ),
            "reaction_type": reaction_type,
            "reaction_name": reaction_metadata.get("canonical_name"),
            "reaction_metadata": reaction_metadata,
            "comparison_basis": basis,
            "downhill_trigger_scope": scope,
            "downhill_tolerance_ev": tolerance,
            "steps": steps,
            "catalysts": catalysts,
            "energy_data": {"steps": steps, "energies": values},
            "csv_text": _energy_csv_text(steps, catalysts, values),
            "downhill_diagnostics": diagnostics,
            "ranking_resolution": ranking_resolution,
            "screening_ranking": ranking,
            "descriptor_candidates": {
                catalyst: _descriptor_candidates(results.get(catalyst, {})) for catalyst in catalysts
            },
            "user_descriptor": input_data.get("volcano_descriptor"),
            "user_activity_metric": input_data.get("volcano_activity_metric"),
            "electrochemical_reference_to_read_first": "MYSKILL/electrochemical.md",
            "sabatier_requirements": {
                "apply_sabatier_principle": True,
                "preserve_uphill_step_screening_evidence": True,
                "do_not_rank_by_steepest_downhill_slope": True,
                "do_not_treat_most_negative_overall_energy_as_automatically_best": True,
                "select_or_validate_a_reaction_specific_binding_descriptor": True,
                "distinguish_weak_binding_optimal_binding_and_strong_binding_branches": True,
                "report_that_two_catalysts_are_insufficient_to_fit_an_empirical_volcano_without_an_external_relation": len(catalysts) == 2,
            },
        }

    return {
        "triggered": triggered,
        "target_skill": TARGET_SKILL if triggered else None,
        "target_skill_display_name": TARGET_SKILL_DISPLAY_NAME if triggered else None,
        "target_skill_path": TARGET_SKILL_PATH if triggered else None,
        "configured_target_skill_path": TARGET_SKILL_PATH,
        "invocation": TARGET_SKILL_INVOCATION if triggered else None,
        "invocation_strategy": (
            "read_target_skill_md_then_invoke_declared_name" if triggered else None
        ),
        "condition": "comparative_thermodynamic_ranking_not_unique",
        "enabled": enabled,
        "enabled_source": enabled_source,
        "comparison_basis": basis,
        "scope": scope,
        "tolerance_ev": tolerance,
        "raw_profiles_all_downhill": raw_all_downhill,
        "all_downhill_across_catalysts": all_downhill,
        "unique_best_catalyst_identified": ranking_resolution["unique_best"],
        "ranking_resolution": ranking_resolution,
        "diagnostics": diagnostics,
        "reason": reason,
        "handoff_payload": handoff_payload,
    }
