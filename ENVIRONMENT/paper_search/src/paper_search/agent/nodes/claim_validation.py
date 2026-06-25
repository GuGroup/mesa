from __future__ import annotations

from typing import Any

from paper_search.agent import prompts
from paper_search.agent.nodes._helpers import stage_error
from paper_search.agent.services import AgentServices
from paper_search.agent.state import GraphState


def claim_validation_node(state: GraphState, *, services: AgentServices) -> dict[str, Any]:
    """Validate claims against the PaperQA index, incrementally and per surface.

    Only surfaces not yet validated are queried (deduped, capped cumulatively by
    ``paperqa.validation_max_queries``). In full mode with ``paperqa.agentic`` it
    uses PaperQA's agent (``agent_query``), falling back to a single ``aquery``
    pass on error.
    """
    claims = state.get("claims", [])
    index_path = state.get("paperqa_index_path")
    material = state["material"]
    reaction = state["reaction"]
    harness_errors = list(state.get("harness_errors", []))
    validated_surfaces = list(state.get("validated_surfaces", []))
    surface_validations: dict[str, Any] = dict(state.get("surface_validations", {}))

    def _rebuild() -> list[dict[str, Any]]:
        return [
            {**c.to_dict(), "validation": surface_validations.get(c.surface_text)}
            for c in claims
        ]

    if not services.full_mode or not index_path or not claims:
        return {"validated_claims": _rebuild()}

    # Unique not-yet-validated surfaces, first-seen order, with a representative.
    representative: dict[str, Any] = {}
    for claim in claims:
        if claim.surface_text in surface_validations:
            continue
        representative.setdefault(claim.surface_text, claim)
    budget = max(
        services.config.paperqa.validation_max_queries - len(validated_surfaces), 0
    )
    todo = list(representative)[:budget]
    if not todo:
        return {"validated_claims": _rebuild()}

    try:
        from pathlib import Path

        from paper_search.agent import paperqa_index as pq

        settings = pq.build_settings(
            services.config.llm,
            services.config.paperqa,
            work_dir=Path(index_path).parent,
        )
        docs = pq.load_docs(index_path)
        questions = {
            surface: prompts.claim_validation_question(
                material, reaction, surface, representative[surface].evidence_text
            )
            for surface in todo
        }

        if services.config.paperqa.agentic:
            for surface, question in questions.items():
                surface_validations[surface] = _agent_or_single(
                    pq, docs, question, settings, harness_errors
                )
                validated_surfaces.append(surface)
        else:
            results = pq.ask_many(docs, list(questions.values()), settings)
            for surface, result in zip(questions.keys(), results):
                surface_validations[surface] = result
                validated_surfaces.append(surface)
    except Exception as exc:
        harness_errors.append(stage_error("claim_validation", None, exc))

    return {
        "validated_claims": _rebuild(),
        "validated_surfaces": validated_surfaces,
        "surface_validations": surface_validations,
        "harness_errors": harness_errors,
    }


def _agent_or_single(pq, docs, question, settings, harness_errors) -> Any:
    try:
        return pq.agent_ask(docs, question, settings)
    except Exception:
        try:
            return pq.ask(docs, question, settings)
        except Exception as exc:
            harness_errors.append(stage_error("claim_validation", None, exc))
            return None
