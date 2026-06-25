from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from paper_search.agent import llm as llm_layer
from paper_search.agent import prompts
from paper_search.agent.nodes._helpers import research_context_dict, stage_error
from paper_search.agent.services import AgentServices
from paper_search.agent.state import GraphState
from paper_search.utils import write_json


def report_writer_node(state: GraphState, *, services: AgentServices) -> dict[str, Any]:
    config = services.config
    material = state["material"]
    reaction = state["reaction"]
    papers = state.get("papers", [])
    claims = state.get("claims", [])
    processed = state.get("processed", [])
    queries = state.get("queries", [])
    search_errors = state.get("search_errors", [])
    resume_events = state.get("resume_events", [])
    harness_errors = list(state.get("harness_errors", []))
    opportunity_report = state.get("opportunity_report", {})
    validated_claims = state.get("validated_claims", [])

    report_markdown: str | None = None
    if services.full_mode and services.chat_model is not None:
        try:
            report_markdown = _write_report(
                services, state, validated_claims, opportunity_report
            )
            (config.output_dir / "report.md").write_text(
                report_markdown, encoding="utf-8"
            )
        except Exception as exc:
            harness_errors.append(stage_error("report_writer", None, exc))

    result = {
        "material": material,
        "reaction": reaction,
        "research_context": research_context_dict(config.research),
        "mode": "full" if services.full_mode else "deterministic",
        "provider": services.provider if services.full_mode else "none",
        "rounds": state.get("round", 1),
        "coverage": state.get("coverage", {}),
        "queries": queries,
        "search_errors": search_errors,
        "paper_count": len(papers),
        "processed": processed,
        "surface_claim_count": len(claims),
        "surface_claims": [claim.to_dict() for claim in claims],
        "validated_claims": validated_claims,
        "opportunity_report": opportunity_report,
        "report_markdown": report_markdown,
        "harness": {
            "resume": config.resume,
            "resume_events": resume_events,
            "http_retry": {
                "events": services.http.retry_events,
                "event_count": len(services.http.retry_events),
            },
            "errors": harness_errors,
            "error_count": len(harness_errors),
        },
    }

    write_json(config.output_dir / "run_manifest.json", result)
    write_json(
        config.output_dir / "surface_claims.json",
        [claim.to_dict() for claim in claims],
    )
    answer = report_markdown or _chat_summary(result)
    return {
        "result": result,
        "report_markdown": report_markdown,
        "messages": [AIMessage(content=answer)],
        "harness_errors": harness_errors,
    }


def _chat_summary(result: dict[str, Any]) -> str:
    """Plain-text answer for the chat transcript (deterministic / no report.md)."""
    report = result.get("opportunity_report", {})
    surfaces = report.get("candidate_surfaces", []) or []
    lines = [
        f"{result['material']} / {result['reaction']} — {result.get('mode', 'deterministic')} "
        f"run over {result['paper_count']} papers across {result.get('rounds', 1)} round(s).",
        f"Extracted {result['surface_claim_count']} surface claims on "
        f"{len(surfaces)} candidate surface(s).",
    ]
    top = [s.get("surface") for s in surfaces[:5] if s.get("surface")]
    if top:
        lines.append("Top candidate surfaces: " + ", ".join(top) + ".")
    suggestions = report.get("calculation_suggestions", []) or []
    if suggestions:
        lines.append(f"{len(suggestions)} calculation suggestion(s) proposed.")
    gaps = report.get("run_level_gaps", []) or []
    if gaps:
        lines.append("Run-level gaps: " + ", ".join(g.get("gap_type", "") for g in gaps) + ".")
    lines.append("See run_manifest.json and opportunity_report.json for details.")
    return "\n".join(lines)


def _write_report(
    services: AgentServices,
    state: GraphState,
    validated_claims: list[dict[str, Any]],
    opportunity_report: dict[str, Any],
) -> str:
    material = state["material"]
    reaction = state["reaction"]
    research_context = state.get("research_context", {})

    paperqa_findings = [
        {
            "system": claim.get("system"),
            "surface": claim.get("surface_text"),
            "reaction": claim.get("reaction"),
            "descriptor": claim.get("descriptor"),
            "method": claim.get("method"),
            "relation_to_target": claim.get("relation_to_target"),
            "claim_type": claim.get("claim_type"),
            "answer": (claim.get("validation") or {}).get("answer"),
        }
        for claim in validated_claims
        if claim.get("validation")
    ]

    system = prompts.report_system(
        material, reaction, research_context, opportunity_report
    )
    human = prompts.report_human(validated_claims, paperqa_findings)
    messages = llm_layer.build_messages(
        system_context=system,
        human_prompt=human,
        provider=services.provider,
        prompt_cache=services.config.llm.cache.prompt_cache,
    )
    response = services.chat_model.invoke(messages)
    return llm_layer.message_text(response).strip()
