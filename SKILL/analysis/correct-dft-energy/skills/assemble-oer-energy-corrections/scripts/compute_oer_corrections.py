#!/usr/bin/env python3
"""Compute closure-checked OER AEM free-energy corrections and descriptors."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping

KB_EV_PER_K = 8.617333262145e-5
REQUIRED_STATES = ("clean", "OH", "O", "OOH")
STEP_LABELS = (
    "* + H2O -> *OH + (H+ + e-)",
    "*OH -> *O + (H+ + e-)",
    "*O + H2O -> *OOH + (H+ + e-)",
    "*OOH -> * + O2 + (H+ + e-)",
)


class OERInputError(ValueError):
    """Raised when the structured input is inconsistent or incomplete."""


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
                "o2_cycle_free_energy_eV": args.o2_cycle_free_energy_ev,
                "closure_tolerance_eV": args.closure_tolerance_ev,
            },
        )
    except (OERInputError, json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    args.outdir.mkdir(parents=True, exist_ok=True)
    write_outputs(args.outdir, result)
    print(json.dumps({
        "motif_count": len(result["descriptors"]),
        "best_motif": result["activity_ranking"][0]["motif"] if result["activity_ranking"] else None,
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
        description="Compute OER adsorbate-evolution free-energy corrections and descriptors.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--temperature-k", type=float, default=None)
    parser.add_argument("--ph", type=float, default=None)
    parser.add_argument("--potential-v", type=float, default=None)
    parser.add_argument("--reference-electrode", choices=("RHE", "SHE"), default=None)
    parser.add_argument("--h2o-reference-correction-ev", type=float, default=None)
    parser.add_argument("--o2-cycle-free-energy-ev", type=float, default=None)
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
        raise OERInputError("reference_electrode must be RHE or SHE")
    if temperature <= 0:
        raise OERInputError("temperature_K must be positive")

    policy = dict(normalized.get("reference_policy", {}))
    mode = str(policy.get("o2_mode", policy.get("mode", "h2o_h2_cycle")))
    if mode not in ("h2o_h2_cycle", "direct_o2"):
        raise OERInputError("reference_policy.o2_mode must be h2o_h2_cycle or direct_o2")

    h2o_cli = overrides.get("h2o_reference_correction_eV")
    h2o_correction = choose_float(h2o_cli, policy.get("h2o_reference_correction_eV"), 0.0)
    closure_tolerance = choose_float(
        overrides.get("closure_tolerance_eV"),
        policy.get("closure_tolerance_eV"),
        1.0e-6,
    )
    if closure_tolerance < 0:
        raise OERInputError("closure_tolerance_eV must be non-negative")

    refs = normalized["references"]
    reject_external_double_count(refs["H2O"], h2o_correction, "H2O")
    g_h2, h2_components = resolve_record(refs["H2"], "references.H2")
    g_h2o_raw, h2o_components = resolve_record(refs["H2O"], "references.H2O")
    g_h2o = g_h2o_raw + h2o_correction
    h2o_phase = str(refs["H2O"].get("phase", "unspecified")).lower()
    if h2o_phase not in ("liquid", "l", "aqueous", "aq") and abs(h2o_correction) <= 1.0e-15:
        add_warning(
            warnings,
            "REFERENCE_PHASE",
            "blocking",
            "H2O is not labeled liquid/aqueous and no explicit phase-reference correction was supplied.",
        )

    cycle_value: float | None = None
    cycle_temperature: float | None = None
    g_o2: float
    o2_components: dict[str, float]
    if mode == "h2o_h2_cycle":
        cycle_raw = overrides.get("o2_cycle_free_energy_eV")
        if cycle_raw is None:
            cycle_raw = policy.get("o2_cycle_free_energy_eV")
        if cycle_raw is None:
            raise OERInputError(
                "h2o_h2_cycle mode requires reference_policy.o2_cycle_free_energy_eV "
                "or --o2-cycle-free-energy-ev"
            )
        cycle_value = as_float(cycle_raw, "o2_cycle_free_energy_eV")
        cycle_temperature = as_float(policy.get("o2_cycle_temperature_K", 298.15), "o2_cycle_temperature_K")
        g_o2 = 2.0 * g_h2o - 2.0 * g_h2 + cycle_value
        o2_components = {
            "2*H2O_reference": 2.0 * g_h2o,
            "-2*H2_reference": -2.0 * g_h2,
            "experimental_cycle": cycle_value,
        }
        if abs(temperature - cycle_temperature) > 0.5:
            add_warning(
                warnings,
                "CYCLE_TEMPERATURE_MISMATCH",
                "blocking",
                f"Calculation temperature {temperature:g} K differs from the O2 cycle temperature "
                f"{cycle_temperature:g} K.",
            )
        if not has_provenance(policy.get("o2_cycle_provenance")):
            add_warning(
                warnings,
                "MISSING_PROVENANCE",
                "blocking",
                "The O2 thermodynamic-cycle value has no source/provenance record.",
            )
    else:
        if "O2" not in refs:
            raise OERInputError("direct_o2 mode requires references.O2")
        g_o2, o2_components = resolve_record(refs["O2"], "references.O2")
        cycle_value = g_o2 + 2.0 * g_h2 - 2.0 * g_h2o
        cycle_temperature = temperature
        add_warning(
            warnings,
            "DIRECT_O2_REFERENCE",
            "advisory",
            "Direct O2 is being used. Report the method-specific O2 gas-phase error before quantitative claims.",
        )

    direct_o2_diagnostic = None
    if "O2" in refs:
        direct_g_o2, _ = resolve_record(refs["O2"], "references.O2")
        direct_cycle = direct_g_o2 + 2.0 * g_h2 - 2.0 * g_h2o
        direct_o2_diagnostic = {
            "direct_o2_free_energy_eV": direct_g_o2,
            "direct_water_splitting_free_energy_eV": direct_cycle,
            "difference_from_selected_cycle_eV": direct_cycle - cycle_value,
        }

    ph_shift = KB_EV_PER_K * temperature * math.log(10.0) * pH
    pair_shift_requested = -potential if electrode == "RHE" else -potential - ph_shift
    pair_shift_zero = 0.0 if electrode == "RHE" else -ph_shift
    pair_requested = 0.5 * g_h2 + pair_shift_requested
    pair_zero = 0.5 * g_h2 + pair_shift_zero

    equilibrium_rhe = cycle_value / 4.0
    equilibrium_selected = equilibrium_rhe if electrode == "RHE" else equilibrium_rhe - ph_shift
    expected_closure_zero = 4.0 * equilibrium_selected

    descriptors: list[dict[str, Any]] = []
    step_rows: list[dict[str, Any]] = []
    profile_rows: list[dict[str, Any]] = []

    for motif in normalized["motifs"]:
        motif_name = str(motif["motif"])
        states = motif["states"]
        check_required_states(motif_name, states)
        resolved = {state: resolve_record(states[state], f"motifs.{motif_name}.states.{state}")[0] for state in REQUIRED_STATES}
        clean, oh, oxygen, ooh = (resolved[key] for key in REQUIRED_STATES)

        steps_requested = oer_steps(clean, oh, oxygen, ooh, g_h2o, g_o2, pair_requested)
        steps_zero = oer_steps(clean, oh, oxygen, ooh, g_h2o, g_o2, pair_zero)
        closure_residual = sum(steps_zero) - expected_closure_zero
        closure_pass = abs(closure_residual) <= closure_tolerance
        if not closure_pass:
            add_warning(
                warnings,
                "OER_CLOSURE_FAILURE",
                "blocking",
                f"{motif_name}: four AEM steps miss the expected overall free energy by "
                f"{closure_residual:+.6f} eV.",
            )

        limiting_potential = max(steps_zero)
        pds_index = steps_zero.index(max(steps_zero))
        overpotential = limiting_potential - equilibrium_selected
        if overpotential < -closure_tolerance:
            add_warning(
                warnings,
                "NEGATIVE_OVERPOTENTIAL",
                "blocking",
                f"{motif_name}: computed thermodynamic overpotential is {overpotential:+.6f} V.",
            )

        cumulative_requested = cumulative(steps_requested)
        cumulative_zero = cumulative(steps_zero)
        state_labels = ("*", "*OH", "*O", "*OOH", "* + O2")

        delta_g_oh = oh - clean - (g_h2o - 0.5 * g_h2)
        delta_g_o = oxygen - clean - (g_h2o - g_h2)
        delta_g_ooh = ooh - clean - (2.0 * g_h2o - 1.5 * g_h2)
        evidence_state = aggregate_evidence_state(states)
        evidence_caveats = aggregate_caveats(states)
        ranking_exclusion_reasons: list[str] = []
        if not closure_pass:
            ranking_exclusion_reasons.append("cycle closure failed")
        if evidence_state == "failed":
            ranking_exclusion_reasons.append("one or more endpoint records failed evidence gating")
            add_warning(
                warnings,
                "FAILED_ENDPOINT_EVIDENCE",
                "blocking",
                f"{motif_name}: one or more AEM endpoint records are failed/excluded.",
            )
        elif evidence_state == "unknown":
            add_warning(
                warnings,
                "UNKNOWN_ENDPOINT_EVIDENCE",
                "advisory",
                f"{motif_name}: endpoint evidence state is incomplete; ranking is provisional.",
            )
        ranking_eligible = not ranking_exclusion_reasons

        row = {
            "motif": motif_name,
            "motif_class": motif.get("motif_class", "unspecified"),
            "delta_g_oh_star_eV": delta_g_oh,
            "delta_g_o_star_eV": delta_g_o,
            "delta_g_ooh_star_eV": delta_g_ooh,
            "ooh_minus_oh_scaling_eV": delta_g_ooh - delta_g_oh,
            "step_free_energies_zero_potential_eV": steps_zero,
            "step_free_energies_requested_potential_eV": steps_requested,
            "potential_determining_step_index": pds_index + 1,
            "potential_determining_step": STEP_LABELS[pds_index],
            "largest_uphill_step_zero_potential_eV": max(steps_zero),
            "thermodynamic_limiting_potential_V": limiting_potential,
            "equilibrium_potential_selected_scale_V": equilibrium_selected,
            "thermodynamic_overpotential_V": overpotential,
            "closure_residual_eV": closure_residual,
            "closure_pass": closure_pass,
            "ranking_eligible": ranking_eligible,
            "ranking_exclusion_reasons": ranking_exclusion_reasons,
            "evidence_acceptance_state": evidence_state,
            "evidence_caveats": evidence_caveats,
        }
        descriptors.append(row)

        for index, (d0, du) in enumerate(zip(steps_zero, steps_requested), start=1):
            step_rows.append({
                "motif": motif_name,
                "motif_class": row["motif_class"],
                "step_index": index,
                "step_label": STEP_LABELS[index - 1],
                "delta_g_zero_potential_eV": d0,
                "delta_g_requested_potential_eV": du,
                "is_potential_determining_step": index == pds_index + 1,
            })
        for index, label in enumerate(state_labels):
            profile_rows.append({
                "motif": motif_name,
                "motif_class": row["motif_class"],
                "state_index": index,
                "state_label": label,
                "relative_free_energy_zero_potential_eV": cumulative_zero[index],
                "relative_free_energy_requested_potential_eV": cumulative_requested[index],
            })

    ranking = []
    eligible_descriptors = [row for row in descriptors if row["ranking_eligible"]]
    for rank, row in enumerate(
        sorted(eligible_descriptors, key=lambda item: item["thermodynamic_overpotential_V"]),
        start=1,
    ):
        ranking.append({
            "rank": rank,
            "motif": row["motif"],
            "motif_class": row["motif_class"],
            "thermodynamic_overpotential_V": row["thermodynamic_overpotential_V"],
            "thermodynamic_limiting_potential_V": row["thermodynamic_limiting_potential_V"],
            "potential_determining_step_index": row["potential_determining_step_index"],
            "potential_determining_step": row["potential_determining_step"],
            "closure_pass": row["closure_pass"],
            "ranking_eligible": row["ranking_eligible"],
            "evidence_acceptance_state": row["evidence_acceptance_state"],
        })

    blocking_warning_count = sum(item["severity"] == "blocking" for item in warnings)
    result = {
        "schema_version": 1,
        "stage": "bounded OER adsorbate-evolution free-energy correction bookkeeping",
        "conditions": {
            "temperature_K": temperature,
            "pH": pH,
            "potential_V": potential,
            "reference_electrode": electrode,
            "pcet_shift_requested_eV_per_pair": pair_shift_requested,
            "pcet_shift_zero_potential_eV_per_pair": pair_shift_zero,
        },
        "reference_policy": {
            "o2_mode": mode,
            "o2_cycle_free_energy_eV": cycle_value,
            "o2_cycle_temperature_K": cycle_temperature,
            "h2o_reference_correction_eV": h2o_correction,
            "equilibrium_potential_RHE_V": equilibrium_rhe,
            "equilibrium_potential_selected_scale_V": equilibrium_selected,
            "closure_tolerance_eV": closure_tolerance,
            "boundary": (
                "Four-step adsorbate-evolution mechanism and CHE thermodynamics only; "
                "no barriers, current density, Tafel slope, explicit double layer, or lattice-oxygen mechanism."
            ),
        },
        "reference_ledger": {
            "H2": {"free_energy_eV": g_h2, "components_eV": h2_components},
            "H2O": {
                "raw_free_energy_eV": g_h2o_raw,
                "reference_correction_eV": h2o_correction,
                "free_energy_eV": g_h2o,
                "components_eV": h2o_components,
            },
            "O2_selected": {"free_energy_eV": g_o2, "components_eV": o2_components},
            "O2_direct_diagnostic": direct_o2_diagnostic,
        },
        "descriptors": descriptors,
        "step_table": step_rows,
        "profile_table": profile_rows,
        "activity_ranking": ranking,
        "warnings": warnings,
        "summary": {
            "motif_count": len(descriptors),
            "closure_failure_count": sum(not row["closure_pass"] for row in descriptors),
            "ranking_eligible_count": len(eligible_descriptors),
            "warning_count": len(warnings),
            "blocking_warning_count": blocking_warning_count,
        },
    }
    return result


def normalize_input(payload: Mapping[str, Any]) -> dict[str, Any]:
    if "free_energy_records" in payload:
        records = payload["free_energy_records"]
        if not isinstance(records, list):
            raise OERInputError("free_energy_records must be a list")
        refs: dict[str, dict[str, Any]] = {}
        motifs: dict[str, dict[str, Any]] = {}
        for record in records:
            if not isinstance(record, Mapping):
                raise OERInputError("Every free_energy_records entry must be an object")
            kind = str(record.get("kind", ""))
            if kind in ("gas", "liquid", "reference"):
                species = str(record.get("species") or record.get("id") or "")
                if species in ("H2", "H2O", "O2"):
                    refs[species] = dict(record)
            elif kind == "surface":
                motif = str(record.get("motif") or "")
                state = str(record.get("state") or "")
                if motif and state:
                    entry = motifs.setdefault(motif, {
                        "motif": motif,
                        "motif_class": record.get("motif_class", "unspecified"),
                        "states": {},
                    })
                    entry["states"][state] = dict(record)
        require_references(refs)
        return {
            "conditions": dict(payload.get("conditions", {})),
            "reference_policy": dict(payload.get("reference_policy", payload.get("o2_reference", {}))),
            "references": refs,
            "motifs": list(motifs.values()),
        }

    if "motifs" not in payload or "references" not in payload:
        raise OERInputError("Input must contain either free_energy_records or motifs+references")
    refs = dict(payload["references"])
    require_references(refs)
    motifs_raw = payload["motifs"]
    if not isinstance(motifs_raw, list) or not motifs_raw:
        raise OERInputError("motifs must be a non-empty list")
    motifs = []
    for item in motifs_raw:
        if not isinstance(item, Mapping) or "motif" not in item or "states" not in item:
            raise OERInputError("Each motif must contain motif and states")
        motifs.append({
            "motif": str(item["motif"]),
            "motif_class": item.get("motif_class", "unspecified"),
            "states": dict(item["states"]),
        })
    return {
        "conditions": dict(payload.get("conditions", {})),
        "reference_policy": dict(payload.get("reference_policy", payload.get("o2_reference", {}))),
        "references": refs,
        "motifs": motifs,
    }


def require_references(refs: Mapping[str, Any]) -> None:
    for species in ("H2", "H2O"):
        if species not in refs:
            raise OERInputError(f"Missing required reference species: {species}")


def reject_external_double_count(record: Mapping[str, Any], external: float, species: str) -> None:
    if abs(external) <= 1.0e-15:
        return
    corrections = record.get("corrections_ev", {}) or {}
    suspicious = {
        str(key).lower()
        for key in corrections
        if any(token in str(key).lower() for token in ("phase_reference", "liquid", "gas_to_liquid"))
    }
    if suspicious:
        raise OERInputError(
            f"{species} has an external reference correction and record-level correction keys "
            f"{sorted(suspicious)}; remove one source to avoid double counting"
        )


def check_required_states(motif: str, states: Mapping[str, Any]) -> None:
    missing = [state for state in REQUIRED_STATES if state not in states]
    if missing:
        raise OERInputError(f"{motif} missing required states: {', '.join(missing)}")


def resolve_record(record: Mapping[str, Any], label: str) -> tuple[float, dict[str, float]]:
    has_total = "free_energy_ev" in record
    has_electronic = "electronic_energy_ev" in record
    corrections = record.get("corrections_ev", {})
    if corrections is None:
        corrections = {}
    if not isinstance(corrections, Mapping):
        raise OERInputError(f"{label}.corrections_ev must be an object")
    if has_total and (has_electronic or corrections):
        raise OERInputError(
            f"{label} supplies free_energy_ev together with electronic_energy_ev/corrections_ev; "
            "this risks double counting"
        )
    if has_total:
        total = as_float(record["free_energy_ev"], f"{label}.free_energy_ev")
        return total, {"provided_free_energy": total}
    if not has_electronic:
        raise OERInputError(f"{label} requires free_energy_ev or electronic_energy_ev")
    components = {"electronic": as_float(record["electronic_energy_ev"], f"{label}.electronic_energy_ev")}
    for key, value in corrections.items():
        components[str(key)] = as_float(value, f"{label}.corrections_ev.{key}")
    return sum(components.values()), components


def oer_steps(clean: float, oh: float, oxygen: float, ooh: float, h2o: float, o2: float, pair: float) -> list[float]:
    return [
        oh + pair - clean - h2o,
        oxygen + pair - oh,
        ooh + pair - oxygen - h2o,
        clean + o2 + pair - ooh,
    ]


def cumulative(steps: list[float]) -> list[float]:
    values = [0.0]
    for step in steps:
        values.append(values[-1] + step)
    return values


def aggregate_evidence_state(states: Mapping[str, Mapping[str, Any]]) -> str:
    values = [str(record.get("evidence_acceptance_state", "unknown")) for record in states.values()]
    if any(value in ("failed", "excluded") for value in values):
        return "failed"
    if any(value == "accepted-with-caveat" for value in values):
        return "accepted-with-caveat"
    if values and all(value == "accepted" for value in values):
        return "accepted"
    return "unknown"


def aggregate_caveats(states: Mapping[str, Mapping[str, Any]]) -> list[str]:
    caveats: list[str] = []
    for record in states.values():
        for caveat in record.get("evidence_caveats", []) or []:
            text = str(caveat)
            if text not in caveats:
                caveats.append(text)
    return caveats


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
        raise OERInputError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise OERInputError(f"{label} must be finite")
    return number


def write_outputs(outdir: Path, result: Mapping[str, Any]) -> None:
    write_json(outdir / "oer_bookkeeping.json", result)
    write_json(outdir / "oer_descriptor_summary.json", {"descriptors": result["descriptors"]})
    write_json(outdir / "oer_activity_ranking.json", {"activity_ranking": result["activity_ranking"]})
    write_csv(outdir / "oer_descriptor_summary.csv", result["descriptors"], [
        "motif", "motif_class", "delta_g_oh_star_eV", "delta_g_o_star_eV",
        "delta_g_ooh_star_eV", "ooh_minus_oh_scaling_eV",
        "potential_determining_step_index", "potential_determining_step",
        "largest_uphill_step_zero_potential_eV", "thermodynamic_limiting_potential_V",
        "equilibrium_potential_selected_scale_V", "thermodynamic_overpotential_V",
        "closure_residual_eV", "closure_pass", "ranking_eligible",
        "ranking_exclusion_reasons", "evidence_acceptance_state",
    ])
    write_csv(outdir / "oer_step_summary.csv", result["step_table"], [
        "motif", "motif_class", "step_index", "step_label",
        "delta_g_zero_potential_eV", "delta_g_requested_potential_eV",
        "is_potential_determining_step",
    ])
    write_csv(outdir / "oer_profile_table.csv", result["profile_table"], [
        "motif", "motif_class", "state_index", "state_label",
        "relative_free_energy_zero_potential_eV",
        "relative_free_energy_requested_potential_eV",
    ])
    write_csv(outdir / "oer_activity_ranking.csv", result["activity_ranking"], [
        "rank", "motif", "motif_class", "thermodynamic_overpotential_V",
        "thermodynamic_limiting_potential_V", "potential_determining_step_index",
        "potential_determining_step", "closure_pass", "ranking_eligible",
        "evidence_acceptance_state",
    ])
    write_csv(outdir / "oer_warnings.csv", result["warnings"], ["code", "severity", "message"])


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
