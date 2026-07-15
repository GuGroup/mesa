#!/usr/bin/env python3
"""Collect minimal four-section evidence for computational Methods writing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 3

SECTION_TITLES = {
    "model_construction": "Model construction",
    "geometry_optimization": "Geometry optimization",
    "vibrational_free_energy_corrections": "Vibrational and free-energy corrections",
    "electrochemical_free_energy_formalism": "Electrochemical free-energy formalism",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def selected_strategy_payload(data: dict[str, Any]) -> dict[str, Any]:
    selected = data.get("selected_strategy")
    return selected if isinstance(selected, dict) else data


def computational_from_strategy(data: dict[str, Any]) -> dict[str, Any]:
    selected = selected_strategy_payload(data)
    experiment = selected.get("experiment", {}) if isinstance(selected, dict) else {}
    computational = experiment.get("computational", {}) if isinstance(experiment, dict) else {}
    return computational if isinstance(computational, dict) else {}


def strategy_id_from_payload(data: dict[str, Any], fallback: str = "") -> str:
    if isinstance(data.get("selected_strategy_id"), str):
        return data["selected_strategy_id"]
    selected = selected_strategy_payload(data)
    sid = selected.get("strategy_id") if isinstance(selected, dict) else None
    return str(sid or fallback)


def first_glob(root: Path, *patterns: str) -> Path | None:
    for pattern in patterns:
        matches = sorted(root.glob(pattern)) if root.exists() else []
        if matches:
            return matches[0]
    return None


def load_json_if_exists(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    return read_json(path)


def unique(values: list[Any]) -> list[Any]:
    seen = set()
    out = []
    for value in values:
        marker = json.dumps(value, sort_keys=True, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(value)
    return out


def compact_model_manifest(model_manifest: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(model_manifest, dict):
        return {"motif_labels": [], "states": [], "motif_state_pairs": []}
    rows = [row for row in model_manifest.get("records", []) if isinstance(row, dict)]
    pairs = unique(
        [
            {
                "motif_label": row.get("motif_label"),
                "state": row.get("state"),
            }
            for row in rows
            if row.get("motif_label") is not None or row.get("state") is not None
        ]
    )
    return {
        "motif_labels": sorted({str(row.get("motif_label")) for row in rows if row.get("motif_label") is not None}),
        "states": sorted({str(row.get("state")) for row in rows if row.get("state") is not None}),
        "motif_state_pairs": pairs,
    }


def compact_gas_metadata(gas_metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(gas_metadata, dict):
        return {}
    return {
        "formula": gas_metadata.get("formula"),
        "cell_lengths": gas_metadata.get("cell_lengths"),
        "pbc": gas_metadata.get("pbc"),
    }


def compact_reference_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(policy, dict):
        return {}
    return {
        "pH": policy.get("pH"),
        "potential_V_RHE": policy.get("potential_V_RHE"),
        "temperature_K": policy.get("temperature_K"),
        "pressure_Pa": policy.get("pressure_Pa"),
        "hydrogen_reference": policy.get("hydrogen_reference"),
        "water_reference": policy.get("water_reference"),
        "oh_minus_and_electron_policy": policy.get("oh_minus_and_electron_policy"),
        "surface_thermal_policy": policy.get("surface_thermal_policy"),
    }


def compact_vibration_summary(vib_summary: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(vib_summary, dict):
        return {}
    return {
        "skill": vib_summary.get("skill"),
        "task_count": vib_summary.get("task_count"),
        "success_count": vib_summary.get("success_count"),
        "frequency_result_count": vib_summary.get("frequency_result_count"),
        "imaginary_mode_record_count": vib_summary.get("imaginary_mode_record_count"),
        "runtime_environment": vib_summary.get("runtime_environment"),
    }


def compact_relaxation_summary(relax_summary: dict[str, Any] | None, relaxation_registry: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(relax_summary, dict):
        out.update(
            {
                "task_count": relax_summary.get("task_count"),
                "success_count": relax_summary.get("success_count"),
            }
        )
    if isinstance(relaxation_registry, dict):
        out.update(
            {
                "total_records": relaxation_registry.get("total_records"),
                "converged_count": relaxation_registry.get("converged_count"),
                "continued_count": relaxation_registry.get("continued_count"),
            }
        )
    return out


def energy_tool_summary(vib_summary: dict[str, Any] | None, free_energy_bookkeeping: dict[str, Any] | None) -> dict[str, Any]:
    tools = []
    if isinstance(vib_summary, dict) and vib_summary.get("skill"):
        tools.append(
            {
                "tool": vib_summary.get("skill"),
                "role": "vibrational frequency and thermochemical correction inputs",
            }
        )
    if isinstance(free_energy_bookkeeping, dict):
        tools.append(
            {
                "tool": "alkaline-her-free-energy-bookkeeper",
                "role": "alkaline electrochemical free-energy bookkeeping and reference-policy application",
            }
        )
    return {
        "tools_used_for_energy_bookkeeping": tools,
        "note_for_writer": "Translate tool names into academic method language in public prose; do not cite internal skill names directly.",
    }


def procedures_by_index(procedures: list[Any], indexes: list[int]) -> list[str]:
    out = []
    for index in indexes:
        if 0 <= index < len(procedures):
            out.append(str(procedures[index]))
    return out


def build_minimal_evidence(
    *,
    strategy_id: str,
    computational: dict[str, Any],
    model_manifest: dict[str, Any] | None,
    gas_metadata: dict[str, Any] | None,
    reference_policy: dict[str, Any] | None,
    vib_summary: dict[str, Any] | None,
    relax_summary: dict[str, Any] | None,
    relaxation_registry: dict[str, Any] | None,
    free_energy_bookkeeping: dict[str, Any] | None,
) -> dict[str, Any]:
    dft_details = computational.get("dft_details", {}) if isinstance(computational.get("dft_details"), dict) else {}
    procedures = computational.get("procedures", []) if isinstance(computational.get("procedures"), list) else []
    methods = computational.get("methods", []) if isinstance(computational.get("methods"), list) else []

    model_manifest_compact = compact_model_manifest(model_manifest)
    gas_example = compact_gas_metadata(gas_metadata)
    ref_policy = compact_reference_policy(reference_policy)
    vib_compact = compact_vibration_summary(vib_summary)
    relax_compact = compact_relaxation_summary(relax_summary, relaxation_registry)
    energy_tools = energy_tool_summary(vib_summary, free_energy_bookkeeping)

    sections = [
        {
            "section_id": "model_construction",
            "title": SECTION_TITLES["model_construction"],
            "strategy_inputs": {
                "models": computational.get("models", []),
                "slab_model": dft_details.get("slab_model"),
                "adsorption_sites": dft_details.get("adsorption_sites", []),
            },
            "project_details": {
                "motif_labels": model_manifest_compact["motif_labels"],
                "states": model_manifest_compact["states"],
                "motif_state_pairs": model_manifest_compact["motif_state_pairs"],
                "gas_model_example": gas_example,
            },
            "procedure_inputs": procedures_by_index(procedures, [0]),
        },
        {
            "section_id": "geometry_optimization",
            "title": SECTION_TITLES["geometry_optimization"],
            "strategy_inputs": {
                "methods": methods,
                "code": dft_details.get("code"),
                "functional": dft_details.get("functional"),
                "pseudopotentials_or_paw": dft_details.get("pseudopotentials_or_paw"),
                "plane_wave_cutoff": dft_details.get("plane_wave_cutoff"),
                "k_point_mesh": dft_details.get("k_point_mesh"),
                "convergence_criteria": dft_details.get("convergence_criteria"),
                "dispersion_correction": dft_details.get("dispersion_correction"),
                "other_settings": dft_details.get("other_settings", []),
            },
            "project_details": {
                "relaxation_summary": relax_compact,
                "vasp_execution_boundary": "VASP-compatible input files may be prepared, but VASP jobs are not submitted in this UMA-only test run.",
            },
            "procedure_inputs": procedures_by_index(procedures, [1]),
        },
        {
            "section_id": "vibrational_free_energy_corrections",
            "title": SECTION_TITLES["vibrational_free_energy_corrections"],
            "strategy_inputs": {
                "thermodynamic_corrections": dft_details.get("thermodynamic_corrections"),
            },
            "project_details": {
                "vibration_summary": vib_compact,
                "surface_thermal_policy": ref_policy.get("surface_thermal_policy"),
                "energy_tools": energy_tools,
            },
            "procedure_inputs": procedures_by_index(procedures, [2, 3]),
        },
        {
            "section_id": "electrochemical_free_energy_formalism",
            "title": SECTION_TITLES["electrochemical_free_energy_formalism"],
            "strategy_inputs": {
                "methods": [item for item in methods if "free" in str(item).lower() or "reference" in str(item).lower()],
                "thermodynamic_corrections": dft_details.get("thermodynamic_corrections"),
            },
            "project_details": {
                "reference_policy": ref_policy,
                "energy_tools": energy_tools,
            },
            "procedure_inputs": procedures_by_index(procedures, [2, 3]),
        },
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "collector": "methods-evidence-collector",
        "strategy_id": strategy_id,
        "purpose": "Minimal deterministic source for drafting only the four core Methods sections.",
        "source_strategy_computational": {
            "models": computational.get("models", []),
            "methods": computational.get("methods", []),
            "dft_details": dft_details,
            "procedures": procedures,
        },
        "sections": sections,
        "excluded_in_this_version": [
            "descriptor_analysis",
            "electronic_structure_analysis",
            "standalone_scope_or_limitations_section",
        ],
    }


def writer_digest_from_minimal(minimal: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": minimal["schema_version"],
        "collector": minimal["collector"],
        "strategy_id": minimal["strategy_id"],
        "purpose": minimal["purpose"],
        "sections": minimal["sections"],
        "writer_rules": [
            "Write only the four included sections.",
            "Do not add descriptor-analysis, electronic-structure-analysis, or standalone limitations sections.",
            "Do not write internal skill names in public prose; translate them into academic method descriptions.",
            "Do not mention file paths, JSON names, or internal workflow ids.",
        ],
    }


def default_outdir(project: Path, strategy_id: str) -> Path:
    return project / "strategy_execution" / f"{strategy_id}_methods" / "evidence"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Project directory, for example project/<project_name>.")
    parser.add_argument("--strategy-id", default="", help="Strategy id such as S1. Inferred from selected_strategy.json when omitted.")
    parser.add_argument("--strategy", default="", help="Path to selected_strategy.json.")
    parser.add_argument("--execution-root", default="", help="Path to <strategy_id>_execution.")
    parser.add_argument("--outdir", default="", help="Output directory. Defaults to project/.../<strategy_id>_methods/evidence.")
    parser.add_argument("--keep-legacy", action="store_true", help="Do not delete older evidence JSON files in the output directory.")
    return parser.parse_args()


def write_summary(path: Path, minimal: dict[str, Any]) -> None:
    lines = [
        "# Methods Evidence Summary",
        "",
        f"- Strategy: `{minimal['strategy_id']}`",
        f"- Schema version: {minimal['schema_version']}",
        f"- Included sections: {len(minimal['sections'])}",
        f"- Excluded in this version: {', '.join(minimal['excluded_in_this_version'])}",
        "",
        "## Included Sections",
        "",
    ]
    for section in minimal["sections"]:
        details = section.get("project_details", {})
        lines.append(f"- `{section['section_id']}`: {section['title']}")
        if section["section_id"] == "model_construction":
            lines.append(f"  - motif labels: {len(details.get('motif_labels', []))}")
            lines.append(f"  - states: {len(details.get('states', []))}")
        if section["section_id"] == "geometry_optimization":
            summary = details.get("relaxation_summary", {})
            lines.append(f"  - relaxation tasks: {summary.get('task_count')}")
            lines.append(f"  - converged records: {summary.get('converged_count')}")
        if section["section_id"] == "vibrational_free_energy_corrections":
            summary = details.get("vibration_summary", {})
            lines.append(f"  - vibration tasks: {summary.get('task_count')}")
            lines.append(f"  - frequency results: {summary.get('frequency_result_count')}")
        if section["section_id"] == "electrochemical_free_energy_formalism":
            policy = details.get("reference_policy", {})
            lines.append(f"  - pH: {policy.get('pH')}")
            lines.append(f"  - U/V_RHE: {policy.get('potential_V_RHE')}")
    write_text(path, "\n".join(lines) + "\n")


def main() -> None:
    args = parse_args()
    project = Path(args.project)
    strategy_path = Path(args.strategy) if args.strategy else project / "strategy_execution" / "strategy_selection" / "selected_strategy.json"
    strategy_data = read_json(strategy_path)
    strategy_id = args.strategy_id or strategy_id_from_payload(strategy_data)
    if not strategy_id:
        raise SystemExit("Could not determine strategy id. Provide --strategy-id.")

    execution_root = Path(args.execution_root) if args.execution_root else project / "strategy_execution" / f"{strategy_id}_execution"
    outdir = Path(args.outdir) if args.outdir else default_outdir(project, strategy_id)

    computational = computational_from_strategy(strategy_data)
    model_manifest = load_json_if_exists(first_glob(execution_root, "**/model_manifest.json"))
    gas_metadata = load_json_if_exists(first_glob(execution_root, "**/gas_models/H2/*metadata.json", "**/gas_models/*/*metadata.json"))
    reference_policy = load_json_if_exists(first_glob(execution_root, "**/reference_policy.json"))
    vib_summary = load_json_if_exists(first_glob(execution_root, "**/uma_vib_batch_summary.json"))
    relax_summary = load_json_if_exists(first_glob(execution_root, "**/uma_relax_batch_summary.json"))
    relaxation_registry = load_json_if_exists(first_glob(execution_root, "**/final_relaxation_registry.json"))
    free_energy_bookkeeping = load_json_if_exists(first_glob(execution_root, "**/*free_energy_bookkeeping.json"))

    minimal = build_minimal_evidence(
        strategy_id=strategy_id,
        computational=computational,
        model_manifest=model_manifest,
        gas_metadata=gas_metadata,
        reference_policy=reference_policy,
        vib_summary=vib_summary,
        relax_summary=relax_summary,
        relaxation_registry=relaxation_registry,
        free_energy_bookkeeping=free_energy_bookkeeping,
    )
    writer = writer_digest_from_minimal(minimal)

    outdir.mkdir(parents=True, exist_ok=True)
    if not args.keep_legacy:
        for name in (
            "methods_raw_evidence.json",
            "methods_section_packets.json",
            "methods_procedure_evidence.json",
            "methods_execution_category_digest.json",
        ):
            path = outdir / name
            if path.exists():
                path.unlink()

    write_json(outdir / "methods_minimal_evidence.json", minimal)
    write_json(outdir / "methods_writer_digest.json", writer)
    write_summary(outdir / "methods_evidence_summary.md", minimal)

    print(f"Wrote {outdir / 'methods_minimal_evidence.json'}")
    print(f"Wrote {outdir / 'methods_writer_digest.json'}")
    print(f"Wrote {outdir / 'methods_evidence_summary.md'}")


if __name__ == "__main__":
    main()
