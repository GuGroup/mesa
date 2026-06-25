from __future__ import annotations

from typing import Any

# Claim types kept consistent with the rule extractor (paper_search.extraction)
# and the opportunity report (paper_search.opportunities).
CLAIM_TYPES = (
    "descriptor",
    "activity",
    "stability",
    "selectivity",
    "synthesis_or_morphology",
    "mechanism",
    "descriptor_activity_relation",
    "surface_mention",
)

# Controlled vocabularies for field-level extraction. The LLM must map each claim
# onto one of these (use "other" when nothing fits) so descriptor/method usage can
# be aggregated across systems. Keep these aligned with the report aggregation.
REACTION_TYPES = (
    "HER", "OER", "ORR", "HOR", "CO2RR", "CORR",
    "NRR", "NO3RR", "MOR", "UOR", "HzOR", "other",
)
DESCRIPTOR_TYPES = (
    "dG_H", "dG_O", "dG_OH", "dG_OOH", "dG_N", "dG_NH", "dG_NO", "dG_NO3",
    "dG_CO", "dG_COOH", "binding_energy", "overpotential", "limiting_potential",
    "d_band_center", "eg_occupancy", "charge_transfer", "bader_charge",
    "work_function", "oxygen_vacancy_formation", "formation_energy",
    "surface_energy", "pourbaix_stability", "dissolution_potential",
    "coordination_number", "strain", "scaling_relation", "other",
)
METHOD_TYPES = (
    "dft", "dft_che", "neb_ts", "microkinetics", "pourbaix", "aimd",
    "mlip", "bader_analysis", "dos_pdos", "constant_potential",
    "machine_learning", "experiment", "other",
)
# How a claim's system/reaction relates to the run target.
RELATIONS = ("both", "same_material", "same_reaction", "analogous")


def research_context_block(research_context: dict[str, Any]) -> str:
    if not research_context:
        return "(no additional research context provided)"
    lines = []
    for key, value in research_context.items():
        if isinstance(value, (list, tuple)):
            value = "; ".join(str(item) for item in value)
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def query_expansion_messages(
    material: str,
    reaction: str,
    research_context: dict[str, Any],
    base_queries: list[str],
) -> tuple[str, str]:
    system = (
        "You are a catalysis literature search strategist. Propose additional "
        "open-access search queries that surface papers about catalyst/material "
        "SURFACE structure (facets, Miller indices, terminations, slabs), "
        "activity descriptors, and stability for the target system.\n"
        f"Research context:\n{research_context_block(research_context)}"
    )
    human = (
        f"Material: {material}\nReaction/application: {reaction}\n"
        f"Existing queries:\n" + "\n".join(f"- {q}" for q in base_queries) + "\n\n"
        "Return ONLY a JSON array of up to 6 additional concise query strings "
        "(no duplicates of the existing ones, no commentary)."
    )
    return system, human


def intake_messages(text: str) -> tuple[str, str]:
    system = (
        "You convert a user's free-text request into a catalyst surface-modeling "
        "job. Extract the target material, the target reaction/application, and an "
        "optional research direction.\n"
        "Return STRICT JSON with keys: material (string), reaction (string, e.g. "
        "HER/OER/ORR/CO2RR or a short phrase), prompt (string, the research "
        "direction, or empty). No prose."
    )
    human = f"User request:\n{text}\n\nReturn the JSON now."
    return system, human


def subquestion_messages(
    material: str, reaction: str, research_context: dict[str, Any]
) -> tuple[str, str]:
    system = (
        "You decompose a catalysis research goal into focused sub-questions that "
        "each map to a literature search about a specific surface property "
        "(facet/Miller index, activity, descriptor, stability, selectivity).\n"
        f"Research context:\n{research_context_block(research_context)}"
    )
    human = (
        f"Material: {material}\nReaction/application: {reaction}\n\n"
        "Return ONLY a JSON array of up to 5 concise sub-question strings."
    )
    return system, human


