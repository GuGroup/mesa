"""All-downhill and electrode-potential analysis for reaction-energy profiles.

The ordinary ``largest positive ΔG`` rule cannot distinguish catalysts when all
potential-coupled steps are exergonic at the input potential.  This module keeps
that case explicit and, when sufficient electrochemical metadata are supplied,
re-evaluates the steps at a common equilibrium potential and derives the
thermodynamic limiting potential.

The module is deliberately conservative.  A steeper downhill profile is not
silently interpreted as a faster or more selective catalyst, and missing
per-step electron counts prevent potential-dependent ranking rather than being
filled with guessed stoichiometry.
"""

from __future__ import annotations

from statistics import pstdev
from typing import Any, Sequence

from ..chemistry import canonical_label
from ..electrochemistry import CHEMICAL_ONLY_CLASSES, ELECTROCHEMICAL_PDS_CLASSES
from ..errors import MesaValidationError
from ..utils import is_number, safe_string

DEFAULT_DOWNHILL_TOLERANCE_EV = 1.0e-9
DEFAULT_CYCLE_CLOSURE_TOLERANCE_EV = 0.05


def _optional_float(input_data: dict[str, Any], *keys: str) -> tuple[float | None, str | None]:
    for key in keys:
        if key not in input_data or input_data[key] in {None, ""}:
            continue
        if not is_number(input_data[key]):
            raise MesaValidationError(f"{key} must be a finite number, got {input_data[key]!r}.")
        return float(input_data[key]), key
    return None, None


def _nonnegative_count(value: Any, label: str) -> float:
    if not is_number(value):
        raise MesaValidationError(f"Electron count for {label} must be numeric, got {value!r}.")
    count = float(value)
    if count < 0:
        raise MesaValidationError(f"Electron count for {label} must be non-negative, got {count}.")
    return count


def _canonical_transition_key(label: str) -> str:
    if "->" not in label:
        return safe_string(label)
    start, end = label.split("->", 1)
    return f"{canonical_label(start)} -> {canonical_label(end)}"


def _counts_from_step_mapping(
    raw_counts: Any,
    transition_rows: Sequence[dict[str, Any]],
) -> list[float | None] | None:
    if raw_counts is None:
        return None
    if isinstance(raw_counts, (list, tuple)):
        if len(raw_counts) != len(transition_rows):
            raise MesaValidationError(
                "step_electron_counts must contain one value per transition "
                f"({len(transition_rows)} expected, {len(raw_counts)} provided)."
            )
        return [_nonnegative_count(value, transition_rows[index]["label"]) for index, value in enumerate(raw_counts)]
    if isinstance(raw_counts, dict):
        normalized: dict[str, Any] = {}
        for key, value in raw_counts.items():
            text_key = safe_string(key)
            normalized[text_key] = value
            normalized[_canonical_transition_key(text_key)] = value
        counts: list[float | None] = []
        for index, row in enumerate(transition_rows):
            candidate_keys = [
                row["label"],
                _canonical_transition_key(row["label"]),
                str(index),
                str(index + 1),
            ]
            found = next((normalized[key] for key in candidate_keys if key in normalized), None)
            counts.append(None if found is None else _nonnegative_count(found, row["label"]))
        return counts
    raise MesaValidationError("step_electron_counts must be a list or transition-label dictionary.")


def _state_count_values(raw_counts: Any, steps: Sequence[str]) -> list[float] | None:
    if raw_counts is None:
        return None
    if isinstance(raw_counts, (list, tuple)):
        if len(raw_counts) != len(steps):
            raise MesaValidationError(
                "state_electron_counts must contain one cumulative value per state "
                f"({len(steps)} expected, {len(raw_counts)} provided)."
            )
        return [_nonnegative_count(value, f"state {steps[index]}") for index, value in enumerate(raw_counts)]
    if isinstance(raw_counts, dict):
        normalized = {canonical_label(key): value for key, value in raw_counts.items()}
        by_index = {safe_string(key): value for key, value in raw_counts.items()}
        values: list[float] = []
        for index, step in enumerate(steps):
            key = canonical_label(step)
            if key in normalized:
                raw_value = normalized[key]
            elif str(index) in by_index:
                raw_value = by_index[str(index)]
            else:
                raise MesaValidationError(
                    f"state_electron_counts is missing a cumulative value for state {index}: {step}."
                )
            values.append(_nonnegative_count(raw_value, f"state {step}"))
        return values
    raise MesaValidationError("state_electron_counts must be a list or state-label dictionary.")


