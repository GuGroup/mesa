#!/usr/bin/env python3
"""Compute HNO3-cycle and CHE-corrected NO3RR-to-NH3 free-energy pathways."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping

KB_EV_PER_K = 8.617333262145e-5
DEFAULT_PATH = ("NO3", "NO3H", "NO2", "NO2H", "NO", "NHO", "NH2O", "NH2OH", "NH2", "NH3")
COMMON_COMPOSITIONS: dict[str, dict[str, int]] = {
    "NO3": {"N": 1, "O": 3, "H": 0},
    "NO3H": {"N": 1, "O": 3, "H": 1},
    "HNO3": {"N": 1, "O": 3, "H": 1},
    "NO2": {"N": 1, "O": 2, "H": 0},
    "NO2H": {"N": 1, "O": 2, "H": 1},
    "HNO2": {"N": 1, "O": 2, "H": 1},
    "NO": {"N": 1, "O": 1, "H": 0},
    "NHO": {"N": 1, "O": 1, "H": 1},
    "HNO": {"N": 1, "O": 1, "H": 1},
    "NOH": {"N": 1, "O": 1, "H": 1},
    "NH2O": {"N": 1, "O": 1, "H": 2},
    "NH2OH": {"N": 1, "O": 1, "H": 3},
    "NH2": {"N": 1, "O": 0, "H": 2},
    "NH3": {"N": 1, "O": 0, "H": 3},
}
REQUIRED_REFERENCES = ("H2", "H2O", "HNO3", "NH3")
ALLOWED_EVIDENCE_LABELS = {
    "MATCHED",
    "PARTIALLY MATCHED",
    "CLOSURE ONLY",
    "SCREENING ASSUMPTION",
    "UNVERIFIED",
}


class NO3RRInputError(ValueError):
    """Raised when the NO3RR correction input is incomplete or inconsistent."""


def main() -> int:
    args = parse_args()
    try:
        payload = json.loads(args.input.expanduser().read_text(encoding="utf-8"))
        result = compute_bookkeeping(
            payload,
            overrides={
                "temperature_K": args.temperature_k,
                "pH": args.ph,
                "potential_v": args.potential_v,
                "reference_electrode": args.reference_electrode,
                "h2o_reference_correction_eV": args.h2o_reference_correction_ev,
                "hno3_molecular_correction_eV": args.hno3_molecular_correction_ev,
                "nh3_molecular_correction_eV": args.nh3_molecular_correction_ev,
                "closure_tolerance_eV": args.closure_tolerance_ev,
            },
        )
    except (NO3RRInputError, json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    args.outdir.mkdir(parents=True, exist_ok=True)
    write_outputs(args.outdir, result)
    print(json.dumps({
        "motif_pathway_count": len(result["pathway_descriptors"]),
        "best_entry": result["pathway_ranking"][0]["entry_id"] if result["pathway_ranking"] else None,
        "warning_count": len(result["warnings"]),
        "outputs": str(args.outdir),
    }, indent=2))

    if args.strict and (
        result["summary"]["closure_failure_count"] > 0
        or result["summary"]["blocking_warning_count"] > 0
    ):
        return 3
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute HNO3-cycle and CHE-corrected NO3RR-to-NH3 free-energy pathways.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--temperature-k", type=float, default=None)
    parser.add_argument("--ph", type=float, default=None)
    parser.add_argument("--potential-v", type=float, default=None)
    parser.add_argument("--reference-electrode", choices=("RHE", "SHE"), default=None)
    parser.add_argument("--h2o-reference-correction-ev", type=float, default=None)
    parser.add_argument("--hno3-molecular-correction-ev", type=float, default=None)
    parser.add_argument("--nh3-molecular-correction-ev", type=float, default=None)
    parser.add_argument("--closure-tolerance-ev", type=float, default=None)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def compute_bookkeeping(payload: Mapping[str, Any], overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    overrides = dict(overrides or {})
    normalized = normalize_input(payload)
    warnings: list[dict[str, str]] = []

    conditions = dict(normalized.get("conditions", {}))
    temperature = choose_float(overrides.get("temperature_K"), conditions.get("temperature_K"), 298.15)
    pH = choose_float(overrides.get("pH"), conditions.get("pH"), 0.0)
    potential = choose_float(overrides.get("potential_v"), conditions.get("potential_v"), 0.0)
    electrode = str(overrides.get("reference_electrode") or conditions.get("reference_electrode") or "RHE").upper()
    if electrode not in ("RHE", "SHE"):
        raise NO3RRInputError("reference_electrode must be RHE or SHE")
    if temperature <= 0:
        raise NO3RRInputError("temperature_K must be positive")

    policy = dict(normalized.get("reference_policy", {}))
    mode = str(policy.get("mode", "hno3_thermodynamic_cycle"))
    if mode != "hno3_thermodynamic_cycle":
        raise NO3RRInputError(
            "This bounded skill currently requires reference_policy.mode = hno3_thermodynamic_cycle. "
            "Use an explicit general reaction-network audit for direct aqueous-ion or whole-reaction-only schemes."
        )
    if "global_nox_correction_eV" in policy:
        raise NO3RRInputError("global_nox_correction_eV is forbidden; corrections must be species-specific")

    closure_tolerance = choose_float(
        overrides.get("closure_tolerance_eV"),
        policy.get("closure_tolerance_eV"),
        1.0e-6,
    )
    if closure_tolerance < 0:
        raise NO3RRInputError("closure_tolerance_eV must be non-negative")

    refs = normalized["references"]
    resolved_refs = {species: resolve_record(refs[species], f"references.{species}") for species in REQUIRED_REFERENCES}

    h2o_correction = choose_float(
        overrides.get("h2o_reference_correction_eV"),
        policy.get("h2o_reference_correction_eV"),
        0.0,
    )
    hno3_correction = choose_float(
        overrides.get("hno3_molecular_correction_eV"),
        policy.get("hno3_molecular_correction_eV"),
        0.0,
    )
    nh3_correction = choose_float(
        overrides.get("nh3_molecular_correction_eV"),
        policy.get("nh3_molecular_correction_eV"),
        0.0,
    )

    reject_external_double_count(refs["HNO3"], hno3_correction, "HNO3")
    reject_external_double_count(refs["NH3"], nh3_correction, "NH3")
    reject_external_double_count(refs["H2O"], h2o_correction, "H2O")

    g_h2 = resolved_refs["H2"]["total_eV"]
    g_h2o_raw = resolved_refs["H2O"]["total_eV"]
    g_h2o = g_h2o_raw + h2o_correction
    g_hno3_raw = resolved_refs["HNO3"]["total_eV"]
    g_hno3 = g_hno3_raw + hno3_correction
    g_nh3_raw = resolved_refs["NH3"]["total_eV"]
    g_nh3 = g_nh3_raw + nh3_correction

    h2o_phase = str(refs["H2O"].get("phase", "unspecified")).lower()
    if h2o_phase not in ("liquid", "l", "aqueous", "aq") and abs(h2o_correction) <= 1.0e-15:
        add_warning(
            warnings,
            "REFERENCE_PHASE",
            "blocking",
            "H2O is not labeled liquid/aqueous and no phase-reference correction was supplied.",
        )
    hno3_phase = str(refs["HNO3"].get("phase", "unspecified")).lower()
    if hno3_phase not in ("gas", "g"):
        add_warning(
            warnings,
            "HNO3_PHASE",
            "blocking",
            "The selected HNO3 cycle is defined from HNO3(g), but the HNO3 record is not labeled gas.",
        )
    nh3_phase = str(refs["NH3"].get("phase", "unspecified")).lower()
    if nh3_phase == "unspecified":
        add_warning(
            warnings,
            "NH3_PHASE_UNSPECIFIED",
            "blocking",
            "NH3 product phase is unspecified; declare gas, aqueous, or another explicit reference state.",
        )

    transfer_standard, transfer_components = resolve_transfer_cycle(policy)
    cycle_temperature = as_float(policy.get("cycle_temperature_K", 298.15), "cycle_temperature_K")
    if abs(temperature - cycle_temperature) > 0.5:
        add_warning(
            warnings,
            "CYCLE_TEMPERATURE_MISMATCH",
            "blocking",
            f"Calculation temperature {temperature:g} K differs from HNO3/NO3- cycle temperature "
            f"{cycle_temperature:g} K.",
        )

    hno3_provenance = policy.get("hno3_molecular_correction_provenance")
    if abs(hno3_correction) > 1.0e-15 and not has_provenance(hno3_provenance):
        add_warning(
            warnings,
            "MISSING_HNO3_CORRECTION_PROVENANCE",
            "blocking",
            "A nonzero HNO3 molecular correction was supplied without method/source provenance.",
        )
    if not has_provenance(policy.get("acid_cycle_provenance")):
        add_warning(
            warnings,
            "MISSING_ACID_CYCLE_PROVENANCE",
            "blocking",
            "The HNO3(g) -> NO3-(aq) + H+(aq) transfer cycle has no provenance record.",
        )
    validate_evidence_label(policy.get("hno3_correction_evidence_label"), "hno3_correction_evidence_label", warnings)
    validate_evidence_label(policy.get("acid_cycle_evidence_label"), "acid_cycle_evidence_label", warnings)

    ph_shift = KB_EV_PER_K * temperature * math.log(10.0) * pH
    activity_correction = resolve_activity_correction(policy, temperature)
    transfer_at_conditions = transfer_standard - ph_shift + activity_correction
    pair_delta_requested = -potential if electrode == "RHE" else -potential - ph_shift
    pair_delta_zero = 0.0 if electrode == "RHE" else -ph_shift

    pathway_descriptors: list[dict[str, Any]] = []
    step_rows: list[dict[str, Any]] = []
    profile_rows: list[dict[str, Any]] = []
    adsorption_rows: list[dict[str, Any]] = []

    for motif in normalized["motifs"]:
        motif_name = str(motif["motif"])
        motif_class = motif.get("motif_class", "unspecified")
        states = motif["states"]
        if "clean" not in states:
            raise NO3RRInputError(f"{motif_name} missing required clean state")
        clean_record = resolve_record(states["clean"], f"motifs.{motif_name}.states.clean")
        clean = clean_record["total_eV"]

        for pathway in normalized["pathways"]:
            pathway_id = str(pathway["id"])
            state_order = [str(item) for item in pathway["state_order"]]
            if not state_order:
                raise NO3RRInputError(f"Pathway {pathway_id} has no states")
            missing = [state for state in state_order if state not in states]
            if missing:
                raise NO3RRInputError(
                    f"{motif_name}/{pathway_id} missing pathway states: {', '.join(missing)}"
                )

            cumulative_zero: list[dict[str, Any]] = [{
                "state": "initial_NO3-(aq)+*",
                "label": "NO3-(aq) + *",
                "neutral_eV": None,
                "electrochemical_eV": 0.0,
                "n_pair": 0,
                "net_electrons_consumed": 0,
                "water_produced": 0,
            }]
            cumulative_requested: list[dict[str, Any]] = [{**cumulative_zero[0]}]
            state_meta: list[dict[str, Any]] = []

            for state_name in state_order:
                record = resolve_record(states[state_name], f"motifs.{motif_name}.states.{state_name}")
                composition = resolve_composition(state_name, states[state_name])
                bookkeeping = nitrate_state_bookkeeping(composition, state_name)
                neutral = (
                    record["total_eV"]
                    + bookkeeping["water_produced"] * g_h2o
                    - clean
                    - g_hno3
                    - bookkeeping["h2_reactant_coefficient"] * g_h2
                )
                ec_zero = neutral - transfer_at_conditions - bookkeeping["net_electrons_consumed"] * pair_delta_zero
                ec_requested = neutral - transfer_at_conditions - bookkeeping["net_electrons_consumed"] * pair_delta_requested
                common = {
                    "state": state_name,
                    "label": f"*{state_name}",
                    "neutral_eV": neutral,
                    "n_pair": bookkeeping["n_pair"],
                    "net_electrons_consumed": bookkeeping["net_electrons_consumed"],
                    "water_produced": bookkeeping["water_produced"],
                    "h2_reactant_coefficient": bookkeeping["h2_reactant_coefficient"],
                    "composition": composition,
                    "evidence_acceptance_state": states[state_name].get("evidence_acceptance_state", "unknown"),
                    "evidence_caveats": states[state_name].get("evidence_caveats", []) or [],
                }
                cumulative_zero.append({**common, "electrochemical_eV": ec_zero})
                cumulative_requested.append({**common, "electrochemical_eV": ec_requested})
                state_meta.append({**common, "resolved_record": record})

            terminal_neutral = g_nh3 + 3.0 * g_h2o - g_hno3 - 4.0 * g_h2
            terminal_n_pair = 9
            terminal_net_e = 8
            terminal_zero = terminal_neutral - transfer_at_conditions - terminal_net_e * pair_delta_zero
            terminal_requested = terminal_neutral - transfer_at_conditions - terminal_net_e * pair_delta_requested
            terminal_common = {
                "state": "terminal_NH3",
                "label": "NH3(product) + * + 3H2O",
                "neutral_eV": terminal_neutral,
                "n_pair": terminal_n_pair,
                "net_electrons_consumed": terminal_net_e,
                "water_produced": 3,
                "h2_reactant_coefficient": 4.0,
                "composition": {"N": 1, "O": 0, "H": 3},
                "evidence_acceptance_state": refs["NH3"].get("evidence_acceptance_state", "unknown"),
                "evidence_caveats": refs["NH3"].get("evidence_caveats", []) or [],
            }
            cumulative_zero.append({**terminal_common, "electrochemical_eV": terminal_zero})
            cumulative_requested.append({**terminal_common, "electrochemical_eV": terminal_requested})

            steps = build_steps(cumulative_zero, cumulative_requested)
            closure_residual = sum(step["delta_g_zero_potential_eV"] for step in steps) - terminal_zero
            closure_pass = abs(closure_residual) <= closure_tolerance
            entry_id = f"{motif_name}::{pathway_id}"
            if not closure_pass:
                add_warning(
                    warnings,
                    "NO3RR_CLOSURE_FAILURE",
                    "blocking",
                    f"{entry_id}: pathway step sum misses the overall endpoint by {closure_residual:+.6f} eV.",
                )

            electron_consuming = [step for step in steps if step["delta_net_electrons_consumed"] > 0]
            if not electron_consuming:
                limiting_potential = None
                limiting_step = None
                overpotential = None
                add_warning(
                    warnings,
                    "NO_REDUCTION_STEPS",
                    "blocking",
                    f"{entry_id}: no electron-consuming steps were found.",
                )
            else:
                for step in electron_consuming:
                    step["downhill_threshold_potential_V"] = (
                        -step["delta_g_zero_potential_eV"] / step["delta_net_electrons_consumed"]
                    )
                limiting_step = min(electron_consuming, key=lambda item: item["downhill_threshold_potential_V"])
                limiting_potential = limiting_step["downhill_threshold_potential_V"]
                equilibrium_potential = -terminal_zero / terminal_net_e
                overpotential = equilibrium_potential - limiting_potential
                if overpotential < -closure_tolerance:
                    add_warning(
                        warnings,
                        "NEGATIVE_THERMODYNAMIC_OVERPOTENTIAL",
                        "blocking",
                        f"{entry_id}: thermodynamic overpotential is {overpotential:+.6f} V.",
                    )

            equilibrium_potential = -terminal_zero / terminal_net_e
            independent_uphill = max(0.0, max(
                (step["delta_g_zero_potential_eV"] for step in steps if step["delta_net_electrons_consumed"] == 0),
                default=0.0,
            ))
            reverse_electron_steps = [step for step in steps if step["delta_net_electrons_consumed"] < 0]
            reverse_uphill_at_limiting = 0.0
            if limiting_potential is not None:
                reverse_uphill_at_limiting = max(0.0, max(
                    (
                        step["delta_g_zero_potential_eV"]
                        + step["delta_net_electrons_consumed"] * limiting_potential
                        for step in reverse_electron_steps
                    ),
                    default=0.0,
                ))
                if reverse_uphill_at_limiting > closure_tolerance:
                    add_warning(
                        warnings,
                        "ADSORPTION_UPHILL_AT_LIMITING_POTENTIAL",
                        "advisory",
                        f"{entry_id}: an electron-releasing adsorption step remains uphill by "
                        f"{reverse_uphill_at_limiting:.4f} eV at the PCET limiting potential.",
                    )

            evidence_records = [states["clean"]] + [states[state] for state in state_order] + [refs["NH3"]]
            evidence_state = aggregate_evidence_state(evidence_records)
            evidence_caveats = aggregate_caveats(evidence_records)
            ranking_exclusion_reasons: list[str] = []
            if not closure_pass:
                ranking_exclusion_reasons.append("pathway closure failed")
            if evidence_state == "failed":
                ranking_exclusion_reasons.append("one or more endpoint records failed evidence gating")
                add_warning(
                    warnings,
                    "FAILED_ENDPOINT_EVIDENCE",
                    "blocking",
                    f"{entry_id}: one or more pathway endpoint records are failed/excluded.",
                )
            elif evidence_state == "unknown":
                add_warning(
                    warnings,
                    "UNKNOWN_ENDPOINT_EVIDENCE",
                    "advisory",
                    f"{entry_id}: endpoint evidence state is incomplete; ranking is provisional.",
                )
            ranking_eligible = not ranking_exclusion_reasons

            descriptor = {
                "entry_id": entry_id,
                "motif": motif_name,
                "motif_class": motif_class,
                "pathway_id": pathway_id,
                "state_order": state_order,
                "overall_free_energy_zero_potential_eV": terminal_zero,
                "overall_free_energy_requested_potential_eV": terminal_requested,
                "net_electrons_consumed_overall": terminal_net_e,
                "equilibrium_potential_selected_scale_V": equilibrium_potential,
                "pcet_limiting_potential_V": limiting_potential,
                "pcet_limiting_step_index": limiting_step["step_index"] if limiting_step else None,
                "pcet_limiting_step": limiting_step["step_label"] if limiting_step else None,
                "thermodynamic_overpotential_V": overpotential,
                "largest_potential_independent_uphill_step_eV": independent_uphill,
                "largest_reverse_electron_step_uphill_at_limiting_potential_eV": reverse_uphill_at_limiting,
                "closure_residual_eV": closure_residual,
                "closure_pass": closure_pass,
                "ranking_eligible": ranking_eligible,
                "ranking_exclusion_reasons": ranking_exclusion_reasons,
                "evidence_acceptance_state": evidence_state,
                "evidence_caveats": evidence_caveats,
            }
            pathway_descriptors.append(descriptor)

            for step in steps:
                step_rows.append({
                    "entry_id": entry_id,
                    "motif": motif_name,
                    "motif_class": motif_class,
                    "pathway_id": pathway_id,
                    **step,
                })
            for index, (zero_state, requested_state) in enumerate(zip(cumulative_zero, cumulative_requested)):
                profile_rows.append({
                    "entry_id": entry_id,
                    "motif": motif_name,
                    "motif_class": motif_class,
                    "pathway_id": pathway_id,
                    "state_index": index,
                    "state": zero_state["state"],
                    "state_label": zero_state["label"],
                    "n_pair": zero_state["n_pair"],
                    "net_electrons_consumed": zero_state["net_electrons_consumed"],
                    "water_produced": zero_state["water_produced"],
                    "neutral_reference_free_energy_eV": zero_state["neutral_eV"],
                    "relative_free_energy_zero_potential_eV": zero_state["electrochemical_eV"],
                    "relative_free_energy_requested_potential_eV": requested_state["electrochemical_eV"],
                })

            first_state_meta = state_meta[0]
            if first_state_meta["state"] == "NO3":
                raw_electronic = nitrate_raw_electronic_adsorption(
                    clean_record,
                    first_state_meta["resolved_record"],
                    resolved_refs["H2"],
                    resolved_refs["HNO3"],
                )
                adsorption_rows.append({
                    "entry_id": entry_id,
                    "motif": motif_name,
                    "pathway_id": pathway_id,
                    "raw_electronic_adsorption_eV": raw_electronic,
                    "corrected_gas_scale_adsorption_eV": first_state_meta["neutral_eV"],
                    "electrochemical_adsorption_zero_potential_eV": cumulative_zero[1]["electrochemical_eV"],
                    "electrochemical_adsorption_requested_potential_eV": cumulative_requested[1]["electrochemical_eV"],
                    "gas_to_electrochemical_shift_zero_potential_eV": (
                        cumulative_zero[1]["electrochemical_eV"] - first_state_meta["neutral_eV"]
                    ),
                    "raw_electronic_to_electrochemical_shift_zero_potential_eV": (
                        None if raw_electronic is None
                        else cumulative_zero[1]["electrochemical_eV"] - raw_electronic
                    ),
                })

    pathway_ranking = []
    eligible_pathways = [row for row in pathway_descriptors if row["ranking_eligible"]]
    sortable = sorted(
        eligible_pathways,
        key=lambda item: (
            item["thermodynamic_overpotential_V"] is None,
            item["thermodynamic_overpotential_V"] if item["thermodynamic_overpotential_V"] is not None else float("inf"),
            -(item["pcet_limiting_potential_V"] if item["pcet_limiting_potential_V"] is not None else -float("inf")),
        ),
    )
    for rank, row in enumerate(sortable, start=1):
        pathway_ranking.append({
            "rank": rank,
            "entry_id": row["entry_id"],
            "motif": row["motif"],
            "motif_class": row["motif_class"],
            "pathway_id": row["pathway_id"],
            "pcet_limiting_potential_V": row["pcet_limiting_potential_V"],
            "equilibrium_potential_selected_scale_V": row["equilibrium_potential_selected_scale_V"],
            "thermodynamic_overpotential_V": row["thermodynamic_overpotential_V"],
            "pcet_limiting_step": row["pcet_limiting_step"],
            "largest_potential_independent_uphill_step_eV": row["largest_potential_independent_uphill_step_eV"],
            "closure_pass": row["closure_pass"],
            "ranking_eligible": row["ranking_eligible"],
            "evidence_acceptance_state": row["evidence_acceptance_state"],
        })

    blocking_warning_count = sum(item["severity"] == "blocking" for item in warnings)
    return {
        "schema_version": 1,
        "stage": "bounded NO3RR-to-NH3 HNO3-cycle and CHE free-energy bookkeeping",
        "conditions": {
            "temperature_K": temperature,
            "pH": pH,
            "potential_V": potential,
            "reference_electrode": electrode,
            "kBT_ln10_pH_eV": ph_shift,
            "pair_delta_requested_from_half_H2_eV": pair_delta_requested,
            "pair_delta_zero_potential_from_half_H2_eV": pair_delta_zero,
        },
        "reference_policy": {
            "mode": mode,
            "hno3_molecular_correction_eV": hno3_correction,
            "nh3_molecular_correction_eV": nh3_correction,
            "h2o_reference_correction_eV": h2o_correction,
            "hno3_gas_to_nitrate_plus_proton_standard_eV": transfer_standard,
            "hno3_transfer_components_eV": transfer_components,
            "acid_cycle_activity_correction_eV": activity_correction,
            "hno3_transfer_at_conditions_eV": transfer_at_conditions,
            "cycle_temperature_K": cycle_temperature,
            "closure_tolerance_eV": closure_tolerance,
            "boundary": (
                "Single-N NO3RR-to-NH3 endpoint thermodynamics using an HNO3 reference cycle; "
                "no vacuum-ion substitution, barriers, current density, selectivity kinetics, or universal NOx correction."
            ),
        },
        "reference_ledger": {
            "H2": resolved_refs["H2"],
            "H2O": {
                **resolved_refs["H2O"],
                "external_reference_correction_eV": h2o_correction,
                "corrected_total_eV": g_h2o,
            },
            "HNO3": {
                **resolved_refs["HNO3"],
                "external_molecular_correction_eV": hno3_correction,
                "corrected_total_eV": g_hno3,
            },
            "NH3": {
                **resolved_refs["NH3"],
                "external_molecular_correction_eV": nh3_correction,
                "corrected_total_eV": g_nh3,
            },
        },
        "nitrate_adsorption_diagnostics": adsorption_rows,
        "pathway_descriptors": pathway_descriptors,
        "step_table": step_rows,
        "profile_table": profile_rows,
        "pathway_ranking": pathway_ranking,
        "warnings": warnings,
        "summary": {
            "motif_count": len(normalized["motifs"]),
            "pathway_count": len(normalized["pathways"]),
            "motif_pathway_count": len(pathway_descriptors),
            "closure_failure_count": sum(not row["closure_pass"] for row in pathway_descriptors),
            "ranking_eligible_count": len(eligible_pathways),
            "warning_count": len(warnings),
            "blocking_warning_count": blocking_warning_count,
        },
    }


def normalize_input(payload: Mapping[str, Any]) -> dict[str, Any]:
    pathways = normalize_pathways(payload)
    if "free_energy_records" in payload:
        records = payload["free_energy_records"]
        if not isinstance(records, list):
            raise NO3RRInputError("free_energy_records must be a list")
        refs: dict[str, dict[str, Any]] = {}
        motifs: dict[str, dict[str, Any]] = {}
        state_compositions = payload.get("state_compositions", {})
        if state_compositions is None:
            state_compositions = {}
        if not isinstance(state_compositions, Mapping):
            raise NO3RRInputError("state_compositions must be an object")
        for record in records:
            if not isinstance(record, Mapping):
                raise NO3RRInputError("Every free_energy_records entry must be an object")
            kind = str(record.get("kind", ""))
            if kind in ("gas", "liquid", "aqueous", "reference"):
                species = str(record.get("species") or record.get("id") or "")
                if species in REQUIRED_REFERENCES:
                    refs[species] = dict(record)
            elif kind == "surface":
                motif = str(record.get("motif") or "")
                state = str(record.get("state") or "")
                if motif and state:
                    cooked = dict(record)
                    if "composition" not in cooked and state in state_compositions:
                        cooked["composition"] = state_compositions[state]
                    entry = motifs.setdefault(motif, {
                        "motif": motif,
                        "motif_class": record.get("motif_class", "unspecified"),
                        "states": {},
                    })
                    entry["states"][state] = cooked
        require_references(refs)
        return {
            "conditions": dict(payload.get("conditions", {})),
            "reference_policy": dict(payload.get("reference_policy", {})),
            "references": refs,
            "motifs": list(motifs.values()),
            "pathways": pathways,
        }

    if "motifs" not in payload or "references" not in payload:
        raise NO3RRInputError("Input must contain either free_energy_records or motifs+references")
    refs = dict(payload["references"])
    require_references(refs)
    motifs_raw = payload["motifs"]
    if not isinstance(motifs_raw, list) or not motifs_raw:
        raise NO3RRInputError("motifs must be a non-empty list")
    motifs = []
    for item in motifs_raw:
        if not isinstance(item, Mapping) or "motif" not in item or "states" not in item:
            raise NO3RRInputError("Each motif must contain motif and states")
        motifs.append({
            "motif": str(item["motif"]),
            "motif_class": item.get("motif_class", "unspecified"),
            "states": dict(item["states"]),
        })
    return {
        "conditions": dict(payload.get("conditions", {})),
        "reference_policy": dict(payload.get("reference_policy", {})),
        "references": refs,
        "motifs": motifs,
        "pathways": pathways,
    }


def normalize_pathways(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("pathways")
    if raw is None and "pathway" in payload:
        raw = [payload["pathway"]]
    if raw is None and payload.get("pathway_template") == "default_no3_to_nh3":
        raw = [{"id": "default_no3_to_nh3", "state_order": list(DEFAULT_PATH)}]
    if raw is None:
        raise NO3RRInputError("Provide pathways, pathway, or pathway_template=default_no3_to_nh3")
    if not isinstance(raw, list) or not raw:
        raise NO3RRInputError("pathways must be a non-empty list")
    out = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if isinstance(item, str):
            if item != "default_no3_to_nh3":
                raise NO3RRInputError(f"Unknown pathway template: {item}")
            cooked = {"id": item, "state_order": list(DEFAULT_PATH)}
        elif isinstance(item, Mapping):
            cooked = dict(item)
            if cooked.get("template") == "default_no3_to_nh3" and "state_order" not in cooked:
                cooked["state_order"] = list(DEFAULT_PATH)
            cooked.setdefault("id", f"pathway_{index + 1}")
        else:
            raise NO3RRInputError("Each pathway must be an object or known template string")
        pathway_id = str(cooked["id"])
        if pathway_id in seen:
            raise NO3RRInputError(f"Duplicate pathway id: {pathway_id}")
        seen.add(pathway_id)
        state_order = cooked.get("state_order")
        if not isinstance(state_order, list) or not state_order:
            raise NO3RRInputError(f"Pathway {pathway_id} requires non-empty state_order")
        out.append({"id": pathway_id, "state_order": [str(value) for value in state_order]})
    return out


def require_references(refs: Mapping[str, Any]) -> None:
    for species in REQUIRED_REFERENCES:
        if species not in refs:
            raise NO3RRInputError(f"Missing required reference species: {species}")


def resolve_record(record: Mapping[str, Any], label: str) -> dict[str, Any]:
    has_total = "free_energy_ev" in record
    has_electronic = "electronic_energy_ev" in record
    corrections = record.get("corrections_ev", {})
    if corrections is None:
        corrections = {}
    if not isinstance(corrections, Mapping):
        raise NO3RRInputError(f"{label}.corrections_ev must be an object")
    if has_total and (has_electronic or corrections):
        raise NO3RRInputError(
            f"{label} supplies free_energy_ev together with electronic_energy_ev/corrections_ev; "
            "this risks double counting"
        )
    if has_total:
        total = as_float(record["free_energy_ev"], f"{label}.free_energy_ev")
        return {
            "total_eV": total,
            "electronic_energy_eV": None,
            "components_eV": {"provided_free_energy": total},
        }
    if not has_electronic:
        raise NO3RRInputError(f"{label} requires free_energy_ev or electronic_energy_ev")
    electronic = as_float(record["electronic_energy_ev"], f"{label}.electronic_energy_ev")
    components = {"electronic": electronic}
    for key, value in corrections.items():
        components[str(key)] = as_float(value, f"{label}.corrections_ev.{key}")
    return {
        "total_eV": sum(components.values()),
        "electronic_energy_eV": electronic,
        "components_eV": components,
    }


def reject_external_double_count(record: Mapping[str, Any], external: float, species: str) -> None:
    if abs(external) <= 1.0e-15:
        return
    corrections = record.get("corrections_ev", {}) or {}
    suspicious = {
        str(key).lower()
        for key in corrections
        if any(token in str(key).lower() for token in ("molecular", "gas_phase", "phase_reference", "liquid"))
    }
    if suspicious:
        raise NO3RRInputError(
            f"{species} has an external correction and record-level correction keys {sorted(suspicious)}; "
            "remove one source to avoid double counting"
        )


def resolve_transfer_cycle(policy: Mapping[str, Any]) -> tuple[float, dict[str, float]]:
    direct = policy.get("hno3_gas_to_nitrate_plus_proton_standard_eV")
    gas_to_liquid = policy.get("hno3_gas_to_liquid_eV")
    liquid_to_aq = policy.get("hno3_liquid_to_nitrate_plus_proton_eV")
    if direct is not None and (gas_to_liquid is not None or liquid_to_aq is not None):
        raise NO3RRInputError(
            "Provide either hno3_gas_to_nitrate_plus_proton_standard_eV or the two component cycle values, not both"
        )
    if direct is not None:
        value = as_float(direct, "hno3_gas_to_nitrate_plus_proton_standard_eV")
        return value, {"direct_standard_transfer": value}
    if gas_to_liquid is None or liquid_to_aq is None:
        raise NO3RRInputError(
            "The HNO3 cycle requires either a direct standard transfer free energy or both "
            "hno3_gas_to_liquid_eV and hno3_liquid_to_nitrate_plus_proton_eV"
        )
    part1 = as_float(gas_to_liquid, "hno3_gas_to_liquid_eV")
    part2 = as_float(liquid_to_aq, "hno3_liquid_to_nitrate_plus_proton_eV")
    return part1 + part2, {
        "HNO3_gas_to_liquid": part1,
        "HNO3_liquid_to_NO3_minus_plus_H_plus": part2,
    }


def resolve_activity_correction(policy: Mapping[str, Any], temperature: float) -> float:
    explicit = policy.get("acid_cycle_activity_correction_eV")
    nitrate_activity = policy.get("nitrate_activity", 1.0)
    hno3_activity = policy.get("hno3_reference_activity", 1.0)
    nitrate_activity = as_float(nitrate_activity, "nitrate_activity")
    hno3_activity = as_float(hno3_activity, "hno3_reference_activity")
    if nitrate_activity <= 0 or hno3_activity <= 0:
        raise NO3RRInputError("Activities must be positive")
    calculated = KB_EV_PER_K * temperature * math.log(nitrate_activity / hno3_activity)
    if explicit is not None and (abs(nitrate_activity - 1.0) > 1.0e-15 or abs(hno3_activity - 1.0) > 1.0e-15):
        raise NO3RRInputError(
            "Do not provide acid_cycle_activity_correction_eV together with non-unit activities"
        )
    if explicit is not None:
        return as_float(explicit, "acid_cycle_activity_correction_eV")
    return calculated


def resolve_composition(state_name: str, record: Mapping[str, Any]) -> dict[str, int]:
    raw = record.get("composition")
    canonical = state_name.lstrip("*")
    if raw is None:
        raw = COMMON_COMPOSITIONS.get(canonical)
    if not isinstance(raw, Mapping):
        raise NO3RRInputError(
            f"State {state_name} requires composition, e.g. {{\"N\": 1, \"O\": 2, \"H\": 1}}"
        )
    composition: dict[str, int] = {}
    for element in ("N", "O", "H"):
        value = raw.get(element, 0)
        try:
            integer = int(value)
        except (TypeError, ValueError) as exc:
            raise NO3RRInputError(f"State {state_name} composition {element} must be an integer") from exc
        if float(value) != integer or integer < 0:
            raise NO3RRInputError(f"State {state_name} composition {element} must be a non-negative integer")
        composition[element] = integer
    return composition


def nitrate_state_bookkeeping(composition: Mapping[str, int], state_name: str) -> dict[str, Any]:
    n_n = composition["N"]
    n_o = composition["O"]
    n_h = composition["H"]
    if n_n != 1:
        raise NO3RRInputError(
            f"State {state_name} has N={n_n}; this bounded skill supports single-N NO3RR-to-NH3 paths only"
        )
    if n_o > 3:
        raise NO3RRInputError(f"State {state_name} has more than three oxygen atoms")
    water = 3 - n_o
    n_pair = n_h + 2 * water
    net_e = n_pair - 1
    h2_coefficient = net_e / 2.0
    return {
        "water_produced": water,
        "n_pair": n_pair,
        "net_electrons_consumed": net_e,
        "h2_reactant_coefficient": h2_coefficient,
    }


def build_steps(zero_states: list[Mapping[str, Any]], requested_states: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for index in range(1, len(zero_states)):
        before = zero_states[index - 1]
        after = zero_states[index]
        before_u = requested_states[index - 1]
        after_u = requested_states[index]
        delta_e = int(after["net_electrons_consumed"] - before["net_electrons_consumed"])
        delta_pair = int(after["n_pair"] - before["n_pair"])
        delta_water = int(after["water_produced"] - before["water_produced"])
        if delta_e > 0:
            step_type = "electron-consuming reduction"
        elif delta_e < 0:
            step_type = "electron-releasing adsorption"
        else:
            step_type = "potential-independent chemical/desorption"
        steps.append({
            "step_index": index,
            "from_state": before["state"],
            "to_state": after["state"],
            "step_label": f"{before['label']} -> {after['label']}",
            "step_type": step_type,
            "delta_pcet_pairs": delta_pair,
            "delta_net_electrons_consumed": delta_e,
            "delta_water_produced": delta_water,
            "delta_g_zero_potential_eV": after["electrochemical_eV"] - before["electrochemical_eV"],
            "delta_g_requested_potential_eV": after_u["electrochemical_eV"] - before_u["electrochemical_eV"],
            "downhill_threshold_potential_V": None,
        })
    return steps


def nitrate_raw_electronic_adsorption(
    clean: Mapping[str, Any],
    no3: Mapping[str, Any],
    h2: Mapping[str, Any],
    hno3: Mapping[str, Any],
) -> float | None:
    values = (
        no3.get("electronic_energy_eV"),
        h2.get("electronic_energy_eV"),
        clean.get("electronic_energy_eV"),
        hno3.get("electronic_energy_eV"),
    )
    if any(value is None for value in values):
        return None
    return float(values[0]) + 0.5 * float(values[1]) - float(values[2]) - float(values[3])


def aggregate_evidence_state(records: list[Mapping[str, Any]]) -> str:
    values = [str(record.get("evidence_acceptance_state", "unknown")) for record in records]
    if any(value in ("failed", "excluded") for value in values):
        return "failed"
    if any(value == "accepted-with-caveat" for value in values):
        return "accepted-with-caveat"
    if values and all(value == "accepted" for value in values):
        return "accepted"
    return "unknown"


def aggregate_caveats(records: list[Mapping[str, Any]]) -> list[str]:
    caveats: list[str] = []
    for record in records:
        for caveat in record.get("evidence_caveats", []) or []:
            text = str(caveat)
            if text not in caveats:
                caveats.append(text)
    return caveats


def validate_evidence_label(value: Any, label: str, warnings: list[dict[str, str]]) -> None:
    if value is None:
        add_warning(warnings, "MISSING_EVIDENCE_LABEL", "advisory", f"{label} is not specified.")
        return
    text = str(value).upper()
    if text not in ALLOWED_EVIDENCE_LABELS:
        raise NO3RRInputError(f"{label} must be one of {sorted(ALLOWED_EVIDENCE_LABELS)}")
    if text == "UNVERIFIED":
        add_warning(warnings, "UNVERIFIED_REFERENCE", "blocking", f"{label} is UNVERIFIED.")


def has_provenance(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return any(str(item).strip() for item in value.values())
    return False


def add_warning(warnings: list[dict[str, str]], code: str, severity: str, message: str) -> None:
    warnings.append({"code": code, "severity": severity, "message": message})


def choose_float(override: Any, configured: Any, default: float) -> float:
    if override is not None:
        return as_float(override, "override")
    if configured is not None:
        return as_float(configured, "configured value")
    return float(default)


def as_float(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise NO3RRInputError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise NO3RRInputError(f"{label} must be finite")
    return number


def write_outputs(outdir: Path, result: Mapping[str, Any]) -> None:
    write_json(outdir / "no3rr_bookkeeping.json", result)
    write_json(outdir / "no3rr_pathway_summary.json", {"pathway_descriptors": result["pathway_descriptors"]})
    write_json(outdir / "no3rr_pathway_ranking.json", {"pathway_ranking": result["pathway_ranking"]})
    write_csv(outdir / "no3rr_pathway_summary.csv", result["pathway_descriptors"], [
        "entry_id", "motif", "motif_class", "pathway_id", "state_order",
        "overall_free_energy_zero_potential_eV", "overall_free_energy_requested_potential_eV",
        "net_electrons_consumed_overall", "equilibrium_potential_selected_scale_V",
        "pcet_limiting_potential_V", "pcet_limiting_step_index", "pcet_limiting_step",
        "thermodynamic_overpotential_V", "largest_potential_independent_uphill_step_eV",
        "largest_reverse_electron_step_uphill_at_limiting_potential_eV",
        "closure_residual_eV", "closure_pass", "ranking_eligible",
        "ranking_exclusion_reasons", "evidence_acceptance_state",
    ])
    write_csv(outdir / "no3rr_step_summary.csv", result["step_table"], [
        "entry_id", "motif", "motif_class", "pathway_id", "step_index",
        "from_state", "to_state", "step_label", "step_type", "delta_pcet_pairs",
        "delta_net_electrons_consumed", "delta_water_produced",
        "delta_g_zero_potential_eV", "delta_g_requested_potential_eV",
        "downhill_threshold_potential_V",
    ])
    write_csv(outdir / "no3rr_profile_table.csv", result["profile_table"], [
        "entry_id", "motif", "motif_class", "pathway_id", "state_index",
        "state", "state_label", "n_pair", "net_electrons_consumed", "water_produced",
        "neutral_reference_free_energy_eV", "relative_free_energy_zero_potential_eV",
        "relative_free_energy_requested_potential_eV",
    ])
    write_csv(outdir / "no3rr_pathway_ranking.csv", result["pathway_ranking"], [
        "rank", "entry_id", "motif", "motif_class", "pathway_id",
        "pcet_limiting_potential_V", "equilibrium_potential_selected_scale_V",
        "thermodynamic_overpotential_V", "pcet_limiting_step",
        "largest_potential_independent_uphill_step_eV", "closure_pass",
        "ranking_eligible", "evidence_acceptance_state",
    ])
    write_csv(outdir / "nitrate_adsorption_diagnostics.csv", result["nitrate_adsorption_diagnostics"], [
        "entry_id", "motif", "pathway_id", "raw_electronic_adsorption_eV",
        "corrected_gas_scale_adsorption_eV", "electrochemical_adsorption_zero_potential_eV",
        "electrochemical_adsorption_requested_potential_eV",
        "gas_to_electrochemical_shift_zero_potential_eV",
        "raw_electronic_to_electrochemical_shift_zero_potential_eV",
    ])
    write_csv(outdir / "no3rr_warnings.csv", result["warnings"], ["code", "severity", "message"])


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[Mapping[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            cooked = {}
            for field in fields:
                value = row.get(field)
                if isinstance(value, (list, dict)):
                    value = json.dumps(value, ensure_ascii=False, sort_keys=True)
                cooked[field] = value
            writer.writerow(cooked)


if __name__ == "__main__":
    raise SystemExit(main())
