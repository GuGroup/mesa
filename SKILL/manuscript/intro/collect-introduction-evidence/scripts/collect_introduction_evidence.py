#!/usr/bin/env python3
"""Collect compact evidence for a manuscript Introduction."""

from __future__ import annotations

import argparse
import ast
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1

ROLE_KEYWORDS: dict[str, list[str]] = {
    "field_motivation": [
        "catalyst", "catalysis", "reaction", "energy", "conversion", "selectivity",
        "activity", "stability", "efficiency", "sustainable", "low-cost",
        "abundant", "precious", "noble", "performance",
    ],
    "catalyst_platform": [
        "material", "catalyst", "surface", "site", "active site", "support",
        "phase", "defect", "edge", "facet", "coordination", "structure",
    ],
    "design_rationale": [
        "doping", "dopant", "substitution", "decoration", "alloy", "defect",
        "strain", "coordination", "composition", "modification", "tuning",
        "adsorption", "energetics",
    ],
    "mechanistic_gap": [
        "mechanism", "intermediate", "adsorption", "desorption", "barrier",
        "free energy", "descriptor", "thermodynamic", "kinetic", "pathway",
        "reaction condition", "pH", "potential",
    ],
    "prior_related_evidence": [
        "reported", "observed", "experiment", "experimental", "previous",
        "prior", "literature", "synthesis", "measurement", "activity",
        "performance", "selectivity",
    ],
    "computational_design_logic": [
        "dft", "density functional", "calculation", "computed", "free energy",
        "descriptor", "thermodynamic", "adsorption", "model", "simulation",
        "screening", "prediction",
    ],
}

ROLE_LIMITS = {
    "field_motivation": 4,
    "catalyst_platform": 5,
    "design_rationale": 5,
    "mechanistic_gap": 5,
    "prior_related_evidence": 5,
    "computational_design_logic": 4,
}

NARRATIVE_ORDER = [
    "field_motivation",
    "catalyst_platform",
    "design_rationale",
    "mechanistic_gap",
    "prior_related_evidence",
    "computational_design_logic",
    "present_work_framing",
]

WRITING_GUARDRAILS = [
    "Do not mention strategy, procedure, workflow, digest, JSON, skill, or file paths.",
    "Do not mention figures or Results-section numeric findings in the Introduction.",
    "Use selected-strategy content only for the final present-work framing.",
    "Do not add citation placeholders in the writer output; citation selection is a later layer.",
]


def load_json_if_exists(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    return read_json(path)


def apply_writing_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    global ROLE_KEYWORDS, ROLE_LIMITS, NARRATIVE_ORDER, WRITING_GUARDRAILS
    if not isinstance(profile, dict):
        return {}
    role_specs = profile.get("introduction_roles")
    if isinstance(role_specs, list) and role_specs:
        keywords: dict[str, list[str]] = {}
        limits: dict[str, int] = {}
        order: list[str] = []
        for item in role_specs:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            if not role:
                continue
            words = [str(word) for word in item.get("keywords", []) if str(word).strip()]
            keywords[role] = words
            limits[role] = int(item.get("limit", 5))
            order.append(role)
        if keywords:
            ROLE_KEYWORDS = keywords
            ROLE_LIMITS = limits
            NARRATIVE_ORDER = order + ["present_work_framing"]
    profile_order = profile.get("introduction_narrative_order")
    if isinstance(profile_order, list) and profile_order:
        NARRATIVE_ORDER = [str(role) for role in profile_order if str(role)] + [
            role for role in ["present_work_framing"] if role not in profile_order
        ]
    guardrails = profile.get("writing_guardrails")
    if isinstance(guardrails, list) and guardrails:
        WRITING_GUARDRAILS = [str(item) for item in guardrails if str(item)]
    return {
        "name": profile.get("name"),
        "introduction_roles": [
            {"role": role, "keywords": ROLE_KEYWORDS.get(role, []), "limit": ROLE_LIMITS.get(role, 5)}
            for role in NARRATIVE_ORDER
            if role != "present_work_framing"
        ],
        "introduction_narrative_order": NARRATIVE_ORDER,
    }


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def compact_text(value: Any, limit: int = 420) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def output_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct:
        return direct
    chunks: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)


