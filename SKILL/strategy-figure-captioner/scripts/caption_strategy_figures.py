#!/usr/bin/env python3
"""Create manuscript captions for realized strategy figures."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.5"

CAPTION_PROMPT = """You are writing public, manuscript-style figure captions for a computational chemistry/DFT catalysis project.

You will receive public figure evidence plus internal provenance extracted from figure_info.json and figure_realization.json.
Internal provenance is for audit only; it must not appear in caption text.

Strict rules:
1. Do not invent scientific conclusions, mechanisms, performance claims, experimental claims, or unsupported descriptors.
2. Use only the public figure evidence: figure type, routed type, realized state, scientific system label, reaction label, plotted quantities, draft title, and draft caption.
3. Do not mention internal workflow language: strategy, procedure, P001-style IDs, C001-style IDs, source procedure, mapping, realization, realized, exported, PNG, QA, caveat, blocker, artifact, manifest, or file paths.
4. For blocked figures, return empty figure_title, caption, and extended_caption.
5. Keep captions descriptive, concise, academically conventional, and suitable for direct use in a paper.
6. Mention computed/plotted quantities only when they appear in the public evidence.
7. Do not mention overpotential, Tafel slope, synthesis, microscopy, spectroscopy, or experimental characterization unless the supplied figure type explicitly says benchmark/experimental.

Return JSON only.

