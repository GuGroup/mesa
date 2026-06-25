from __future__ import annotations

import uuid
from typing import Any, Callable, Iterator

from langgraph.graph import END, START, StateGraph

from paper_search.agent import nodes
from paper_search.agent.nodes._helpers import research_context_dict
from paper_search.agent.services import AgentServices
from paper_search.agent.state import GraphState
from paper_search.config import PipelineConfig

# Dataclasses carried in checkpointed state, registered so the serializer does
# not warn / block on them.
_ALLOWED_STATE_MODULES = [
    ("paper_search.models", "Paper"),
    ("paper_search.models", "SurfaceClaim"),
]

# Linear stage sequence. LLM/PaperQA nodes self-gate on services.full_mode, so
# the same wiring serves deterministic and full agent runs.
NODE_SEQUENCE: list[tuple[str, Callable[..., dict[str, Any]]]] = [
    ("intake", nodes.intake_node),
    ("query_planner", nodes.query_planner_node),
    ("search", nodes.search_node),
    ("relevance_grading", nodes.relevance_grading_node),
    ("resolve_download", nodes.resolve_download_node),
    ("parse", nodes.parse_node),
    ("paperqa_index", nodes.paperqa_index_node),
    ("evidence_extraction", nodes.evidence_extraction_node),
    ("claim_validation", nodes.claim_validation_node),
    ("gap_ranking", nodes.gap_ranking_node),
    ("report_writer", nodes.report_writer_node),
]


def _bind(fn: Callable[..., dict[str, Any]], services: AgentServices) -> Callable[[GraphState], dict[str, Any]]:
    # Single-positional-arg wrapper so LangGraph does not try to inject a config.
    def bound(state: GraphState) -> dict[str, Any]:
        return fn(state, services=services)

    return bound


def _route_after_gap(services: AgentServices) -> Callable[[GraphState], str]:
    """Continue the gap-driven loop, or finish, based on coverage + budget."""

    def route(state: GraphState) -> str:
        config = services.config
        round_no = state.get("round", 1)
        coverage = state.get("coverage", {})
        if (
            round_no < config.max_search_rounds
            and coverage.get("has_gaps")
            and state.get("new_papers_last_round", 0) >= config.min_new_papers_to_continue
            and state.get("gap_queries")
        ):
            return "query_planner"
        return "report_writer"

    return route


class CatalystLiteratureGraph:
    """Catalyst surface-modeling literature agent built on LangGraph.

    Orchestrates the existing deterministic retrieval/parsing stages plus
    LLM/PaperQA reasoning into a single ``StateGraph``.
    """

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def build(self, services: AgentServices, checkpointer: Any = None) -> Any:
        builder = StateGraph(GraphState)
        names = [name for name, _ in NODE_SEQUENCE]
        for name, fn in NODE_SEQUENCE:
            builder.add_node(name, _bind(fn, services))
        builder.add_edge(START, names[0])
        # Linear chain up to gap_ranking; the gap_ranking -> ? hop is conditional.
        for prev, curr in zip(names, names[1:]):
            if prev == "gap_ranking":
                continue
            builder.add_edge(prev, curr)
        builder.add_conditional_edges(
            "gap_ranking",
            _route_after_gap(services),
            {"query_planner": "query_planner", "report_writer": "report_writer"},
        )
        builder.add_edge("report_writer", END)
        return builder.compile(checkpointer=checkpointer)

    def _invoke_config(self, checkpointer: Any) -> dict[str, Any]:
        # Bound the cyclic graph so a runaway loop raises instead of hanging.
        config: dict[str, Any] = {
            "recursion_limit": self.config.max_search_rounds * 12 + 12
        }
        if checkpointer is not None:
            config["configurable"] = {"thread_id": uuid.uuid4().hex}
        return config

    def _make_checkpointer(self) -> Any:
        if not self.config.checkpoint:
            return None
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

        serde = JsonPlusSerializer(
            pickle_fallback=True,
            allowed_msgpack_modules=_ALLOWED_STATE_MODULES,
        )
        return MemorySaver(serde=serde)

    def _initial_state(
        self, services: AgentServices, material: str, reaction: str,
        extra_terms: list[str] | None,
    ) -> GraphState:
        return {
            "material": material,
            "reaction": reaction,
            "extra_terms": extra_terms or [],
            "research_context": research_context_dict(self.config.research),
            "full_mode": services.full_mode,
            "harness_errors": [],
            "resume_events": [],
        }

    def run(
        self,
        material: str,
        reaction: str,
        extra_terms: list[str] | None = None,
        on_node: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        with AgentServices.create(self.config) as services:
            checkpointer = self._make_checkpointer()
            graph = self.build(services, checkpointer=checkpointer)
            initial = self._initial_state(services, material, reaction, extra_terms)
            invoke_config = self._invoke_config(checkpointer)
            if on_node is None:
                final = graph.invoke(initial, config=invoke_config)
                return final["result"]
            # Stream node-by-node so a long run reports progress instead of going
            # silent. The report_writer node carries the final result payload.
            result: dict[str, Any] | None = None
            for update in graph.stream(
                initial, config=invoke_config, stream_mode="updates"
            ):
                for node_name, delta in update.items():
                    on_node(node_name, delta if isinstance(delta, dict) else {})
                    if isinstance(delta, dict) and "result" in delta:
                        result = delta["result"]
            if result is None:
                raise RuntimeError("graph finished without producing a result")
            return result

    def stream(
        self,
        material: str,
        reaction: str,
        extra_terms: list[str] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield per-node state updates as the graph runs (for progress/UX)."""
        with AgentServices.create(self.config) as services:
            checkpointer = self._make_checkpointer()
            graph = self.build(services, checkpointer=checkpointer)
            initial = self._initial_state(services, material, reaction, extra_terms)
            yield from graph.stream(
                initial, config=self._invoke_config(checkpointer), stream_mode="updates"
            )
