#!/usr/bin/env python3
"""Compute bounded alkaline HER descriptors from endpoint free energies."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


REQUIRED_STATES = ("clean", "H2O", "OH", "H", "H_OH", "H2")


def main() -> int:
    args = parse_args()
    payload = json.loads(args.input.expanduser().read_text(encoding="utf-8"))
    data = normalize_input(payload)
    refs = data["references"]
    motifs = data["motifs"]

    g_h2 = refs["H2"]["free_energy_ev"]
    g_h2o = refs["H2O"]["free_energy_ev"] + args.h2o_reference_correction_ev

    descriptors = []
    for motif in motifs:
        states = motif["states"]
        check_required_states(motif["motif"], states)
        clean = g(states["clean"])
        delta_g_h2o = g(states["H2O"]) - clean - g_h2o
        delta_g_h_oh = g(states["H_OH"]) - clean - g_h2o
        delta_g_h = g(states["H"]) - clean - 0.5 * g_h2
        delta_g_oh = g(states["OH"]) - clean - (g_h2o - 0.5 * g_h2)
        delta_g_h2_ads = g(states["H2"]) - clean - g_h2
        h2_desorption = -delta_g_h2_ads
        profile = [0.0, delta_g_h2o, delta_g_h_oh, delta_g_h2_ads, 0.0]
        steps = [profile[index + 1] - profile[index] for index in range(len(profile) - 1)]
        score = (
            abs(delta_g_h)
            + max(delta_g_h2o, 0.0)
            + max(h2_desorption, 0.0)
            + max(delta_g_oh - args.oh_penalty_offset_ev, 0.0)
        )
        descriptors.append({
            "motif": motif["motif"],
            "motif_class": motif.get("motif_class") or infer_motif_class(motif["motif"]),
            "delta_g_h_ev": delta_g_h,
            "delta_g_oh_ev": delta_g_oh,
            "delta_g_h2o_ev": delta_g_h2o,
            "delta_g_h_oh_ev": delta_g_h_oh,
            "delta_g_h2_ads_ev": delta_g_h2_ads,
            "h2_desorption_free_energy_ev": h2_desorption,
            "thermodynamic_span_ev": max(profile) - min(profile),
            "largest_uphill_step_ev": max(steps),
            "largest_uphill_step_index": steps.index(max(steps)),
            "bounded_activity_score_ev": score,
            "profile_relative_energies_ev": profile,
            "profile_step_energies_ev": steps,
            "evidence_acceptance_state": aggregate_evidence_state(states),
            "evidence_caveats": aggregate_caveats(states),
        })

    ranking = build_ranking(descriptors)
    state_table = build_state_table(descriptors)
    out = {
        "schema_version": 1,
        "stage": "bounded alkaline HER free-energy bookkeeping",
        "input": str(args.input),
        "reference_policy": {
            "ph": args.ph,
            "potential_rhe_v": args.potential_rhe,
            "h2_reference": "0.5 * G(H2)",
            "h2o_reference": "G(H2O) plus command-line H2O correction if provided",
            "h2o_reference_correction_ev": args.h2o_reference_correction_ev,
            "oh_penalty_offset_ev": args.oh_penalty_offset_ev,
            "boundary": "bounded thermodynamic descriptor bookkeeping; no explicit charged OH-, barrier, current, overpotential, or Tafel prediction",
        },
        "descriptors": descriptors,
        "activity_ranking": ranking,
        "state_table": state_table,
    }

    args.outdir.mkdir(parents=True, exist_ok=True)
    write_json(args.outdir / "alkaline_her_bookkeeping.json", out)
    write_json(args.outdir / "descriptor_summary.json", {"descriptors": descriptors})
    write_json(args.outdir / "activity_ranking.json", {"activity_ranking": ranking})
    write_csv(args.outdir / "descriptor_summary.csv", descriptors, [
        "motif",
        "motif_class",
        "delta_g_h_ev",
        "delta_g_oh_ev",
        "delta_g_h2o_ev",
        "delta_g_h_oh_ev",
        "delta_g_h2_ads_ev",
        "h2_desorption_free_energy_ev",
        "thermodynamic_span_ev",
        "largest_uphill_step_ev",
        "bounded_activity_score_ev",
        "evidence_acceptance_state",
    ])
    write_csv(args.outdir / "activity_ranking.csv", ranking, [
        "rank",
        "motif",
        "motif_class",
        "bounded_activity_score_ev",
        "delta_g_h_ev",
        "delta_g_oh_ev",
        "delta_g_h2o_ev",
        "delta_g_h_oh_ev",
        "thermodynamic_span_ev",
        "largest_uphill_step_ev",
    ])
    write_csv(args.outdir / "bounded_profile_table.csv", state_table, [
        "motif",
        "motif_class",
        "state_index",
        "state_label",
        "relative_free_energy_ev",
    ])
    print(json.dumps({
        "motif_count": len(descriptors),
        "best_motif": ranking[0]["motif"] if ranking else None,
        "outputs": str(args.outdir),
    }, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute bounded alkaline HER descriptors from endpoint free energies.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--ph", type=float, default=14.0)
    parser.add_argument("--potential-rhe", type=float, default=0.0)
    parser.add_argument("--h2o-reference-correction-ev", type=float, default=0.0)
    parser.add_argument("--oh-penalty-offset-ev", type=float, default=0.5)
    return parser.parse_args()


def normalize_input(payload: dict[str, Any]) -> dict[str, Any]:
    if "free_energy_records" in payload:
        return normalize_records(payload["free_energy_records"])
    if "motifs" in payload and "references" in payload:
        motifs = []
        for motif in payload["motifs"]:
            motifs.append({
                "motif": motif["motif"],
                "motif_class": motif.get("motif_class"),
                "states": motif["states"],
            })
        refs = payload["references"]
        require_refs(refs)
        return {"motifs": motifs, "references": refs}
    raise SystemExit("Input must contain either free_energy_records or motifs+references.")


def normalize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    refs: dict[str, dict[str, Any]] = {}
    motifs: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("kind") == "gas":
            species = record.get("species") or record.get("id")
            if species in ("H2", "H2O"):
                refs[str(species)] = record
        elif record.get("kind") == "surface":
            motif = record.get("motif")
            state = record.get("state")
            if motif and state:
                entry = motifs.setdefault(str(motif), {
                    "motif": str(motif),
                    "motif_class": record.get("motif_class"),
                    "states": {},
                })
                entry["states"][str(state)] = record
    require_refs(refs)
    return {"motifs": list(motifs.values()), "references": refs}


def require_refs(refs: dict[str, Any]) -> None:
    for species in ("H2", "H2O"):
        if species not in refs:
            raise SystemExit(f"Missing required reference species: {species}")
        g(refs[species])


def check_required_states(motif: str, states: dict[str, Any]) -> None:
    missing = [state for state in REQUIRED_STATES if state not in states]
    if missing:
        raise SystemExit(f"{motif} missing required states: {', '.join(missing)}")
    for state in REQUIRED_STATES:
        g(states[state])


def g(record: dict[str, Any]) -> float:
    try:
        return float(record["free_energy_ev"])
    except Exception as exc:
        raise SystemExit(f"Record lacks numeric free_energy_ev: {record}") from exc


def infer_motif_class(motif: str) -> str:
    return "Ni-doped" if motif.lower().startswith("ni_") else "pristine"


def aggregate_evidence_state(states: dict[str, dict[str, Any]]) -> str:
    values = [str(record.get("evidence_acceptance_state", "unknown")) for record in states.values()]
    if any(value in ("failed", "excluded") for value in values):
        return "failed"
    if any(value == "accepted-with-caveat" for value in values):
        return "accepted-with-caveat"
    if all(value == "accepted" for value in values):
        return "accepted"
    return "unknown"


def aggregate_caveats(states: dict[str, dict[str, Any]]) -> list[str]:
    caveats: list[str] = []
    for record in states.values():
        for caveat in record.get("evidence_caveats", []) or []:
            text = str(caveat)
            if text not in caveats:
                caveats.append(text)
    return caveats


def build_ranking(descriptors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for rank, row in enumerate(sorted(descriptors, key=lambda item: item["bounded_activity_score_ev"]), start=1):
        out.append({
            "rank": rank,
            "motif": row["motif"],
            "motif_class": row["motif_class"],
            "bounded_activity_score_ev": row["bounded_activity_score_ev"],
            "delta_g_h_ev": row["delta_g_h_ev"],
            "delta_g_oh_ev": row["delta_g_oh_ev"],
            "delta_g_h2o_ev": row["delta_g_h2o_ev"],
            "delta_g_h_oh_ev": row["delta_g_h_oh_ev"],
            "thermodynamic_span_ev": row["thermodynamic_span_ev"],
            "largest_uphill_step_ev": row["largest_uphill_step_ev"],
        })
    return out


def build_state_table(descriptors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labels = ["Initial", "H2O*", "H*+OH*", "H2*", "Final"]
    rows = []
    for row in descriptors:
        for index, value in enumerate(row["profile_relative_energies_ev"]):
            rows.append({
                "motif": row["motif"],
                "motif_class": row["motif_class"],
                "state_index": index,
                "state_label": labels[index],
                "relative_free_energy_ev": value,
            })
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


if __name__ == "__main__":
    raise SystemExit(main())
