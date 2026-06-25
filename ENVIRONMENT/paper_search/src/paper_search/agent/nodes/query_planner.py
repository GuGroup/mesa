from __future__ import annotations

from typing import Any

from paper_search.agent import llm as llm_layer
from paper_search.agent import prompts
from paper_search.agent.nodes._helpers import stage_error
from paper_search.agent.services import AgentServices
from paper_search.agent.state import GraphState
from paper_search.planner import build_queries


def query_planner_node(state: GraphState, *, services: AgentServices) -> dict[str, Any]:
    material = state["material"]
    reaction = state["reaction"]
    extra_terms = state.get("extra_terms") or []
    research_context = state.get("research_context", {})
    harness_errors = list(state.get("harness_errors", []))
    seen_queries = state.get("seen_queries", [])
    sub_questions = list(state.get("sub_questions", []))
    round_no = state.get("round", 0) + 1

    if round_no == 1:
        queries = build_queries(
            material,
            reaction,
            extra_terms,
            research=services.config.research,
            field_scope=services.config.field_scope,
        )
        if services.full_mode and services.chat_model is not None:
            try:
                extra = _expand_queries(
                    services, material, reaction, research_context, queries
                )
                queries.extend(extra)
            except Exception as exc:
                harness_errors.append(stage_error("query_expansion", None, exc))
            try:
                sub_questions = _decompose(services, material, reaction, research_context)
                queries.extend(sub_questions)
            except Exception as exc:
                harness_errors.append(stage_error("subquestion_decomposition", None, exc))
    else:
        # Later rounds run only the gap-targeted queries from gap_ranking.
        queries = list(state.get("gap_queries", []))

    # Drop queries already issued in earlier rounds.
    seen_lower = {q.lower() for q in seen_queries}
    new_queries: list[str] = []
    for query in queries:
        key = query.lower()
        if query and key not in seen_lower:
            new_queries.append(query)
            seen_lower.add(key)

    return {
        "queries": new_queries,
        "round": round_no,
        "sub_questions": sub_questions,
        "harness_errors": harness_errors,
    }


def _expand_queries(
    services: AgentServices,
    material: str,
    reaction: str,
    research_context: dict[str, Any],
    base_queries: list[str],
) -> list[str]:
    system, human = prompts.query_expansion_messages(
        material, reaction, research_context, base_queries
    )
    return _ask_for_list(services, system, human)


def _decompose(
    services: AgentServices,
    material: str,
    reaction: str,
    research_context: dict[str, Any],
) -> list[str]:
    system, human = prompts.subquestion_messages(material, reaction, research_context)
    return _ask_for_list(services, system, human)


def _ask_for_list(services: AgentServices, system: str, human: str) -> list[str]:
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
