from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages

from paper_search.models import Paper, SurfaceClaim


class GraphState(TypedDict, total=False):
    """Shared state passed between LangGraph nodes.

    Collections that several nodes append to (``processed``, ``harness_errors``,
    ``resume_events``) use read-modify-write: each node reads the current value
    from state and returns the full updated list, so the default overwrite merge
    is correct without custom reducers.
    """

    # Chat transcript (Agent Chat UI / LangGraph). intake parses material/reaction
    # from the latest human message; report_writer appends the answer.
    messages: Annotated[list, add_messages]

    # Inputs / run context
    material: str
    reaction: str
    extra_terms: list[str]
    research_context: dict[str, Any]
    full_mode: bool

    # Loop bookkeeping (gap-driven re-search)
    round: int  # 1-indexed count of search rounds entered
    rounds: int  # total rounds run (mirrored into the manifest)
    sub_questions: list[str]
    gap_queries: list[str]  # gap-targeted queries for the next round
    seen_queries: list[str]  # queries already issued (dedup across rounds)
    seen_paper_ids: list[str]  # papers already discovered
    graded: dict[str, bool]  # paper_id -> relevant?
    indexed_paper_ids: list[str]  # papers already in the PaperQA index
    validated_surfaces: list[str]  # surfaces already validated
    surface_validations: dict[str, Any]  # surface -> PaperQA validation result
    coverage: dict[str, Any]  # gap summary from gap_ranking
    new_papers_last_round: int

    # Stage outputs
    queries: list[str]
    papers: list[Paper]
    search_errors: list[dict[str, str]]
    resume_events: list[dict[str, Any]]
    harness_errors: list[dict[str, str]]
    processed: list[dict[str, Any]]
    # Transient side-maps keyed by paper_id, passed between stage nodes.
    # Kept JSON-serializable so the graph can run under a checkpointer.
    downloaded_sources: dict[str, dict[str, Any]]  # paper_id -> DownloadedSource dict
    blocks_paths: dict[str, str]  # paper_id -> best blocks json path
    # paper_id -> concatenated parsed full text (for PaperQA + LLM extraction)
    parsed_texts: dict[str, str]
    # On-disk PaperQA index path, or None in deterministic mode. The heavy Docs
    # object is persisted to disk rather than held in state so the state stays
    # serializable and the index is reusable on resume.
    paperqa_index_path: str | None
    claims: list[SurfaceClaim]
    validated_claims: list[dict[str, Any]]
    opportunity_report: dict[str, Any]
    report_markdown: str | None

    # Final assembled manifest (also written to disk by ReportWriterNode)
    result: dict[str, Any]
