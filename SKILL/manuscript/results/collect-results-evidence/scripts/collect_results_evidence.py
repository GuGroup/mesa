#!/usr/bin/env python3
"""Collect compact figure-centered evidence for Results and Discussion writing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return read_json(path)


def selected_strategy_payload(data: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    selected = data.get("selected_strategy")
    return selected if isinstance(selected, dict) else data


def strategy_id_from_payload(data: dict[str, Any] | None, fallback: str) -> str:
    if isinstance(data, dict) and isinstance(data.get("selected_strategy_id"), str):
        return data["selected_strategy_id"]
    selected = selected_strategy_payload(data)
    sid = selected.get("strategy_id") if isinstance(selected, dict) else None
    return str(sid or fallback)


def compact_strategy_context(strategy_data: dict[str, Any] | None) -> dict[str, Any]:
    selected = selected_strategy_payload(strategy_data)
    problem = selected.get("problem", {}) if isinstance(selected.get("problem"), dict) else {}
    hypothesis = selected.get("hypothesis", {}) if isinstance(selected.get("hypothesis"), dict) else {}
    return {
        "strategy_id": selected.get("strategy_id"),
        "title": selected.get("title"),
        "question": problem.get("question"),
        "unexplained_phenomenon": problem.get("unexplained_phenomenon"),
        "hypothesis": hypothesis.get("statement"),
        "proposed_mechanism_or_prediction": hypothesis.get("proposed_mechanism_or_prediction"),
    }


def by_key(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(item.get(key)): item for item in items if isinstance(item, dict) and item.get(key) is not None}


def figure_number(level: str, main_index: int, supp_index: int) -> str | None:
    if level == "supplementary":
        return f"Fig. S{supp_index}"
    if level in {"must_have", "useful"}:
        return f"Fig. {main_index}"
    return None


def build_figure_backbone(
    mapping: dict[str, Any] | None,
    captions: dict[str, Any] | None,
    realization: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    figures = mapping.get("figures", []) if isinstance(mapping, dict) else []
    caption_map = by_key(captions.get("captions", []) if isinstance(captions, dict) else [], "figure_id")
    realization_map = by_key(realization.get("figures", []) if isinstance(realization, dict) else [], "id")
    backbone: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    main_count = 0
    supp_count = 0
    for fig in figures:
        if not isinstance(fig, dict):
            continue
        fid = str(fig.get("id") or "")
        level = str(fig.get("level") or "")
        cap = caption_map.get(fid, {})
        real = realization_map.get(fid, {})
        state = cap.get("state") or real.get("state") or fig.get("status")
        if state == "blocked" or fig.get("blockers") or cap.get("blockers"):
            blocked.append(
                {
                    "figure_id": fid,
                    "figure_type": fig.get("figure_type"),
                    "level": level,
                    "reason": fig.get("blockers") or cap.get("blockers") or real.get("notes") or [],
                    "status": state,
                }
            )
            continue
        if level == "supplementary":
            supp_count += 1
            number = figure_number(level, main_count, supp_count)
        else:
            main_count += 1
            number = figure_number(level, main_count, supp_count)
        backbone.append(
            {
                "figure_id": fid,
                "figure_number": number,
                "level": level,
                "figure_type": fig.get("figure_type"),
                "routed_type": fig.get("type"),
                "title": cap.get("figure_title") or fig.get("title"),
                "caption": cap.get("caption"),
                "extended_caption": cap.get("extended_caption"),
                "state": state,
                "exported_files": cap.get("exported_files") or real.get("exported_files") or [],
                "claim_from_mapping": fig.get("claim"),
                "caveats": cap.get("caveats") or fig.get("caveats") or [],
                "source_basis": cap.get("source_basis") or fig.get("source", {}).get("procedures", []),
            }
        )
    return backbone, blocked


def compact_descriptors(descriptor_summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    descriptors = descriptor_summary.get("descriptors", []) if isinstance(descriptor_summary, dict) else []
    keep = [
        "rank",
        "motif",
        "motif_class",
        "bounded_activity_score_ev",
        "thermodynamic_span_ev",
        "largest_uphill_step_ev",
        "delta_g_h2o_ev",
        "delta_g_h_oh_ev",
        "delta_g_h_ev",
        "delta_g_oh_ev",
        "delta_g_h2_ads_ev",
        "h2_desorption_free_energy_ev",
        "profile_relative_energies_ev",
        "profile_step_energies_ev",
    ]
    out = []
    for row in descriptors:
        if not isinstance(row, dict):
            continue
        out.append({k: row.get(k) for k in keep if k in row})
    return out


def compact_state_profiles(relative_free_energies: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    table = relative_free_energies.get("state_table", []) if isinstance(relative_free_energies, dict) else []
    profiles: dict[str, list[dict[str, Any]]] = {}
    keep = ["sequence", "state_id", "state_label", "relative_free_energy_ev", "relative_energy_expression"]
    for row in table:
        if not isinstance(row, dict):
            continue
        motif = str(row.get("motif") or "")
        if not motif:
            continue
        profiles.setdefault(motif, []).append({k: row.get(k) for k in keep if k in row})
    for rows in profiles.values():
        rows.sort(key=lambda item: item.get("sequence", 0))
    return profiles


def compact_model_manifest(model_manifest: dict[str, Any] | None) -> dict[str, Any]:
    records = model_manifest.get("records", []) if isinstance(model_manifest, dict) else []
    motif_labels = {}
    states = set()
    for row in records:
        if not isinstance(row, dict):
            continue
        if row.get("motif") and row.get("motif_label"):
            motif_labels[str(row["motif"])] = row["motif_label"]
        if row.get("state"):
            states.add(str(row["state"]))
    return {
        "motif_count": model_manifest.get("motif_count") if isinstance(model_manifest, dict) else None,
        "state_count_per_motif": model_manifest.get("state_count_per_motif") if isinstance(model_manifest, dict) else None,
        "total_structures": model_manifest.get("total_structures") if isinstance(model_manifest, dict) else None,
        "motif_labels": motif_labels,
        "states": sorted(states),
    }


def compact_relaxation_summary(relaxation_registry: dict[str, Any] | None, result_artifact: dict[str, Any] | None) -> dict[str, Any]:
    fallback = {}
    if isinstance(result_artifact, dict):
        fallback = result_artifact.get("key_evidence", {}).get("relaxations", {})
    if not isinstance(relaxation_registry, dict):
        return fallback or {}
    return {
        "total_records": relaxation_registry.get("total_records", fallback.get("total_records")),
        "converged_count": relaxation_registry.get("converged_count", fallback.get("converged_count")),
        "continued_count": relaxation_registry.get("continued_count", fallback.get("continued_count")),
    }


def compact_vibration_summary(vibration_summary: dict[str, Any] | None, result_artifact: dict[str, Any] | None) -> dict[str, Any]:
    fallback = {}
    if isinstance(result_artifact, dict):
        fallback = result_artifact.get("key_evidence", {}).get("vibrations", {})
    if not isinstance(vibration_summary, dict):
        return fallback or {}
    return {
        "task_count": vibration_summary.get("task_count", fallback.get("task_count")),
        "success_count": vibration_summary.get("success_count"),
        "frequency_result_count": vibration_summary.get("frequency_result_count", fallback.get("frequency_result_count")),
        "imaginary_mode_record_count": vibration_summary.get("imaginary_mode_record_count", fallback.get("imaginary_mode_record_count")),
    }


def key_findings_from_inputs(
    result_artifact: dict[str, Any] | None,
    activity_ranking: dict[str, Any] | None,
    benchmark: dict[str, Any] | None,
    figure_backbone: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    evidence = result_artifact.get("key_evidence", {}) if isinstance(result_artifact, dict) else {}
    ranking = activity_ranking.get("ranking", []) if isinstance(activity_ranking, dict) else []
    if not ranking and isinstance(benchmark, dict):
        ranking = benchmark.get("activity_ranking", [])
    main_figures = [
        fig.get("figure_number")
        for fig in (figure_backbone or [])
        if fig.get("figure_number") and not str(fig.get("figure_number")).startswith("Fig. S")
    ]
    findings: list[dict[str, Any]] = []
    if result_artifact and result_artifact.get("central_claim"):
        findings.append(
            {
                "finding_id": "central_claim",
                "finding": result_artifact.get("central_claim"),
                "evidence_type": "bounded_result_artifact",
                "related_figures": main_figures,
                "support": evidence.get("best_motif"),
                "confidence": "direct_bounded",
            }
        )
    if evidence.get("best_motif"):
        support = evidence.get("best_motif")
        best_name = support.get("motif") or support.get("motif_label") or support.get("name") if isinstance(support, dict) else None
        findings.append(
            {
                "finding_id": "best_motif",
                "finding": f"The best-ranked candidate in the computed thermodynamic ranking is {best_name}." if best_name else "The computed ranking identifies a best-ranked candidate among the tested models.",
                "evidence_type": "activity_ranking",
                "related_figures": main_figures,
                "support": evidence.get("best_motif"),
                "confidence": "direct",
            }
        )
    for key, value in evidence.items():
        if key in {"best_motif", "evidence_readiness", "relaxations", "vibrations"} or not isinstance(value, (dict, list, str, int, float)):
            continue
        if key == "ni_decorated_vs_pristine_s_edge":
            finding_text = "A direct comparator analysis reports a thermodynamic difference between the modified and pristine model families."
        elif key == "best_ni_vs_best_pristine":
            finding_text = "The best modified model improves the computed thermodynamic score relative to the best pristine comparator."
        else:
            label = key.replace("_", " ")
            finding_text = f"The computed evidence reports {label} as a directly computed comparison."
        findings.append(
            {
                "finding_id": key,
                "finding": finding_text,
                "evidence_type": "descriptor_comparison",
                "related_figures": main_figures,
                "support": value,
                "confidence": "direct",
            }
        )
    if isinstance(benchmark, dict) and benchmark.get("conclusion"):
        conclusion = benchmark.get("conclusion")
        if isinstance(conclusion, dict):
            finding_text = conclusion.get("summary") or json.dumps(conclusion, ensure_ascii=False, sort_keys=True)
        else:
            finding_text = str(conclusion)
        findings.append(
            {
                "finding_id": "benchmark_directional_consistency",
                "finding": finding_text,
                "evidence_type": "directional_benchmark_comparison",
                "related_figures": [],
                "support": {
                    "benchmark_constraints": benchmark.get("benchmark_constraints"),
                    "computed_checks": benchmark.get("computed_checks"),
                },
                "confidence": "directional_only",
            }
        )
    if ranking:
        findings.append(
            {
                "finding_id": "motif_ranking",
                "finding": "The computed ranking orders the tested models by the reported thermodynamic descriptor or score.",
                "evidence_type": "activity_ranking",
                "related_figures": main_figures,
                "support": ranking,
                "confidence": "direct",
            }
        )
    return findings


def collect_evidence(args: argparse.Namespace) -> dict[str, Any]:
    project = Path(args.project)
    strategy_path = Path(args.strategy) if args.strategy else project / "strategy_execution" / "strategy_selection" / "selected_strategy.json"
    strategy_data = load_json_if_exists(strategy_path)
    strategy_id = args.strategy_id or strategy_id_from_payload(strategy_data, "S1")
    execution_root = Path(args.execution_root) if args.execution_root else project / "strategy_execution" / f"{strategy_id}_execution"
    figure_root = Path(args.figure_root) if args.figure_root else project / "strategy_execution" / f"{strategy_id}_figure"
    result_artifact_path = (
        Path(args.result_artifact)
        if args.result_artifact
        else project / "strategy_execution" / f"{strategy_id}_result_artifact" / f"{strategy_id}_bounded_result_artifact.json"
    )

    paths = {
        "strategy": strategy_path,
        "result_artifact": result_artifact_path,
        "figure_mapping": figure_root / "mapping" / "figure_info.json",
        "figure_captions": figure_root / "caption" / "caption_info.json",
        "figure_realization": figure_root / "realization" / "figure_realization.json",
        "descriptor_summary": execution_root / "free_energy" / "descriptor_summary.json",
        "activity_ranking": execution_root / "free_energy" / "activity_ranking.json",
        "relative_free_energies": execution_root / "free_energy" / "pH14_U0_relative_free_energies.json",
        "benchmark_comparison": execution_root / "free_energy" / "benchmark_constraint_comparison.json",
        "model_manifest": execution_root / "model_build" / "model_manifest.json",
        "relaxation_registry": execution_root / "uma_relax" / "final_relaxation_registry.json",
        "vibration_summary": execution_root / "uma_vib" / "uma_vib_batch_summary.json",
        "p006_unresolved_summary": execution_root / "p006_unresolved_summary.json",
    }

    loaded = {name: load_json_if_exists(path) for name, path in paths.items()}
    figure_backbone, blocked_figures = build_figure_backbone(
        loaded["figure_mapping"],
        loaded["figure_captions"],
        loaded["figure_realization"],
    )
    result_artifact = loaded["result_artifact"] if isinstance(loaded["result_artifact"], dict) else {}
    limitations = []
    limitations.extend(result_artifact.get("limitations", []) if isinstance(result_artifact.get("limitations"), list) else [])
    activity = loaded["activity_ranking"] if isinstance(loaded["activity_ranking"], dict) else {}
    limitations.extend(activity.get("limitations", []) if isinstance(activity.get("limitations"), list) else [])
    limitations = list(dict.fromkeys(str(item) for item in limitations if item))

    p006 = loaded["p006_unresolved_summary"] if isinstance(loaded["p006_unresolved_summary"], dict) else result_artifact.get("p006_status")
    blocked_or_unavailable = blocked_figures[:]
    if p006:
        blocked_or_unavailable.append(
            {
                "evidence_id": "P006_electronic_descriptors",
                "status": p006.get("status"),
                "reason": p006.get("reason"),
                "required_future_artifacts": p006.get("required_future_artifacts"),
                "not_substituted_with_proxy": p006.get("not_substituted_with_proxy"),
            }
        )

    evidence = {
        "schema_version": SCHEMA_VERSION,
        "collector": "results-evidence-collector",
        "strategy_id": strategy_id,
        "purpose": "Compact deterministic source for drafting Results and Discussion from grounded evidence.",
        "input_paths": {name: str(path) for name, path in paths.items()},
        "missing_inputs": [name for name, value in loaded.items() if value is None],
        "strategy_context": compact_strategy_context(strategy_data),
        "figure_backbone": figure_backbone,
        "key_findings": key_findings_from_inputs(result_artifact, loaded["activity_ranking"], loaded["benchmark_comparison"], figure_backbone),
        "computed_tables": {
            "descriptors": compact_descriptors(loaded["descriptor_summary"]),
            "state_profiles_by_motif": compact_state_profiles(loaded["relative_free_energies"]),
            "activity_ranking": loaded["activity_ranking"].get("ranking", []) if isinstance(loaded["activity_ranking"], dict) else [],
            "benchmark_constraints": loaded["benchmark_comparison"].get("benchmark_constraints", {}) if isinstance(loaded["benchmark_comparison"], dict) else {},
        },
        "quality_summary": {
            "model_manifest": compact_model_manifest(loaded["model_manifest"]),
            "relaxation_summary": compact_relaxation_summary(loaded["relaxation_registry"], result_artifact),
            "vibration_summary": compact_vibration_summary(loaded["vibration_summary"], result_artifact),
            "evidence_readiness": result_artifact.get("key_evidence", {}).get("evidence_readiness", {}),
        },
        "limitations": limitations,
        "blocked_or_unavailable_evidence": blocked_or_unavailable,
        "writer_rules": [
            "Write Results and Discussion around the figure backbone and key findings.",
            "Do not mention internal file paths, JSON names, recipe ids, or procedure ids in manuscript prose.",
            "Do not claim PDOS, Bader charge, charge transfer, kinetic barriers, active-site density, or double-layer effects as completed evidence.",
            "Do not claim quantitative overpotential or Tafel-slope prediction from thermodynamic descriptors.",
            "Use the limitations as scope-control language where needed, not as standalone procedural narration.",
        ],
    }
    return evidence


def writer_digest(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": evidence["schema_version"],
        "collector": evidence["collector"],
        "strategy_id": evidence["strategy_id"],
        "writing_task": "Draft Results and Discussion from evidence only.",
        "writer_rules": evidence["writer_rules"],
        "strategy_context": evidence["strategy_context"],
        "figure_backbone": [
            {
                "figure_id": f.get("figure_id"),
                "figure_number": f.get("figure_number"),
                "level": f.get("level"),
                "figure_type": f.get("figure_type"),
                "title": f.get("title"),
                "caption": f.get("caption"),
                "exported_files": f.get("exported_files"),
                "caveats": f.get("caveats"),
            }
            for f in evidence["figure_backbone"]
        ],
        "key_findings": evidence["key_findings"],
        "computed_tables": {
            "descriptors": evidence["computed_tables"]["descriptors"],
            "state_profiles_by_motif": evidence["computed_tables"]["state_profiles_by_motif"],
            "activity_ranking": evidence["computed_tables"]["activity_ranking"],
            "benchmark_constraints": evidence["computed_tables"]["benchmark_constraints"],
        },
        "quality_summary": evidence["quality_summary"],
        "limitations": evidence["limitations"],
        "blocked_or_unavailable_evidence": evidence["blocked_or_unavailable_evidence"],
    }


def write_summary(path: Path, evidence: dict[str, Any]) -> None:
    lines = [
        "# Results Evidence Summary",
        "",
        f"- Strategy: `{evidence['strategy_id']}`",
        f"- Schema version: {evidence['schema_version']}",
        f"- Figure entries: {len(evidence['figure_backbone'])}",
        f"- Key findings: {len(evidence['key_findings'])}",
        f"- Missing inputs: {', '.join(evidence['missing_inputs']) if evidence['missing_inputs'] else 'None'}",
        "",
        "## Input Paths",
        "",
    ]
    for name, path_value in evidence["input_paths"].items():
        lines.append(f"- `{name}`: `{path_value}`")
    lines.extend(["", "## Figure Backbone", ""])
    for fig in evidence["figure_backbone"]:
        lines.append(
            f"- {fig.get('figure_number') or fig.get('figure_id')}: {fig.get('title')} "
            f"(`{fig.get('figure_id')}`, {fig.get('level')}, {fig.get('state')})"
        )
    lines.extend(["", "## Key Findings", ""])
    for finding in evidence["key_findings"]:
        lines.append(f"- `{finding['finding_id']}`: {finding['finding']}")
    lines.extend(["", "## Limitations", ""])
    if evidence["limitations"]:
        lines.extend(f"- {item}" for item in evidence["limitations"])
    else:
        lines.append("- None")
    lines.extend(["", "## Blocked Or Unavailable Evidence", ""])
    if evidence["blocked_or_unavailable_evidence"]:
        for item in evidence["blocked_or_unavailable_evidence"]:
            lines.append(f"- `{item.get('figure_id') or item.get('evidence_id')}`: {item.get('reason') or item.get('status')}")
    else:
        lines.append("- None")
    write_text(path, "\n".join(lines) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Project directory, for example project/mos_0629_2.")
    parser.add_argument("--strategy-id", default="", help="Strategy id such as S1. Inferred from selected_strategy.json when omitted.")
    parser.add_argument("--strategy", default="", help="Path to selected_strategy.json.")
    parser.add_argument("--result-artifact", default="", help="Path to <strategy_id>_bounded_result_artifact.json.")
    parser.add_argument("--figure-root", default="", help="Path to <strategy_id>_figure.")
    parser.add_argument("--execution-root", default="", help="Path to <strategy_id>_execution.")
    parser.add_argument("--outdir", default="", help="Output directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evidence = collect_evidence(args)
    project = Path(args.project)
    outdir = Path(args.outdir) if args.outdir else project / "strategy_execution" / f"{evidence['strategy_id']}_results" / "evidence"
    outdir.mkdir(parents=True, exist_ok=True)
    evidence_path = outdir / "results_evidence.json"
    digest_path = outdir / "results_writer_digest.json"
    summary_path = outdir / "results_evidence_summary.md"
    digest = writer_digest(evidence)
    write_json(evidence_path, evidence)
    write_json(digest_path, digest)
    write_summary(summary_path, evidence)
    print(
        json.dumps(
            {
                "ok": True,
                "strategy_id": evidence["strategy_id"],
                "outdir": str(outdir),
                "evidence": str(evidence_path),
                "digest": str(digest_path),
                "summary": str(summary_path),
                "figure_count": len(evidence["figure_backbone"]),
                "key_finding_count": len(evidence["key_findings"]),
                "missing_inputs": evidence["missing_inputs"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