def resolve_transition_electron_counts(
    input_data: dict[str, Any],
    steps: Sequence[str],
    transition_rows: Sequence[dict[str, Any]],
) -> tuple[list[float | None], str, list[str]]:
    """Resolve transferred electrons for each transition.

    Precedence is explicit ``step_electron_counts``, explicit cumulative
    ``state_electron_counts``, and finally an opt-in one-electron assumption.
    Pure adsorption/desorption and duplicate transitions default to zero
    electrons.  Missing counts for potential-coupled steps remain ``None``.
    """
    warnings: list[str] = []
    explicit_step = _counts_from_step_mapping(input_data.get("step_electron_counts"), transition_rows)
    if explicit_step is not None:
        counts = explicit_step
        source = "step_electron_counts"
    else:
        state_values = _state_count_values(input_data.get("state_electron_counts"), steps)
        if state_values is not None:
            counts = []
            for index in range(1, len(state_values)):
                delta = state_values[index] - state_values[index - 1]
                if delta < -DEFAULT_DOWNHILL_TOLERANCE_EV:
                    raise MesaValidationError(
                        "state_electron_counts must be cumulative and non-decreasing in the stated reaction direction."
                    )
                counts.append(max(0.0, delta))
            source = "state_electron_counts"
        else:
            counts = [None] * len(transition_rows)
            source = "not_provided"

    assume_one = bool(input_data.get("assume_one_electron_per_electrochemical_step", False))
    for index, row in enumerate(transition_rows):
        classification = row.get("classification")
        if counts[index] is not None:
            continue
        if classification in CHEMICAL_ONLY_CLASSES or classification == "duplicate":
            counts[index] = 0.0
        elif assume_one and classification in ELECTROCHEMICAL_PDS_CLASSES:
            counts[index] = 1.0
            if source == "not_provided":
                source = "one_electron_assumption"

    if source == "one_electron_assumption":
        warnings.append(
            "A one-electron count was assumed for each label-classified electrochemical/unknown step. "
            "Verify this assumption for multielectron or chemically coupled steps."
        )
    return counts, source, warnings


def _direction(input_data: dict[str, Any], metadata: dict[str, Any]) -> str:
    requested = safe_string(input_data.get("reaction_direction") or metadata.get("direction")).lower()
    if requested in {"reduction", "cathodic"}:
        return "reduction"
    if requested in {"oxidation", "anodic"}:
        return "oxidation"
    return "unknown"


def _potential_shifted_delta_g(
    delta_g_reference_ev: float,
    electron_count: float,
    target_potential_v: float,
    reference_potential_v: float,
    direction: str,
) -> float:
    delta_u = target_potential_v - reference_potential_v
    if direction == "reduction":
        # A reduction step consumes electrons: ΔG(U) = ΔG(U_ref) + n e (U-U_ref).
        return delta_g_reference_ev + electron_count * delta_u
    if direction == "oxidation":
        # An oxidation step releases electrons: ΔG(U) = ΔG(U_ref) - n e (U-U_ref).
        return delta_g_reference_ev - electron_count * delta_u
    raise MesaValidationError("reaction_direction must be reduction or oxidation for potential analysis.")


def _limiting_potential_boundary(
    delta_g_reference_ev: float,
    electron_count: float,
    reference_potential_v: float,
    direction: str,
) -> float:
    if direction == "reduction":
        return reference_potential_v - delta_g_reference_ev / electron_count
    if direction == "oxidation":
        return reference_potential_v + delta_g_reference_ev / electron_count
    raise MesaValidationError("reaction_direction must be reduction or oxidation for potential analysis.")


