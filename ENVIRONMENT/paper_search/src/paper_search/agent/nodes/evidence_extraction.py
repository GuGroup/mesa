from __future__ import annotations

from typing import Any

from paper_search.agent import llm as llm_layer
from paper_search.agent import prompts
from paper_search.agent.nodes._helpers import append_stage_error, papers_by_id
from paper_search.agent.services import AgentServices
from paper_search.agent.state import GraphState
from paper_search.extraction import extract_surface_claims
from paper_search.models import Paper, SurfaceClaim
from paper_search.utils import write_json


def evidence_extraction_node(state: GraphState, *, services: AgentServices) -> dict[str, Any]:
    config = services.config
    processed = state.get("processed", [])
    blocks_paths = state.get("blocks_paths", {})
    parsed_texts = state.get("parsed_texts", {})
    harness_errors = list(state.get("harness_errors", []))
    resume_events = list(state.get("resume_events", []))
    by_id = papers_by_id(state.get("papers", []))
    material = state["material"]
    reaction = state["reaction"]
    research_context = state.get("research_context", {})

    all_claims: list[SurfaceClaim] = list(state.get("claims", []))

    for record in processed:
        if record["status"] != "parsed":
            continue
        paper = by_id[record["paper"]["paper_id"]]

        cached_claims = None
        if config.resume:
            try:
                cached_claims = services.cache.read_surface_claims(paper)
            except Exception as exc:
                append_stage_error(record, harness_errors, "resume_extract", paper, exc)
        if cached_claims is not None:
            claims = cached_claims
            resume_events.append(
                {
                    "stage": "extract",
                    "paper_id": paper.paper_id,
                    "status": "reused_surface_claims",
                }
            )
        else:
            try:
                claims = _extract(
                    services,
                    paper,
                    blocks_paths.get(paper.paper_id),
                    parsed_texts.get(paper.paper_id),
                    material,
                    reaction,
                    research_context,
                )
            except Exception as exc:
                append_stage_error(record, harness_errors, "extract", paper, exc)
                record["status"] = "extract_error"
                continue

        all_claims.extend(claims)
        record["claim_count"] = len(claims)
        record["status"] = "ok"

    return {
        "processed": processed,
        "claims": all_claims,
        "harness_errors": harness_errors,
        "resume_events": resume_events,
    }


def _extract(
    services: AgentServices,
    paper: Paper,
    blocks_path: str | None,
    text: str | None,
    material: str,
    reaction: str,
    research_context: dict[str, Any],
) -> list[SurfaceClaim]:
    output_dir = services.cache.extraction_dir(paper)

    if services.full_mode and services.chat_model is not None and text:
        try:
            claims = _llm_extract(
                services, paper, text, material, reaction, research_context
            )
            if claims:
                output_dir.mkdir(parents=True, exist_ok=True)
                write_json(
                    output_dir / "surface_claims.json",
                    [claim.to_dict() for claim in claims],
                )
                return claims
        except Exception:
            # Fall through to the deterministic rule extractor below.
            pass

    if blocks_path:
        from pathlib import Path

        return extract_surface_claims(
            blocks_path=Path(blocks_path),
            material=material,
            reaction=reaction,
            output_dir=output_dir,
        )
    return []


def _llm_extract(
    services: AgentServices,
    paper: Paper,
    text: str,
    material: str,
    reaction: str,
    research_context: dict[str, Any],
) -> list[SurfaceClaim]:
    system = prompts.extraction_system(material, reaction, research_context)
    human = prompts.extraction_human(paper.paper_id, paper.title, text)
    messages = llm_layer.build_messages(
        system_context=system,
        human_prompt=human,
        provider=services.provider,
        prompt_cache=services.config.llm.cache.prompt_cache,
    )
    response = services.chat_model.invoke(messages)
    parsed = llm_layer.parse_json_response(llm_layer.message_text(response))
    if not isinstance(parsed, list):
        return []

    claims: list[SurfaceClaim] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        surface_text = str(item.get("surface_text") or "").strip()
        evidence_text = str(item.get("evidence_text") or "").strip()
        descriptor = _enum(item.get("descriptor"), prompts.DESCRIPTOR_TYPES)
        claim_sentence = _optional_str(item.get("claim"))
        # A claim needs evidence plus at least one anchor (facet, descriptor, or a
        # substantive claim sentence) -- field-level claims often have no facet.
        if not evidence_text or not (surface_text or descriptor or claim_sentence):
            continue
        claim_type = str(item.get("claim_type") or "surface_mention").strip()
        if claim_type not in prompts.CLAIM_TYPES:
            claim_type = "surface_mention"
        system = _optional_str(item.get("system")) or material
        claim_reaction = _enum(
            item.get("reaction"), prompts.REACTION_TYPES, default=reaction.upper()
        )
        claims.append(
            SurfaceClaim(
                paper_id=paper.paper_id,
                material=material,
                reaction=reaction,
                surface_text=surface_text,
                evidence_text=evidence_text,
                claim_type=claim_type,
                section=_optional_str(item.get("section")),
                figure_or_table=_optional_str(item.get("figure_or_table")),
                confidence=_confidence(item.get("confidence")),
                value=_optional_str(item.get("value")),
                unit=_optional_str(item.get("unit")),
                system=system,
                descriptor=descriptor,
                method=_enum(item.get("method"), prompts.METHOD_TYPES),
                claim=claim_sentence,
                relation_to_target=_relation_to_target(
                    system, claim_reaction, material, reaction
                ),
            )
        )
    return claims


def _enum(value: Any, allowed: tuple[str, ...], default: str | None = None) -> str | None:
    """Map a free-text value onto a controlled vocabulary, else 'other'/default."""
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    lookup = {a.lower(): a for a in allowed}
    if text.lower() in lookup:
        return lookup[text.lower()]
    return "other" if "other" in allowed else default


def _relation_to_target(
    system: str, claim_reaction: str | None, material: str, reaction: str
) -> str:
    """Tag how a claim relates to the run target so the report can separate
    target-specific evidence from transferable field evidence."""
    compact = material.replace(" ", "").lower()
    same_material = compact in (system or "").replace(" ", "").lower()
    same_reaction = bool(claim_reaction) and claim_reaction.upper() == reaction.upper()
    if same_material and same_reaction:
        return "both"
    if same_material:
        return "same_material"
    if same_reaction:
        return "same_reaction"
    return "analogous"


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _confidence(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.6
    return max(0.0, min(score, 1.0))
