from __future__ import annotations

from typing import Any

from paper_search.agent import llm as llm_layer
from paper_search.agent import prompts
from paper_search.agent.nodes._helpers import stage_error
from paper_search.agent.services import AgentServices
from paper_search.agent.state import GraphState
from paper_search.opportunities import _desired_claim_types, build_opportunity_report
from paper_search.utils import write_json

# Claim type -> extra search terms used to build gap-targeted queries.
_TYPE_TERMS = {
    "descriptor": "adsorption free energy binding energy descriptor",
    "activity": "overpotential activity current density",
    "stability": "stability dissolution durability",
    "selectivity": "selectivity faradaic efficiency pathway",
}
_MAX_GAP_QUERIES = 6


def gap_ranking_node(state: GraphState, *, services: AgentServices) -> dict[str, Any]:
    config = services.config
    claims = state.get("claims", [])
    material = state["material"]
    reaction = state["reaction"]
    research_context = state.get("research_context", {})
    harness_errors = list(state.get("harness_errors", []))
    seen_queries = {q.lower() for q in state.get("seen_queries", [])}

    try:
        report = build_opportunity_report(
            claims=claims, material=material, reaction=reaction, research=config.research
        )
    except Exception as exc:
        report = {"status": "failed", "error": str(exc)}
        harness_errors.append(stage_error("opportunity_report", None, exc))

    coverage = _coverage(report, reaction, config.research)

    if (
        services.full_mode
        and services.chat_model is not None
        and report.get("status") != "failed"
    ):
        try:
            ranking = _llm_rank(services, material, reaction, research_context, report)
            if ranking:
                report["llm_ranking"] = ranking
        except Exception as exc:
            harness_errors.append(stage_error("gap_ranking_llm", None, exc))

    gap_queries = _gap_queries(
        services, material, reaction, research_context, coverage, seen_queries
    )

    write_json(config.output_dir / "opportunity_report.json", report)
    return {
        "opportunity_report": report,
        "coverage": coverage,
        "gap_queries": gap_queries,
        "harness_errors": harness_errors,
    }


def _coverage(report: dict[str, Any], reaction: str, research: Any) -> dict[str, Any]:
    if report.get("status") == "failed":
        return {"has_gaps": True, "missing_global_types": [], "surfaces_needing": []}
    desired = _desired_claim_types(reaction, research)
    present = set(report.get("claim_type_coverage", {}))
    missing_global = [t for t in desired if t not in present]
    surfaces_needing = []
    for surface in report.get("candidate_surfaces", []):
        missing = surface.get("missing_claim_types") or []
        if missing or surface.get("status") == "surface_mention_only":
            surfaces_needing.append(
                {
                    "surface": surface.get("surface"),
                    "missing": missing,
                    "status": surface.get("status"),
                }
            )
    run_gaps = report.get("run_level_gaps") or []
    has_gaps = bool(missing_global or surfaces_needing or run_gaps)
    return {
        "has_gaps": has_gaps,
        "desired_types": desired,
        "missing_global_types": missing_global,
        "surfaces_needing": surfaces_needing,
        "run_level_gaps": run_gaps,
    }


def _gap_queries(
    services: AgentServices,
    material: str,
    reaction: str,
    research_context: dict[str, Any],
    coverage: dict[str, Any],
    seen_lower: set[str],
) -> list[str]:
    if not coverage.get("has_gaps"):
        return []

    candidates: list[str] = []
    if services.full_mode and services.chat_model is not None:
        try:
            candidates = _llm_gap_queries(services, material, reaction, research_context, coverage)
        except Exception:
            candidates = []
    if not candidates:
        candidates = _rule_gap_queries(material, reaction, coverage)

    out: list[str] = []
    for query in candidates:
        key = query.lower()
        if query and key not in seen_lower and key not in {q.lower() for q in out}:
            out.append(query)
        if len(out) >= _MAX_GAP_QUERIES:
            break
    return out


def _rule_gap_queries(material: str, reaction: str, coverage: dict[str, Any]) -> list[str]:
    queries: list[str] = []
    for surface in coverage.get("surfaces_needing", [])[:3]:
        s = surface.get("surface") or ""
        for claim_type in (surface.get("missing") or ["activity", "descriptor"])[:2]:
            terms = _TYPE_TERMS.get(claim_type, claim_type)
            queries.append(f"{material} {reaction} {s} {terms}".strip())
    for claim_type in coverage.get("missing_global_types", []):
        queries.append(f"{material} {reaction} {_TYPE_TERMS.get(claim_type, claim_type)}")
    if not queries:  # no surfaces/claims yet -> broaden
        queries = [
            f"{material} {reaction} surface facet activity",
            f"{material} {reaction} DFT adsorption free energy",
            f"{material} {reaction} surface stability",
        ]
    return queries


def _llm_gap_queries(
    services: AgentServices,
    material: str,
    reaction: str,
    research_context: dict[str, Any],
    coverage: dict[str, Any],
) -> list[str]:
    system, human = prompts.gap_query_messages(material, reaction, research_context, coverage)
    messages = llm_layer.build_messages(
        system_context=system,
        human_prompt=human,
        provider=services.provider,
        prompt_cache=services.config.llm.cache.prompt_cache,
    )
    response = services.chat_model.invoke(messages)
    parsed = llm_layer.parse_json_response(llm_layer.message_text(response))
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return []


def _llm_rank(
    services: AgentServices,
    material: str,
    reaction: str,
    research_context: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any] | None:
    system, human = prompts.gap_ranking_messages(material, reaction, research_context, report)
    messages = llm_layer.build_messages(
        system_context=system,
        human_prompt=human,
        provider=services.provider,
        prompt_cache=services.config.llm.cache.prompt_cache,
    )
    response = services.chat_model.invoke(messages)
    parsed = llm_layer.parse_json_response(llm_layer.message_text(response))
    return parsed if isinstance(parsed, dict) else None