def relevance_grading_messages(
    material: str,
    reaction: str,
    research_context: dict[str, Any],
    papers: list[dict[str, Any]],
    strict: bool = False,
) -> tuple[str, str]:
    import json

    if strict:
        criterion = (
            f"A paper is relevant only if it plausibly contains surface-level "
            f"evidence about {material} for {reaction} (facets, Miller indices, "
            "descriptors, activity, stability, selectivity)."
        )
    else:
        criterion = (
            f"Relevance is MATERIAL-FIRST. A paper is relevant if it concerns "
            f"{material} (or closely related phases/composites/heterostructures/"
            "interfaces) in any surface, electrocatalysis, or water-splitting "
            f"context. The specific reaction need NOT match {reaction}: evidence "
            "about the same material under a different reaction (e.g. OER instead "
            "of HER) still informs its surface modeling, because facet stability, "
            "adsorption descriptors, and surface structure transfer across "
            "reactions. Surface-level details usually appear only in the full "
            "text, so DO NOT require the abstract to mention facets or "
            "descriptors. Strongly prefer recall: include the paper whenever it "
            f"names {material}, and when uncertain. Exclude ONLY papers clearly "
            "about a different material with no role for the target material."
        )
    system = (
        "You filter literature search hits for a catalyst surface-modeling study.\n"
        f"{criterion}\n"
        f"Research context:\n{research_context_block(research_context)}"
    )
    human = (
        "Papers (JSON array of {paper_id, title, abstract}):\n"
        f"{json.dumps(papers, ensure_ascii=False)[:14000]}\n\n"
        "Return ONLY a JSON array of the relevant paper_id strings."
    )
    return system, human


def gap_query_messages(
    material: str,
    reaction: str,
    research_context: dict[str, Any],
    coverage: dict[str, Any],
) -> tuple[str, str]:
    import json

    system = (
        "You turn evidence gaps into targeted open-access literature search "
        "queries for a catalyst surface-modeling study. Each query should aim at "
        "a specific missing property/surface.\n"
        f"Material: {material}\nReaction: {reaction}\n"
        f"Research context:\n{research_context_block(research_context)}"
    )
    human = (
        "Coverage gaps (JSON):\n"
        f"{json.dumps(coverage, ensure_ascii=False)[:8000]}\n\n"
        "Return ONLY a JSON array of up to 6 concise query strings targeting the "
        "gaps (no duplicates, no commentary)."
    )
    return system, human


def extraction_system(material: str, reaction: str, research_context: dict[str, Any]) -> str:
    return (
        "You extract SURFACE-CATALYSIS evidence for computational screening. "
        "Capture how the paper reasons about catalysis: which material/surface, "
        "which reaction, which DESCRIPTOR, which CALCULATION, and what it CLAIMS. "
        "Do NOT restrict to the target material or facet -- a different "
        "metal/surface studied under the same reaction is valuable, because its "
        "descriptor and method transfer to the target's surface modeling. Extract "
        "every distinct, text-grounded claim.\n\n"
        f"Run target (for relating evidence, not for filtering): material="
        f"{material}, reaction={reaction}\n"
        f"Research context:\n{research_context_block(research_context)}\n\n"
        "Output STRICT JSON: an array of objects with keys:\n"
        "- system: the actual catalyst/material the claim is about (e.g. "
        "\"Pt(111)\", \"Ru-RuO2\", \"Co3O4\"); never assume it is the target.\n"
        f"- reaction: one of {', '.join(REACTION_TYPES)} (classify what the claim "
        "studies; \"other\" if unclear).\n"
        "- surface_text: facet/termination/slab if stated (e.g. \"(110)\"), else null.\n"
        f"- descriptor: one of {', '.join(DESCRIPTOR_TYPES)} (the key quantity the "
        "claim hinges on; \"other\" if none fits, null if no descriptor).\n"
        f"- method: one of {', '.join(METHOD_TYPES)} (how it was computed/measured; "
        "\"other\"/null as appropriate).\n"
        "- claim: ONE sentence stating what the paper argues (the structure-activity "
        "or mechanistic point), in your own words.\n"
        "- evidence_text: a verbatim supporting sentence from the text.\n"
        f"- claim_type: one of {', '.join(CLAIM_TYPES)}.\n"
        "- value: numeric string or null; unit: string or null; "
        "section: string or null; confidence: 0-1 float.\n"
        "Only include claims grounded in the text. A claim needs at least a "
        "descriptor, a surface_text, or a substantive claim sentence. Return [] if "
        "none. No prose outside the JSON."
    )


