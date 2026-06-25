from __future__ import annotations

import re
from typing import Any

from paper_search.agent import llm as llm_layer
from paper_search.agent import prompts
from paper_search.agent.nodes._helpers import stage_error
from paper_search.agent.services import AgentServices
from paper_search.agent.state import GraphState
from paper_search.extraction import REACTION_ALIASES

_REACTIONS = sorted(REACTION_ALIASES, key=len, reverse=True)


def intake_node(state: GraphState, *, services: AgentServices) -> dict[str, Any]:
    """Parse material/reaction from the latest chat message (Agent Chat UI path).

    No-op when material/reaction are already provided (CLI path). LLM-parsed in
    full mode, heuristic in deterministic mode.
    """
    if state.get("material") and state.get("reaction"):
        return {}

    text = _last_human_text(state.get("messages", []))
    if not text:
        return {}

    harness_errors = list(state.get("harness_errors", []))
    parsed: dict[str, str] = {}
    if services.full_mode and services.chat_model is not None:
        try:
            parsed = _llm_parse(services, text)
        except Exception as exc:
            harness_errors.append(stage_error("intake", None, exc))
    if not parsed.get("material") or not parsed.get("reaction"):
        parsed = {**_rule_parse(text), **{k: v for k, v in parsed.items() if v}}

    out: dict[str, Any] = {}
    if parsed.get("material"):
        out["material"] = parsed["material"]
    if parsed.get("reaction"):
        out["reaction"] = parsed["reaction"]
    if parsed.get("prompt"):
        research_context = dict(state.get("research_context", {}))
        research_context.setdefault("prompt", parsed["prompt"])
        out["research_context"] = research_context
    if harness_errors:
        out["harness_errors"] = harness_errors
    return out


def _last_human_text(messages: list[Any]) -> str:
    for message in reversed(messages or []):
        role = getattr(message, "type", None) or (
            message.get("role") if isinstance(message, dict) else None
        )
        if role in ("human", "user"):
            content = getattr(message, "content", None)
            if content is None and isinstance(message, dict):
                content = message.get("content")
            return llm_layer.message_text(message) if content is None else _as_text(content)
    # Fall back to the last message of any role.
    if messages:
        last = messages[-1]
        content = getattr(last, "content", None)
        if content is None and isinstance(last, dict):
            content = last.get("content")
        return _as_text(content) if content is not None else ""
    return ""


def _as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content)


def _rule_parse(text: str) -> dict[str, str]:
    upper = text.upper()
    reaction = ""
    for alias in _REACTIONS:
        if re.search(rf"\b{re.escape(alias)}\b", upper):
            reaction = alias
            break
    # Material guess: a token with a digit/capital pattern (e.g. RuO2, Pt3Ni) or
    # the first capitalized word that is not the reaction acronym.
    material = ""
    for token in re.findall(r"[A-Za-z][A-Za-z0-9()]+", text):
        if reaction and token.upper() == reaction:
            continue
        if re.search(r"[A-Z].*\d", token) or re.match(r"[A-Z][a-z]", token):
            material = token
            break
    return {"material": material, "reaction": reaction or text.strip()[:40], "prompt": text.strip()}


def _llm_parse(services: AgentServices, text: str) -> dict[str, str]:
    system, human = prompts.intake_messages(text)
    messages = llm_layer.build_messages(
        system_context=system,
        human_prompt=human,
        provider=services.provider,
        prompt_cache=services.config.llm.cache.prompt_cache,
    )
    response = services.chat_model.invoke(messages)
    parsed = llm_layer.parse_json_response(llm_layer.message_text(response))
    if isinstance(parsed, dict):
        return {
            "material": str(parsed.get("material") or "").strip(),
            "reaction": str(parsed.get("reaction") or "").strip(),
            "prompt": str(parsed.get("prompt") or "").strip(),
        }
    return {}