Schema:
{
  "captions": [
    {
      "figure_id": "F1",
      "figure_title": "Short public figure title without trailing punctuation.",
      "caption": "One or two sentence caption.",
      "extended_caption": "Optional longer manuscript caption without internal provenance."
    }
  ]
}
"""

BANNED_CLAIM_TERMS = {
    "experimentally",
    "measured",
    "synthesized",
    "microscopy",
    "spectroscopy",
    "performance",
    "overpotential",
    "tafel",
    "improves",
    "enhances",
    "superior",
    "best catalyst",
}

FORBIDDEN_PUBLIC_PATTERNS = [
    r"\bstrategy\b",
    r"\bstrategies\b",
    r"\bprocedure\b",
    r"\bprocedures\b",
    r"\bsource\b",
    r"\bsources\b",
    r"\bmapping\b",
    r"\bmapped\b",
    r"\brealization\b",
    r"\brealized\b",
    r"\bexported\b",
    r"\bpng\b",
    r"\bsvg\b",
    r"\bpdf\b",
    r"\bqa\b",
    r"\bcaveat\b",
    r"\bcaveats\b",
    r"\bblocker\b",
    r"\bblockers\b",
    r"\bartifact\b",
    r"\bartifacts\b",
    r"\bmanifest\b",
    r"\bworkflow\b",
    r"\bfigure_info\b",
    r"\bfigure_realization\b",
    r"\bgrounding\b",
    r"\bgrounded\b",
    r"\bP\d{3}\b",
    r"\bC\d{3}\b",
    r"\bP\d{3}/C\d{3}\b",
    r"[/\\][A-Za-z0-9_.-]+",
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_default_env() -> None:
    cwd = Path.cwd()
    for path in (cwd / ".env", cwd / "DEPENDENCY" / ".env"):
        load_env_file(path)


def figure_root_from_mapping(mapping: Path) -> Path:
    if mapping.name == "figure_info.json" and mapping.parent.name == "mapping":
        return mapping.parent.parent
    return mapping.parent


def default_realization_path(mapping: Path) -> Path:
    return figure_root_from_mapping(mapping) / "realization" / "figure_realization.json"


def default_outdir(mapping: Path) -> Path:
    return figure_root_from_mapping(mapping) / "caption"


def output_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct:
        return direct
    chunks: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)


def parse_json_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(stripped[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("Caption output must be a JSON object.")
    return data


def call_openai(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"OpenAI API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"OpenAI API request failed: {exc.reason}") from exc


def nice_label(text: str) -> str:
    return text.replace("_ev", " (eV)").replace("_", " ")


def human_quantity(quantity: str) -> str:
    labels = {
        "delta_g_h_ev": "Delta G_H (eV)",
        "delta_g_oh_ev": "Delta G_OH (eV)",
        "delta_g_h2o_ev": "Delta G_H2O (eV)",
        "thermodynamic_span_ev": "thermodynamic span (eV)",
        "largest_uphill_step_ev": "largest uphill step (eV)",
        "h2_desorption_free_energy_ev": "H2* desorption free energy (eV)",
    }
    if quantity in labels:
        return labels[quantity]
    if quantity == "free_energy_profile":
        return "free-energy profile"
    if quantity == "potential_shift":
        return "potential-shifted free-energy profile"
    if quantity == "charge_transfer":
        return "charge-transfer descriptor"
    if quantity == "projected_dos":
        return "projected DOS"
    if quantity == "structure-grid":
        return "structure grid"
    if quantity == "calculation-diagnostic":
        return "calculation diagnostic"
    return nice_label(quantity)


def extract_metric_from_notes(notes: list[str]) -> str:
    for note in notes:
        match = re.search(r"`([^`]+)`", note)
        if match:
            return match.group(1)
    return ""


def realization_by_id(realization: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(fig.get("id")): fig for fig in realization.get("figures", []) if isinstance(fig, dict)}


def source_basis(fig: dict[str, Any]) -> list[str]:
    procedures = fig.get("source", {}).get("procedures", [])
    return [str(item) for item in procedures]


def source_calculations(fig: dict[str, Any]) -> list[str]:
    calculations = fig.get("source", {}).get("calculations", [])
    return [str(item) for item in calculations]


def compact_text(value: Any) -> str:
    return " ".join(str(value).split())


def evidence_text(fig: dict[str, Any]) -> str:
    pieces: list[str] = []
    for key in ("figure_type", "title", "claim"):
        if fig.get(key):
            pieces.append(str(fig[key]))
    for item in fig.get("artifacts", []):
        pieces.append(str(item))
    grounding = fig.get("grounding", {})
    for item in grounding.get("basis", []):
        pieces.append(str(item))
    for item in grounding.get("quantities", []):
        pieces.append(str(item))
    return "\n".join(pieces)


def system_label(fig: dict[str, Any]) -> str:
    lowered = evidence_text(fig).lower()
    if "mos2" in lowered and "ni" in lowered:
        return "pristine and Ni-modified MoS2 edge motifs"
    if "mos2" in lowered:
        return "MoS2 edge motifs"
    if "edge" in lowered:
        return "modeled catalyst edge motifs"
    return "modeled catalyst motifs"


def global_system_label(mapping: dict[str, Any]) -> str:
    lowered = "\n".join(
        evidence_text(fig)
        for fig in mapping.get("figures", [])
        if isinstance(fig, dict)
    ).lower()
    if "mos2" in lowered and "ni" in lowered:
        return "pristine and Ni-modified MoS2 edge motifs"
    if "mos2" in lowered:
        return "MoS2 edge motifs"
    if "edge" in lowered:
        return "modeled catalyst edge motifs"
    return "modeled catalyst motifs"


def reaction_label(fig: dict[str, Any]) -> str:
    lowered = evidence_text(fig).lower()
    has_her = "her" in lowered or "hydrogen evolution" in lowered
    if "alkaline" in lowered and has_her:
        return "alkaline HER"
    if has_her:
        return "HER"
    return "the modeled reaction pathway"


def condition_phrase(fig: dict[str, Any]) -> str:
    lowered = evidence_text(fig).lower()
    if "ph 14" in lowered and ("0 v_rhe" in lowered or "0 v rhe" in lowered or "0 v" in lowered):
        return "at pH 14 and U = 0 V_RHE"
    if "ph 14" in lowered:
        return "at pH 14"
    return "under the modeled reaction conditions"


def adsorbate_phrase(fig: dict[str, Any]) -> str:
    lowered = evidence_text(fig).lower()
    labels: list[str] = []
    for token, label in (
        ("h2o", "H2O*"),
        ("h_oh", "coadsorbed H*+OH*"),
        ("h2", "H2*"),
        ("oh", "OH*"),
        ("/h/", "H*"),
    ):
        if token in lowered and label not in labels:
            labels.append(label)
    if labels:
        return ", ".join(labels)
    return "adsorbate-bearing"


def clean_title(text: str) -> str:
    return compact_text(text).rstrip(".:;")


def deterministic_title(fig: dict[str, Any], routed_type: str) -> str:
    figure_type = str(fig.get("figure_type") or fig.get("title") or fig.get("type", "Figure"))
    if routed_type == "energy-diagram":
        reaction = reaction_label(fig)
        if reaction == "alkaline HER":
            return "Alkaline HER free-energy diagram"
        if reaction == "HER":
            return "HER free-energy diagram"
        return "Free-energy diagram"
    return clean_title(figure_type)


def provenance(fig: dict[str, Any], rec: dict[str, Any], blockers: list[str] | None = None) -> dict[str, Any]:
    return {
        "source_basis": source_basis(fig),
        "source_calculations": source_calculations(fig),
        "grounding_quantities": [str(item) for item in fig.get("grounding", {}).get("quantities", [])],
        "exported_files": [str(path) for path in rec.get("exported_files", [])],
        "source_files": [str(path) for path in rec.get("source_files", [])],
        "realization_notes": [str(note) for note in rec.get("notes", [])],
        "caveats": [str(item) for item in fig.get("caveats", [])],
        "blockers": blockers if blockers is not None else [str(item) for item in fig.get("blockers", [])],
    }


def blocked_caption(fig: dict[str, Any], rec: dict[str, Any]) -> dict[str, Any]:
    blockers = [str(item) for item in fig.get("blockers", [])]
    if rec.get("notes"):
        blockers.extend(str(note) for note in rec.get("notes", []))
    prov = provenance(fig, rec, blockers)
    return {
        "figure_id": fig["id"],
        "state": rec.get("state", fig.get("status", "blocked")),
        "figure_type": fig.get("figure_type") or fig.get("title") or fig.get("type", ""),
        "routed_type": fig.get("type", ""),
        "exported_files": prov["exported_files"],
        "figure_title": "",
        "caption": "",
        "extended_caption": "",
        "source_basis": prov["source_basis"],
        "caption_source": "blocked",
        "caveats": prov["caveats"],
        "blockers": blockers,
        "provenance": prov,
    }


def deterministic_caption(fig: dict[str, Any], rec: dict[str, Any], system_override: str = "") -> dict[str, Any]:
    figure_id = str(fig.get("id", ""))
    figure_type = str(fig.get("figure_type") or fig.get("title") or fig.get("type", "Figure"))
    routed_type = str(fig.get("type", ""))
    state = str(rec.get("state", fig.get("status", "")))
    notes = [str(note) for note in rec.get("notes", [])]
    quantities = [str(item) for item in fig.get("grounding", {}).get("quantities", [])]
    exported = [str(path) for path in rec.get("exported_files", [])]
    prov = provenance(fig, rec)
    figure_title = deterministic_title(fig, routed_type)

    if state in {"blocked", "skipped", "failed"} or not exported:
        return blocked_caption(fig, rec)

    system = system_override or system_label(fig)
    metric = extract_metric_from_notes(notes)
    quantity_text = human_quantity(metric) if metric else ", ".join(human_quantity(q) for q in quantities[:3])

    if routed_type == "structure-grid" and "adsorbate" in figure_type.lower():
        caption = f"Representative {adsorbate_phrase(fig)} configurations are shown on {system}."
        extended = ""
    elif routed_type == "structure-grid":
        caption = f"Clean catalyst structures are shown for {system}."
        extended = ""
    elif routed_type == "energy-diagram":
        caption = f"Computed relative free energies are compared for modeled reaction states on {system} {condition_phrase(fig)}."
        extended = ""
    elif routed_type == "descriptor-comparison":
        if quantity_text:
            caption = f"Bars show computed {quantity_text} values across {system}."
        else:
            caption = f"Computed thermodynamic quantities are compared across {system}."
        extended = "The comparison summarizes the thermodynamic quantities calculated for each modeled motif."
    elif routed_type == "calculation-diagnostic":
        caption = f"Side and top views summarize optimized adsorbate configurations on {system}."
        extended = "The final relaxed geometries are used for thermodynamic analysis."
    else:
        caption = f"Computed quantities are summarized for {system}."
        extended = "The panel summarizes the computed quantities shown in the figure."

    record = {
        "figure_id": figure_id,
        "state": state,
        "figure_type": figure_type,
        "routed_type": routed_type,
        "exported_files": exported,
        "figure_title": figure_title,
        "caption": compact_text(caption),
        "extended_caption": compact_text(extended),
        "source_basis": prov["source_basis"],
        "caption_source": "deterministic",
        "caveats": prov["caveats"],
        "blockers": prov["blockers"],
        "provenance": prov,
    }
    if public_caption_is_invalid(record["figure_title"] + " " + record["caption"] + " " + record["extended_caption"], figure_type):
        record["figure_title"] = clean_title(figure_type)
        record["caption"] = f"Computed data are summarized for {system}."
        record["extended_caption"] = ""
        record["caption_source"] = "deterministic-style-fallback"
    return record


def build_caption_records(mapping: dict[str, Any], realization: dict[str, Any]) -> list[dict[str, Any]]:
    real_by_id = realization_by_id(realization)
    records: list[dict[str, Any]] = []
    system = global_system_label(mapping)
    for fig in mapping.get("figures", []):
        if not isinstance(fig, dict) or not fig.get("id"):
            continue
        rec = real_by_id.get(str(fig["id"]), {})
        records.append(deterministic_caption(fig, rec, system))
    return records


def prompt_evidence(records: list[dict[str, Any]], mapping: dict[str, Any]) -> dict[str, Any]:
    evidence = []
    for record in records:
        evidence.append(
            {
                "figure_id": record["figure_id"],
                "state": record["state"],
                "figure_type": record["figure_type"],
                "routed_type": record["routed_type"],
                "public_evidence": {
                    "draft_figure_title": record["figure_title"],
                    "draft_caption": record["caption"],
                    "draft_extended_caption": record["extended_caption"],
                    "plotted_quantities": record.get("provenance", {}).get("grounding_quantities", []),
                },
                "internal_provenance_do_not_cite": record.get("provenance", {}),
            }
        )
    return {"strategy_id": mapping.get("strategy_id", ""), "figures": evidence}

def build_prompt(records: list[dict[str, Any]], mapping: dict[str, Any]) -> str:
    return f"{CAPTION_PROMPT}\n\nGrounded figure evidence:\n{json.dumps(prompt_evidence(records, mapping), indent=2)}\n"


def build_payload(model: str, prompt: str) -> dict[str, Any]:
    return {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            }
        ],
    }


def caption_has_banned_claim(caption: str, figure_type: str) -> bool:
    lowered = caption.lower()
    allow_benchmark = "benchmark" in figure_type.lower()
    for term in BANNED_CLAIM_TERMS:
        if term in {"overpotential", "tafel", "performance"} and allow_benchmark:
            continue
        if term in lowered:
            return True
    return False


def caption_has_forbidden_public_text(caption: str) -> bool:
    return any(re.search(pattern, caption, flags=re.IGNORECASE) for pattern in FORBIDDEN_PUBLIC_PATTERNS)


def public_caption_is_invalid(caption: str, figure_type: str) -> bool:
    return caption_has_banned_claim(caption, figure_type) or caption_has_forbidden_public_text(caption)


def apply_llm_captions(records: list[dict[str, Any]], llm_payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = llm_payload.get("captions")
    if not isinstance(raw, list):
        raise ValueError("LLM caption JSON must contain a captions list.")
    by_id = {str(item.get("figure_id")): item for item in raw if isinstance(item, dict)}
    updated = []
    for record in records:
        item = by_id.get(record["figure_id"])
        if not item or record["state"] in {"blocked", "skipped", "failed"}:
            updated.append(record)
            continue
        figure_title = clean_title(item.get("figure_title", "")) or record.get("figure_title", "")
        caption = compact_text(item.get("caption", ""))
        extended = compact_text(item.get("extended_caption", ""))
        if not caption or public_caption_is_invalid(figure_title + " " + caption + " " + extended, record["figure_type"]):
            updated.append(record)
            continue
        new_record = dict(record)
        new_record["figure_title"] = figure_title
        new_record["caption"] = caption
        new_record["extended_caption"] = extended or record["extended_caption"]
        new_record["caption_source"] = "llm-polished"
        updated.append(new_record)
    return updated


def md_cell(value: Any) -> str:
    return compact_text(value).replace("|", "\\|")


def caption_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Figure Captions for {payload.get('strategy_id') or 'strategy'}",
        "",
        "## Public Captions",
        "",
        "| Figure | State | Title | Caption | Extended Caption |",
        "| --- | --- | --- | --- | --- |",
    ]
    for cap in payload.get("captions", []):
        figure_title = cap.get("figure_title") or ""
        caption = cap.get("caption") or "_not captioned_"
        extended = cap.get("extended_caption") or ""
        lines.append(f"| {md_cell(cap['figure_id'])} | {md_cell(cap['state'])} | {md_cell(figure_title)} | {md_cell(caption)} | {md_cell(extended)} |")

    lines.extend(["", "## Internal Provenance", ""])
    for cap in payload.get("captions", []):
        prov = cap.get("provenance", {}) if isinstance(cap.get("provenance"), dict) else {}
        lines.append(f"### {cap['figure_id']} {cap.get('figure_type', '')}")
        lines.append(f"- State: `{cap.get('state', '')}`")
        lines.append(f"- Caption mode: `{cap.get('caption_source', '')}`")
        if cap.get("figure_title"):
            lines.append(f"- Public figure title: {cap['figure_title']}")
        if cap.get("caption"):
            lines.append(f"- Public caption: {cap['caption']}")
        if cap.get("extended_caption"):
            lines.append(f"- Public extended caption: {cap['extended_caption']}")
        exported_files = prov.get("exported_files") or cap.get("exported_files") or []
        if exported_files:
            lines.append("- Exported files:")
            lines.extend(f"  - `{path}`" for path in exported_files)
        source_basis = prov.get("source_basis") or cap.get("source_basis") or []
        if source_basis:
            lines.append(f"- Source procedures: {', '.join(source_basis)}")
        source_calculations = prov.get("source_calculations") or []
        if source_calculations:
            lines.append(f"- Source calculations: {', '.join(source_calculations)}")
        quantities = prov.get("grounding_quantities") or []
        if quantities:
            lines.append(f"- Grounding quantities: {', '.join(quantities)}")
        caveats = prov.get("caveats") or cap.get("caveats") or []
        if caveats:
            lines.append("- Caveats:")
            lines.extend(f"  - {item}" for item in caveats)
        blockers = prov.get("blockers") or cap.get("blockers") or []
        if blockers:
            lines.append("- Blockers:")
            lines.extend(f"  - {item}" for item in blockers)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create public figure titles and captions for MESA strategy figures.")
    parser.add_argument("--mapping", required=True, help="Path to figure_info.json.")
    parser.add_argument("--realization", help="Path to figure_realization.json. Defaults beside mapping.")
    parser.add_argument("--outdir", help="Caption output directory. Defaults to <figure-root>/caption.")
    parser.add_argument("--no-llm", action="store_true", help="Use deterministic captions only.")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL), help=f"OpenAI model. Defaults to OPENAI_MODEL or {DEFAULT_MODEL}.")
    parser.add_argument("--save-prompt", help="Write the exact LLM prompt.")
    parser.add_argument("--save-response", help="Write the full OpenAI response JSON.")
    return parser


def main() -> int:
    load_default_env()
    args = build_parser().parse_args()
    mapping_path = Path(args.mapping)
    realization_path = Path(args.realization) if args.realization else default_realization_path(mapping_path)
    outdir = Path(args.outdir) if args.outdir else default_outdir(mapping_path)

    mapping = read_json(mapping_path)
    realization = read_json(realization_path)
    records = build_caption_records(mapping, realization)

    caption_source = "deterministic"
    if not args.no_llm:
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            prompt = build_prompt(records, mapping)
            if args.save_prompt:
                write_text(Path(args.save_prompt), prompt)
            response = call_openai(build_payload(args.model, prompt), api_key)
            if args.save_response:
                write_json(Path(args.save_response), response)
            text = output_text(response)
            if text:
                try:
                    records = apply_llm_captions(records, parse_json_text(text))
                    caption_source = "llm-polished"
                except Exception:
                    caption_source = "deterministic-fallback"
        else:
            caption_source = "deterministic-no-api-key"

    payload = {
        "schema_version": 2,
        "strategy_id": mapping.get("strategy_id", realization.get("strategy_id", "")),
        "mapping": str(mapping_path),
        "realization": str(realization_path),
        "caption_source": caption_source,
        "captions": records,
    }
    write_json(outdir / "caption_info.json", payload)
    write_text(outdir / "caption_info.md", caption_markdown(payload))
    print(f"Wrote {outdir / 'caption_info.json'}")
    print(f"Wrote {outdir / 'caption_info.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
