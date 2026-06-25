from __future__ import annotations

from typing import Any

from paper_search.agent import llm as llm_layer
from paper_search.agent import prompts
from paper_search.agent.nodes._helpers import stage_error
from paper_search.agent.services import AgentServices
from paper_search.agent.state import GraphState
from paper_search.extraction import REACTION_ALIASES
from paper_search.models import Paper

_SURFACE_TERMS = ("surface", "facet", "plane", "miller", "termination", "slab", "(1", "(0")


def _mode(value: Any) -> str:
    """Normalize relevance_filter to strict | lenient | off (accepts legacy bool)."""
    if value is False:
        return "off"
    if value is True:
        return "lenient"
    text = str(value).strip().lower()
    if text in ("off", "none", "false", "no", ""):
        return "off"
    if text == "strict":
        return "strict"
    return "lenient"


def relevance_grading_node(state: GraphState, *, services: AgentServices) -> dict[str, Any]:
    """Drop off-topic papers before download. Lenient by default: topical
    relevance + keep-on-uncertainty (recall over precision), since surface
    details live in the full text, not the abstract. Modes: strict|lenient|off.
    Grades only papers not yet graded (incremental)."""
    mode = _mode(services.config.relevance_filter)
    graded: dict[str, bool] = dict(state.get("graded", {}))
    papers = state.get("papers", [])

    if mode == "off":
        for paper in papers:
            graded.setdefault(paper.paper_id, True)
        return {"graded": graded}

    new_papers = [p for p in papers if p.paper_id not in graded]
    if not new_papers:
        return {"graded": graded}

    harness_errors = list(state.get("harness_errors", []))
    material = state["material"]
    reaction = state["reaction"]
    research_context = state.get("research_context", {})

    verdicts: dict[str, bool] | None = None
    if services.full_mode and services.chat_model is not None:
        try:
            verdicts = _llm_grade(
                services, material, reaction, research_context, new_papers, mode == "strict"
            )
        except Exception as exc:
            harness_errors.append(stage_error("relevance_grading", None, exc))
            # keep-on-failure: don't silently drop papers on a grading error
            verdicts = {p.paper_id: True for p in new_papers}
    if verdicts is None:
        verdicts = {p.paper_id: _rule_relevant(p, material, reaction, mode) for p in new_papers}

    strict = mode == "strict"
    field_on = _field_scope_on(getattr(services.config, "field_scope", "off"))
    for paper in new_papers:
        verdict = verdicts.get(paper.paper_id, True)
        if not strict and not verdict:
            # Recall floor (lenient only): never drop a clear target-material
            # match, whatever the LLM says. Surface/descriptor/stability evidence
            # about the same material transfers across reactions -- a RuO2 OER
            # surface paper still informs RuO2 HER surface modeling -- and the
            # detail lives in the full text, not the abstract. This guards the
            # false-negative that was silently dropping accessible Elsevier RuO2
            # papers before download.
            if _material_present(paper, material):
                verdict = True
            # Field floor (Tier B): when field_scope is on, also keep same-reaction
            # papers on OTHER systems that carry a surface/descriptor signal --
            # their descriptor/method evidence transfers to the target.
            elif field_on and _field_relevant(paper, reaction):
                verdict = True
        graded[paper.paper_id] = verdict
    return {"graded": graded, "harness_errors": harness_errors}


_FIELD_SIGNALS = _SURFACE_TERMS + (
    "descriptor", "adsorption", "free energy", "d-band", "overpotential",
    "dft", "first-principles", "electrocatal", "binding energy", "volcano",
)


def _field_scope_on(field_scope: Any) -> bool:
    return str(field_scope or "off").strip().lower() not in ("off", "none", "", "false")


def _field_relevant(paper: Paper, reaction: str) -> bool:
    """Same-reaction field paper with a surface/descriptor signal (Tier B keep)."""
    text = f"{paper.title or ''} {paper.abstract or ''}".lower()
    reaction_terms = [t.lower() for t in REACTION_ALIASES.get(reaction.upper(), [reaction])]
    if not any(t in text for t in reaction_terms):
        return False
    return any(s in text for s in _FIELD_SIGNALS)


def _material_present(paper: Paper, material: str) -> bool:
    text = f"{paper.title or ''} {paper.abstract or ''}".lower()
    compact = material.replace(" ", "").lower()
    return any(t and t in text for t in {material.lower(), compact})


def _rule_relevant(paper: Paper, material: str, reaction: str, mode: str) -> bool:
    text = f"{paper.title or ''} {paper.abstract or ''}".lower()
    material_present = _material_present(paper, material)
    reaction_terms = [t.lower() for t in REACTION_ALIASES.get(reaction.upper(), [reaction])]
    reaction_present = any(t in text for t in reaction_terms)
    surface_present = any(t in text for t in _SURFACE_TERMS)

    if mode == "strict":
        if not material_present:
            return False
        if reaction_present or surface_present:
            return True
        return not bool(paper.abstract)

    # lenient: keep if on-topic; keep when we cannot judge (no abstract).
    if material_present or reaction_present:
        return True
    return not bool(paper.abstract)


def _llm_grade(
    services: AgentServices,
    material: str,
    reaction: str,
    research_context: dict[str, Any],
    papers: list[Paper],
    strict: bool,
) -> dict[str, bool]:
    payload = [
        {"paper_id": p.paper_id, "title": p.title, "abstract": (p.abstract or "")[:600]}
        for p in papers
    ]
    system, human = prompts.relevance_grading_messages(
        material, reaction, research_context, payload, strict=strict
    )
    messages = llm_layer.build_messages(
        system_context=system,
        human_prompt=human,
        provider=services.provider,
        prompt_cache=services.config.llm.cache.prompt_cache,
    )
    response = services.chat_model.invoke(messages)
    parsed = llm_layer.parse_json_response(llm_layer.message_text(response))
    relevant_ids = {str(x) for x in parsed} if isinstance(parsed, list) else set()
    return {p.paper_id: (p.paper_id in relevant_ids) for p in papers}