def extraction_human(paper_id: str, title: str, text: str, max_chars: int = 24000) -> str:
    snippet = text[:max_chars]
    return (
        f"paper_id: {paper_id}\ntitle: {title}\n\n"
        f"PAPER TEXT:\n{snippet}\n\n"
        "Extract the surface claims now as a JSON array."
    )


def claim_validation_question(material: str, reaction: str, surface: str, evidence: str) -> str:
    return (
        f"For {material} {surface} in the context of {reaction}: is the following "
        f"claim supported by the indexed papers, and by which citation? "
        f"Claim/evidence: \"{evidence}\". Answer whether it is supported, "
        "contradicted, or unaddressed, and cite the source."
    )


# For prompt caching the large, stable content (research context + the
# opportunity report) lives in the system block so it can sit behind a
# provider cache breakpoint; the variable per-call task goes in the human turn.
def gap_ranking_messages(
    material: str,
    reaction: str,
    research_context: dict[str, Any],
    baseline_report: dict[str, Any],
) -> tuple[str, str]:
    import json

    system = (
        "You are a computational catalysis advisor. Given a rule-based evidence "
        "report over candidate surfaces, refine the prioritization and the "
        "suggested surface-modeling calculations (facet selection, adsorption / "
        "free-energy descriptors, surface stability under reaction conditions, "
        "selectivity-determining intermediates). Respect the research context.\n\n"
        f"Material: {material}\nReaction: {reaction}\n"
        f"Research context:\n{research_context_block(research_context)}\n\n"
        "Baseline report (JSON):\n"
        f"{json.dumps(baseline_report, ensure_ascii=False)[:18000]}"
    )
    human = (
        "Return STRICT JSON with keys: ranked_surfaces (array of "
        "{surface, priority (high|medium|low), rationale}), and "
        "calculation_suggestions (array of {surface, calculation_type, "
        "priority, reason, suggested_next_step}). No prose."
    )
    return system, human


def report_system(
    material: str,
    reaction: str,
    research_context: dict[str, Any],
    opportunity_report: dict[str, Any],
) -> str:
    import json

    return (
        "You are writing a concise, citation-grounded surface-modeling proposal "
        "for a computational catalysis collaborator. Use ONLY the supplied "
        "evidence and validated claims; cite paper ids / DOIs where given. Do not "
        "invent results.\n\n"
        f"Target material: {material}\n"
        f"Target reaction/application: {reaction}\n"
        f"Research context:\n{research_context_block(research_context)}\n\n"
        "Opportunity / gap report (JSON):\n"
        f"{json.dumps(opportunity_report, ensure_ascii=False)[:8000]}"
    )


def report_human(
    validated_claims: list[dict[str, Any]],
    paperqa_findings: list[dict[str, Any]],
) -> str:
    import json

    return (
        "Validated claims (JSON):\n"
        f"{json.dumps(validated_claims, ensure_ascii=False)[:12000]}\n\n"
        "PaperQA findings (JSON):\n"
        f"{json.dumps(paperqa_findings, ensure_ascii=False)[:8000]}\n\n"
        "Each claim carries: system (the catalyst studied, which may differ from "
        "the target), reaction, descriptor, method, and relation_to_target "
        "(both | same_material | same_reaction | analogous). Use claims about "
        "OTHER systems under the same reaction as transferable field evidence.\n\n"
        "Write a Markdown report with these sections:\n"
        "1. Summary of evidence for the target system\n"
        "2. Field landscape: for the target reaction across ALL systems, which "
        "DESCRIPTORS and CALCULATION METHODS are standard and what they argue "
        "(a compact table of system x surface x descriptor x method x claim, "
        "marking each row's relation_to_target); note which transfer to the "
        "target.\n"
        "3. Candidate surfaces/interfaces of the target ranked for modeling "
        "(rationale + citations)\n"
        "4. Recommended calculations (facet, descriptor, method, stability, "
        "selectivity), each justified by the field landscape and the gap it "
        "closes\n"
        "5. Open questions / data gaps\n"
        "Cite paper ids / DOIs. Keep it grounded in the evidence above."
    )