def _secondary_metrics(steps: Sequence[str], series: Sequence[float], transition_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    deltas = [float(row["delta_g_ev"]) for row in transition_rows]
    relevant_deltas = [
        float(row["delta_g_ev"])
        for row in transition_rows
        if row.get("classification") in ELECTROCHEMICAL_PDS_CLASSES
    ]
    interior_indices = list(range(1, max(1, len(series) - 1)))
    if not interior_indices and series:
        interior_indices = list(range(len(series)))
    deepest_index = min(interior_indices, key=lambda index: float(series[index])) if interior_indices else None
    deepest_value = float(series[deepest_index]) if deepest_index is not None else None
    initial = float(series[0])
    final = float(series[-1])
    desorption_rows = [
        row
        for row in transition_rows
        if row.get("classification") in {"desorption", "desorption_or_surface_cleanup"}
    ]
    max_desorption = max(desorption_rows, key=lambda row: float(row["delta_g_ev"]), default=None)
    largest_drop = min(transition_rows, key=lambda row: float(row["delta_g_ev"]), default=None)
    return {
        "overall_driving_force_ev": final - initial,
        "deepest_intermediate": steps[deepest_index] if deepest_index is not None else None,
        "deepest_intermediate_energy_ev": deepest_value,
        "energy_well_depth_from_initial_ev": None if deepest_value is None else deepest_value - initial,
        "escape_energy_from_deepest_to_final_ev": None if deepest_value is None else final - deepest_value,
        "largest_exergonic_step": largest_drop["label"] if largest_drop else None,
        "largest_exergonic_delta_g_ev": float(largest_drop["delta_g_ev"]) if largest_drop else None,
        "step_roughness_pstdev_ev": pstdev(relevant_deltas or deltas) if len(relevant_deltas or deltas) > 1 else 0.0,
        "largest_desorption_step": max_desorption["label"] if max_desorption else None,
        "largest_desorption_delta_g_ev": float(max_desorption["delta_g_ev"]) if max_desorption else None,
        "overbinding_conclusion": "not_determined_from_downhill_slope_alone",
    }


def analyze_downhill_profile(
    catalyst: str,
    steps: list[str],
    series: list[float],
    transition_rows: list[dict[str, Any]],
    metadata: dict[str, Any],
    input_data: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Analyze an individual profile, including optional equilibrium-potential transformation."""
    warnings: list[str] = []
    tolerance_value, _ = _optional_float(input_data, "downhill_tolerance_ev")
    tolerance = DEFAULT_DOWNHILL_TOLERANCE_EV if tolerance_value is None else abs(tolerance_value)
    closure_tol_value, _ = _optional_float(input_data, "cycle_closure_tolerance_ev")
    closure_tolerance = (
        DEFAULT_CYCLE_CLOSURE_TOLERANCE_EV if closure_tol_value is None else abs(closure_tol_value)
    )

    relevant_rows = [
        row for row in transition_rows if row.get("classification") in ELECTROCHEMICAL_PDS_CLASSES
    ]
    all_downhill_electrochemical = bool(relevant_rows) and all(
        float(row["delta_g_ev"]) <= tolerance for row in relevant_rows
    )
    all_downhill_all_steps = bool(transition_rows) and all(
        float(row["delta_g_ev"]) <= tolerance for row in transition_rows
    )
    least_favorable = max(relevant_rows, key=lambda row: float(row["delta_g_ev"]), default=None)

    electron_counts, count_source, count_warnings = resolve_transition_electron_counts(
        input_data, steps, transition_rows
    )
    warnings.extend(f"{catalyst}: {warning}" for warning in count_warnings)
    for row, count in zip(transition_rows, electron_counts):
        row["electron_count"] = count
        row["potential_coupled"] = bool(count is not None and count > 0)
        row["delta_g_per_electron_ev"] = (
            float(row["delta_g_ev"]) / count if count is not None and count > 0 else None
        )

    direction = _direction(input_data, metadata)
    reference_potential, reference_key = _optional_float(
        input_data,
        "energy_reference_potential_v",
        "input_potential_v",
        "diagram_potential_v",
    )
    equilibrium_potential, equilibrium_key = _optional_float(
        input_data,
        "equilibrium_potential_v",
        "reversible_potential_v",
    )
    if equilibrium_potential is None and is_number(metadata.get("equilibrium_potential_v")):
        equilibrium_potential = float(metadata["equilibrium_potential_v"])
        equilibrium_key = "reaction_metadata.equilibrium_potential_v"

    reference_assumed = False
    if equilibrium_potential is not None and reference_potential is None:
        reference_potential = 0.0
        reference_key = "assumed_zero_volts"
        reference_assumed = True
        warnings.append(
            f"{catalyst}: equilibrium-potential analysis assumed that the supplied diagram is referenced to 0.0 V."
        )

    coupled_rows = [row for row in transition_rows if row.get("potential_coupled")]
    missing_counts = [
        row["label"]
        for row in relevant_rows
        if row.get("electron_count") is None
    ]
    potential_analysis: dict[str, Any] = {
        "status": "not_available",
        "reaction_direction": direction,
        "electron_count_source": count_source,
        "missing_electron_counts_for": missing_counts,
        "energy_reference_potential_v": reference_potential,
        "energy_reference_potential_source": reference_key,
        "energy_reference_potential_assumed": reference_assumed,
        "equilibrium_potential_v": equilibrium_potential,
        "equilibrium_potential_source": equilibrium_key,
        "reference_electrode": safe_string(input_data.get("reference_electrode")) or None,
        "pH": float(input_data["pH"]) if is_number(input_data.get("pH")) else None,
    }

    if direction == "unknown":
        potential_analysis["status"] = "missing_reaction_direction"
    elif not coupled_rows:
        potential_analysis["status"] = "missing_electron_counts"
    elif missing_counts:
        potential_analysis["status"] = "incomplete_electron_counts"
    elif reference_potential is None:
        potential_analysis["status"] = "missing_energy_reference_potential"
    else:
        boundaries: list[dict[str, Any]] = []
        for row in coupled_rows:
            count = float(row["electron_count"])
            boundary = _limiting_potential_boundary(
                float(row["delta_g_ev"]), count, reference_potential, direction
            )
            boundaries.append(
                {
                    "label": row["label"],
                    "electron_count": count,
                    "delta_g_reference_ev": float(row["delta_g_ev"]),
                    "delta_g_per_electron_ev": float(row["delta_g_ev"]) / count,
                    "zero_delta_g_boundary_potential_v": boundary,
                }
            )
        pds_boundary = max(boundaries, key=lambda row: row["delta_g_per_electron_ev"])
        if direction == "reduction":
            limiting_potential = min(row["zero_delta_g_boundary_potential_v"] for row in boundaries)
        else:
            limiting_potential = max(row["zero_delta_g_boundary_potential_v"] for row in boundaries)
        potential_analysis.update(
            {
                "status": "limiting_potential_available",
                "potential_determining_step": pds_boundary["label"],
                "max_delta_g_per_electron_at_reference_v": pds_boundary["delta_g_per_electron_ev"],
                "limiting_potential_v": limiting_potential,
                "step_potential_boundaries": boundaries,
            }
        )

        if equilibrium_potential is not None:
            equilibrium_rows: list[dict[str, Any]] = []
            all_shifted_rows_known = True
            for row in transition_rows:
                count = row.get("electron_count")
                if count is None:
                    all_shifted_rows_known = False
                    shifted = None
                else:
                    shifted = _potential_shifted_delta_g(
                        float(row["delta_g_ev"]),
                        float(count),
                        equilibrium_potential,
                        reference_potential,
                        direction,
                    )
                row["delta_g_at_equilibrium_ev"] = shifted
                equilibrium_rows.append(
                    {
                        "label": row["label"],
                        "classification": row.get("classification"),
                        "electron_count": count,
                        "delta_g_at_equilibrium_ev": shifted,
                        "delta_g_at_equilibrium_per_electron_v": (
                            shifted / float(count) if shifted is not None and count and float(count) > 0 else None
                        ),
                    }
                )
            coupled_eq = [
                row
                for row in equilibrium_rows
                if row["electron_count"] is not None and float(row["electron_count"]) > 0
            ]
            equilibrium_pds = max(
                coupled_eq,
                key=lambda row: float(row["delta_g_at_equilibrium_per_electron_v"]),
            )
            residual_per_electron = float(equilibrium_pds["delta_g_at_equilibrium_per_electron_v"])
            raw_overpotential = (
                equilibrium_potential - limiting_potential
                if direction == "reduction"
                else limiting_potential - equilibrium_potential
            )
            # These should be equal within numerical precision under the same convention.
            overpotential_consistency_error = raw_overpotential - residual_per_electron
            all_downhill_at_equilibrium = all(
                float(row["delta_g_at_equilibrium_ev"]) <= tolerance for row in coupled_eq
            )
            complete_cycle = bool(input_data.get("complete_reaction_cycle", False))
            closure_delta = (
                sum(float(row["delta_g_at_equilibrium_ev"]) for row in equilibrium_rows)
                if all_shifted_rows_known
                else None
            )
            closure_status = "not_requested"
            if complete_cycle:
                if closure_delta is None:
                    closure_status = "unavailable_missing_electron_counts"
                elif abs(closure_delta) <= closure_tolerance:
                    closure_status = "pass"
                else:
                    closure_status = "fail"
                    warnings.append(
                        f"{catalyst}: complete_reaction_cycle=true, but the summed step free energy at the "
                        f"equilibrium potential is {closure_delta:.3f} eV rather than approximately 0 eV. "
                        "Check reference states, omitted reservoir species, pH/potential conventions, and electron counts."
                    )

            ranking_valid = raw_overpotential >= -tolerance
            if raw_overpotential < -tolerance:
                warnings.append(
                    f"{catalyst}: all represented potential-coupled steps remain downhill at the supplied equilibrium "
                    "potential, giving a negative apparent overpotential. The pathway is likely incomplete or its "
                    "reference/electron-count convention is inconsistent; do not rank by slope."
                )
            if all_downhill_at_equilibrium and complete_cycle and closure_status != "pass":
                warnings.append(
                    f"{catalyst}: a complete cycle cannot be strongly downhill at equilibrium. Review the cycle closure before ranking."
                )

            potential_analysis.update(
                {
                    "status": "equilibrium_potential_available" if ranking_valid else "equilibrium_profile_inconsistent",
                    "equilibrium_steps": equilibrium_rows,
                    "equilibrium_potential_determining_step": equilibrium_pds["label"],
                    "max_residual_uphill_per_electron_v": residual_per_electron,
                    "max_residual_uphill_delta_g_ev": equilibrium_pds["delta_g_at_equilibrium_ev"],
                    "all_potential_coupled_steps_downhill_at_equilibrium": all_downhill_at_equilibrium,
                    "thermodynamic_overpotential_v_raw": raw_overpotential,
                    "thermodynamic_overpotential_v": max(0.0, raw_overpotential) if ranking_valid else None,
                    "overpotential_consistency_error_v": overpotential_consistency_error,
                    "complete_reaction_cycle_declared": complete_cycle,
                    "cycle_closure_delta_g_at_equilibrium_ev": closure_delta,
                    "cycle_closure_tolerance_ev": closure_tolerance,
                    "cycle_closure_status": closure_status,
                    "ranking_valid": ranking_valid,
                }
            )

    if all_downhill_electrochemical:
        if potential_analysis.get("status") == "equilibrium_potential_available":
            mode = "all_downhill_resolved_at_equilibrium_potential"
            confidence = "medium_thermodynamic_only"
            conclusion = (
                "All relevant steps are downhill at the input potential. Thermodynamic superiority is compared at "
                "the common equilibrium potential using the maximum residual uphill free energy per transferred electron."
            )
        elif potential_analysis.get("status") == "limiting_potential_available":
            mode = "all_downhill_limiting_potential_without_equilibrium_reference"
            confidence = "low_to_medium"
            conclusion = (
                "A limiting potential can be computed from explicit electron counts, but an equilibrium potential is "
                "required to convert it into a reaction-specific thermodynamic overpotential."
            )
        else:
            mode = "all_downhill_secondary_diagnostics_only"
            confidence = "low"
            conclusion = (
                "The raw downward slope does not establish catalyst superiority. Supply a common equilibrium potential, "
                "the input diagram potential, and per-step or cumulative electron counts for potential-based comparison."
            )
            warnings.append(
                f"{catalyst}: all relevant steps are downhill, so a positive-ΔG-only PDS rule cannot rank this profile. "
                "Raw slope, overall driving force, or deepest energy alone must not be treated as proof of higher activity."
            )
    else:
        mode = "uphill_step_present_at_input_potential"
        confidence = "standard_thermodynamic_screening"
        conclusion = "At least one relevant step is uphill at the input potential; conventional thermodynamic PDS screening applies."

    analysis = {
        "evaluation_mode": mode,
        "all_downhill_electrochemical_steps": all_downhill_electrochemical,
        "all_downhill_all_steps": all_downhill_all_steps,
        "least_favorable_step_at_input": least_favorable["label"] if least_favorable else None,
        "least_favorable_delta_g_at_input_ev": float(least_favorable["delta_g_ev"]) if least_favorable else None,
        "ranking_confidence": confidence,
        "thermodynamic_conclusion": conclusion,
        "raw_slope_alone_can_rank": False if all_downhill_electrochemical else None,
        "secondary_metrics": _secondary_metrics(steps, series, transition_rows),
        "potential_analysis": potential_analysis,
        "recommended_next_checks": [
            "product desorption or surface-regeneration free energy",
            "kinetic activation barriers for the candidate bottleneck steps",
            "competing reaction descriptors under the same potential, pH, and coverage",
            "coverage, solvent, field, and constant-potential effects",
            "catalyst stability and possible surface reconstruction",
        ],
    }
    return analysis, warnings


def downhill_ranking_record(catalyst: str, analysis: dict[str, Any]) -> dict[str, Any]:
    """Build a lower-is-better ranking record from an all-downhill analysis."""
    potential = analysis["potential_analysis"]
    if potential.get("status") == "equilibrium_potential_available" and potential.get("ranking_valid"):
        return {
            "catalyst": catalyst,
            "metric": "thermodynamic_overpotential_at_equilibrium_v",
            "score": float(potential["thermodynamic_overpotential_v"]),
            "pds": potential.get("equilibrium_potential_determining_step"),
            "eta_calc_v": float(potential["thermodynamic_overpotential_v"]),
            "limiting_potential_v": potential.get("limiting_potential_v"),
            "ranking_status": "equilibrium_potential_thermodynamic_screening",
            "thermodynamic_ranking_resolved": True,
            "performance_ranking_definitive": False,
            "ranking_confidence": analysis["ranking_confidence"],
        }
    if potential.get("status") == "limiting_potential_available":
        return {
            "catalyst": catalyst,
            "metric": "max_delta_g_per_electron_at_reference_v",
            "score": float(potential["max_delta_g_per_electron_at_reference_v"]),
            "pds": potential.get("potential_determining_step"),
            "eta_calc_v": None,
            "limiting_potential_v": potential.get("limiting_potential_v"),
            "ranking_status": "limiting_potential_only_equilibrium_potential_missing",
            "thermodynamic_ranking_resolved": False,
            "performance_ranking_definitive": False,
            "ranking_confidence": analysis["ranking_confidence"],
        }
    raw_score = analysis.get("least_favorable_delta_g_at_input_ev")
    return {
        "catalyst": catalyst,
        "metric": "least_favorable_downhill_step_ev_screening_only",
        "score": float(raw_score) if raw_score is not None else 0.0,
        "pds": None,
        "least_favorable_step": analysis.get("least_favorable_step_at_input"),
        "eta_calc_v": None,
        "limiting_potential_v": None,
        "ranking_status": "secondary_screening_only_no_potential_ranking",
        "thermodynamic_ranking_resolved": False,
        "performance_ranking_definitive": False,
        "ranking_confidence": analysis["ranking_confidence"],
    }