def parse_assignment_object(text: str) -> Any | None:
    stripped = text.strip()
    match = re.search(r"^[A-Za-z_][A-Za-z0-9_]*\s*=\s*(\{.*\})\s*$", stripped, flags=re.S)
    if not match:
        return None
    try:
        return ast.literal_eval(match.group(1))
    except (SyntaxError, ValueError):
        return None


def infer_citation_key(path: Path, citation_sources: dict[str, Any]) -> str | None:
    stem = path.stem.lower().replace("_response", "")
    keys = {str(rec.get("citation_key")) for rec in citation_sources.get("primary_papers", [])}
    for key in keys:
        if key and key.lower() in stem:
            return key
    return None


def source_lookup(citation_sources: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for rec in citation_sources.get("primary_papers", []) + citation_sources.get("second_neighbor_references", []):
        key = rec.get("citation_key")
        if key:
            lookup[str(key)] = rec
    return lookup


def source_id_for(rec: dict[str, Any]) -> str:
    return str(rec.get("paper_id") or rec.get("reference_id") or rec.get("citation_key") or "")


def flatten_value(value: Any, prefix: str = "") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, sub in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.extend(flatten_value(sub, next_prefix))
    elif isinstance(value, list):
        for idx, sub in enumerate(value):
            next_prefix = f"{prefix}[{idx}]"
            out.extend(flatten_value(sub, next_prefix))
    elif isinstance(value, (str, int, float)):
        text = compact_text(value)
        if len(text) >= 40:
            out.append((prefix, text))
    return out


def fallback_lines(text: str) -> list[tuple[str, str]]:
    lines = []
    for idx, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip(" -\t")
        if len(line) < 50:
            continue
        if line.startswith(("Evidence:", "Source:", "Rationale:")):
            line = line.split(":", 1)[1].strip()
        lines.append((f"line_{idx}", compact_text(line)))
    return lines


def normalize_for_dedupe(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())[:180]


def should_drop_intro_claim(text: str) -> bool:
    lower = text.lower()
    if text.strip().endswith("?"):
        return True
    blocked_phrases = [
        "does not report explicit",
        "does not fully resolve",
        "the paper does not report",
        "fixed-layer choices",
        "constant-potential",
        "scope_or_limitations",
        "source_pdf_paths",
    ]
    return any(phrase in lower for phrase in blocked_phrases)


def role_score(text: str, role: str) -> int:
    lower = text.lower().replace("δ", "delta")
    score = 0
    for keyword in ROLE_KEYWORDS[role]:
        if keyword in lower:
            score += 1
    return score


def best_roles(text: str) -> list[tuple[str, int]]:
    scored = [(role, role_score(text, role)) for role in ROLE_KEYWORDS]
    return sorted([(role, score) for role, score in scored if score > 0], key=lambda item: item[1], reverse=True)


def collect_source_papers(citation_sources: dict[str, Any]) -> list[dict[str, Any]]:
    papers = []
    for rec in citation_sources.get("primary_papers", []):
        papers.append({
            "source_id": source_id_for(rec),
            "citation_key": rec.get("citation_key"),
            "title": rec.get("title"),
            "authors": rec.get("authors", []),
            "year": rec.get("year"),
            "doi": rec.get("doi"),
            "collection": rec.get("collection"),
            "source_role": rec.get("source_role"),
            "abstract_excerpt": compact_text(rec.get("abstract_excerpt"), 700),
        })
    return papers


def evidence_from_extraction(
    path: Path,
    citation_key: str | None,
    lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    response = read_json(path)
    text = output_text(response)
    parsed = parse_assignment_object(text)
    entries = flatten_value(parsed) if parsed is not None else fallback_lines(text)
    source = lookup.get(citation_key or "", {})
    source_id = source_id_for(source) if source else (citation_key or path.stem)
    title = source.get("title") or ""
    out = []
    for field, statement in entries:
        if not statement:
            continue
        if should_drop_intro_claim(statement):
            continue
        roles = best_roles(statement)
        if not roles:
            continue
        out.append({
            "field": field,
            "claim": statement,
            "citation_keys": [citation_key] if citation_key else [],
            "source_ids": [source_id] if source_id else [],
            "source_titles": [title] if title else [],
            "source_path": str(path),
            "role_scores": [{"role": role, "score": score} for role, score in roles[:3]],
        })
    return out


def collect_unkeyed_extraction_evidence(path: Path | None, lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    response = read_json(path)
    text = output_text(response)
    entries = fallback_lines(text)
    out = []
    for field, statement in entries:
        if should_drop_intro_claim(statement):
            continue
        roles = best_roles(statement)
        if not roles:
            continue
        out.append({
            "field": field,
            "claim": statement,
            "citation_keys": [],
            "source_ids": [],
            "source_titles": [],
            "source_path": str(path),
            "role_scores": [{"role": role, "score": score} for role, score in roles[:3]],
        })
    return out


def choose_evidence_by_role(candidates: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    seen_by_role: dict[str, set[str]] = defaultdict(set)
    for item in candidates:
        for role_score_item in item.get("role_scores", []):
            role = role_score_item["role"]
            score = int(role_score_item["score"])
            norm = normalize_for_dedupe(item["claim"])
            if norm in seen_by_role[role]:
                continue
            seen_by_role[role].add(norm)
            priority = score
            if item.get("citation_keys"):
                priority += 2
            field = str(item.get("field") or "")
            if any(token in field for token in ("central_thesis", "field_problem", "problem", "hypothesis", "conclusion")):
                priority += 2
            compact = {
                "claim": item["claim"],
                "citation_keys": item.get("citation_keys", []),
                "source_ids": item.get("source_ids", []),
                "source_titles": item.get("source_titles", []),
                "evidence_text": item["claim"],
                "source_field": item.get("field"),
                "source_path": item.get("source_path"),
                "score": priority,
            }
            buckets[role].append((priority, compact))
    selected: dict[str, list[dict[str, Any]]] = {}
    for role, items in buckets.items():
        items.sort(key=lambda x: x[0], reverse=True)
        limit = ROLE_LIMITS.get(role, 5)
        selected[role] = [item for _, item in items[:limit]]
    return selected


def project_positioning(selected_strategy_path: Path | None) -> dict[str, Any]:
    if selected_strategy_path is None or not selected_strategy_path.exists():
        return {
            "selected_strategy_id": "",
            "selected_strategy_title": "",
            "present_work_question": "",
            "present_work_gap": "",
            "present_work_scope": [],
        }
    data = read_json(selected_strategy_path)
    strategy = data.get("selected_strategy", data)
    problem = strategy.get("problem", {}) if isinstance(strategy, dict) else {}
    experiment = strategy.get("experiment", {}) if isinstance(strategy, dict) else {}
    computational = experiment.get("computational", {}) if isinstance(experiment, dict) else {}
    methods = computational.get("methods", []) if isinstance(computational, dict) else []
    models = computational.get("models", []) if isinstance(computational, dict) else []
    procedures = computational.get("procedures", []) if isinstance(computational, dict) else []
    procedure_texts = []
    for item in procedures[:4]:
        if isinstance(item, dict):
            procedure_texts.append(compact_text(item.get("description") or item.get("step") or item, 220))
        else:
            procedure_texts.append(compact_text(item, 220))
    return {
        "selected_strategy_id": data.get("selected_strategy_id") or strategy.get("strategy_id", ""),
        "selected_strategy_title": data.get("selected_strategy_title") or strategy.get("title", ""),
        "present_work_question": compact_text(problem.get("question"), 700),
        "present_work_gap": compact_text(problem.get("unexplained_phenomenon"), 700),
        "present_work_context": compact_text(problem.get("context"), 700),
        "present_work_scope": [
            compact_text(item, 260)
            for item in (list(models[:5]) if isinstance(models, list) else [])
        ] + [
            compact_text(item, 260)
            for item in (list(methods[:5]) if isinstance(methods, list) else [])
        ] + procedure_texts[:4],
    }


def citation_seed(evidence_by_role: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    seen: dict[str, set[str]] = defaultdict(set)
    rows = []
    for role in NARRATIVE_ORDER:
        for point in evidence_by_role.get(role, []):
            for key in point.get("citation_keys", []):
                if key in seen[role]:
                    continue
                seen[role].add(key)
                rows.append({
                    "role": role,
                    "citation_key": key,
                    "source_ids": point.get("source_ids", []),
                    "source_titles": point.get("source_titles", []),
                    "example_claim": point.get("claim", ""),
                })
    return rows


def flatten_selected_points(evidence_by_role: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    points = []
    for role in NARRATIVE_ORDER:
        for point in evidence_by_role.get(role, []):
            points.append({
                "role": role,
                "claim": point.get("claim", ""),
                "citation_keys": point.get("citation_keys", []),
                "source_ids": point.get("source_ids", []),
                "source_titles": point.get("source_titles", []),
                "evidence_text": point.get("evidence_text", ""),
            })
    return points


def write_summary(path: Path, evidence: dict[str, Any]) -> None:
    lines = [
        "# Introduction Evidence Summary",
        "",
        f"- Project: `{evidence.get('project')}`",
        f"- Strategy ID: `{evidence.get('strategy_id')}`",
        f"- Source papers: {len(evidence.get('source_papers', []))}",
        f"- Evidence points: {sum(len(v) for v in evidence.get('evidence_by_role', {}).values())}",
        "",
    ]
    for role in NARRATIVE_ORDER:
        if role == "present_work_framing":
            continue
        items = evidence.get("evidence_by_role", {}).get(role, [])
        lines.extend([f"## {role}", ""])
        if not items:
            lines.append("- None")
        for item in items:
            keys = ", ".join(item.get("citation_keys", [])) or "uncited"
            lines.append(f"- [{keys}] {item.get('claim')}")
        lines.append("")
    pp = evidence.get("project_positioning", {})
    lines.extend([
        "## present_work_framing",
        "",
        f"- Strategy: {pp.get('selected_strategy_id')} | {pp.get('selected_strategy_title')}",
        f"- Question: {pp.get('present_work_question')}",
        f"- Gap: {pp.get('present_work_gap')}",
        "",
        "## Validation",
        "",
    ])
    for key, value in evidence.get("validation", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    write_text(path, "\n".join(lines) + "\n")


def default_paths(project: Path, strategy_id: str) -> dict[str, Path]:
    return {
        "citation_sources": project / "references" / "citation_sources.json",
        "selected_strategy": project / "strategy_execution" / "strategy_selection" / "selected_strategy.json",
        "paper_extraction_dir": project / "strategy_generation" / "paper_extraction",
        "experimental_extraction": project / "strategy_generation" / "experimental_extraction" / "openai_response.json",
        "writing_profile": project / "manuscript_writing_profile.json",
        "outdir": project / "strategy_execution" / f"{strategy_id}_introduction" / "evidence",
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    project = Path(args.project)
    strategy_id = args.strategy_id
    paths = default_paths(project, strategy_id)
    citation_sources_path = Path(args.citation_sources) if args.citation_sources else paths["citation_sources"]
    selected_strategy_path = Path(args.selected_strategy) if args.selected_strategy else paths["selected_strategy"]
    paper_extraction_dir = Path(args.paper_extraction_dir) if args.paper_extraction_dir else paths["paper_extraction_dir"]
    experimental_extraction = Path(args.experimental_extraction) if args.experimental_extraction else paths["experimental_extraction"]
    writing_profile_path = Path(args.writing_profile) if args.writing_profile else paths["writing_profile"]
    outdir = Path(args.outdir) if args.outdir else paths["outdir"]
    writing_profile = apply_writing_profile(load_json_if_exists(writing_profile_path))

    citation_sources = read_json(citation_sources_path)
    lookup = source_lookup(citation_sources)
    candidates: list[dict[str, Any]] = []
    extraction_paths = sorted(paper_extraction_dir.glob("*/*_response.json"))
    for path in extraction_paths:
        key = infer_citation_key(path, citation_sources)
        candidates.extend(evidence_from_extraction(path, key, lookup))
    candidates.extend(collect_unkeyed_extraction_evidence(experimental_extraction, lookup))
    evidence_by_role = choose_evidence_by_role(candidates)
    positioning = project_positioning(selected_strategy_path)
    validation = {
        "source_paper_count": len(citation_sources.get("primary_papers", [])),
        "paper_extraction_count": len(extraction_paths),
        "raw_candidate_count": len(candidates),
        "selected_evidence_count": sum(len(v) for v in evidence_by_role.values()),
        "roles_with_evidence": sorted(role for role, items in evidence_by_role.items() if items),
        "has_project_positioning": bool(positioning.get("present_work_question")),
    }
    source_files = {
        "citation_sources": str(citation_sources_path),
        "selected_strategy": str(selected_strategy_path),
        "paper_extraction_dir": str(paper_extraction_dir),
        "paper_extraction_responses": [str(path) for path in extraction_paths],
        "experimental_extraction": str(experimental_extraction) if experimental_extraction.exists() else None,
        "writing_profile": str(writing_profile_path) if writing_profile_path.exists() else None,
    }
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "project": str(project),
        "strategy_id": strategy_id,
        "source_files": source_files,
        "source_papers": collect_source_papers(citation_sources),
        "writing_profile": writing_profile,
        "evidence_by_role": evidence_by_role,
        "project_positioning": positioning,
        "citation_seed": citation_seed(evidence_by_role),
        "validation": validation,
    }
    digest = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": strategy_id,
        "section_goal": "Write a literature-led Introduction for a computational catalysis manuscript.",
        "narrative_order": NARRATIVE_ORDER,
        "writing_profile": writing_profile,
        "evidence_points": flatten_selected_points(evidence_by_role),
        "project_positioning": positioning,
        "writing_guardrails": WRITING_GUARDRAILS,
        "source_digest": "introduction_evidence.json",
    }
    write_json(outdir / "introduction_evidence.json", evidence)
    write_json(outdir / "introduction_writer_digest.json", digest)
    write_summary(outdir / "introduction_evidence_summary.md", evidence)
    return evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Project directory, e.g. project/<project_name>.")
    parser.add_argument("--strategy-id", default="S1", help="Strategy id for output folder naming.")
    parser.add_argument("--citation-sources", default="", help="Override citation_sources.json path.")
    parser.add_argument("--selected-strategy", default="", help="Override selected_strategy.json path.")
    parser.add_argument("--paper-extraction-dir", default="", help="Override paper extraction directory.")
    parser.add_argument("--experimental-extraction", default="", help="Override experimental extraction response path.")
    parser.add_argument("--writing-profile", default="", help="Optional manuscript_writing_profile.json path.")
    parser.add_argument("--outdir", default="", help="Override output directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    evidence = run(args)
    outdir = Path(args.outdir) if args.outdir else default_paths(Path(args.project), args.strategy_id)["outdir"]
    print(json.dumps({
        "ok": True,
        "outdir": str(outdir),
        "selected_evidence_count": evidence["validation"]["selected_evidence_count"],
        "roles_with_evidence": evidence["validation"]["roles_with_evidence"],
    }, indent=2))


if __name__ == "__main__":
    main()
