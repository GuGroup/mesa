from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from paper_search.agent.nodes._helpers import stage_error
from paper_search.agent.services import AgentServices
from paper_search.agent.state import GraphState
from paper_search.dedup import dedupe_papers
from paper_search.models import Paper
from paper_search.utils import write_json


def search_node(state: GraphState, *, services: AgentServices) -> dict[str, Any]:
    config = services.config
    queries = state.get("queries", [])
    harness_errors = list(state.get("harness_errors", []))
    resume_events = list(state.get("resume_events", []))
    search_errors = list(state.get("search_errors", []))
    round_no = state.get("round", 1)

    config.output_dir.mkdir(parents=True, exist_ok=True)

    existing_papers: list[Paper] = list(state.get("papers", []))
    seen_ids = set(state.get("seen_paper_ids", []))
    seen_queries = list(state.get("seen_queries", []))

    # Round 1: reuse cached papers.json when resuming. A non-empty cache only:
    # an empty papers.json means the previous round-1 search found nothing
    # (typically because every client errored), so reusing it would make a
    # transient outage permanently cache "0 papers". Re-searching is idempotent.
    if round_no <= 1 and not existing_papers and config.resume:
        try:
            cached = services.cache.read_papers()
        except Exception as exc:
            cached = None
            harness_errors.append(stage_error("resume_search", None, exc))
        if cached:
            resume_events.append({"stage": "search", "status": "reused_papers_json"})
            return {
                "papers": cached,
                "seen_paper_ids": sorted({p.paper_id for p in cached}),
                "new_papers_last_round": len(cached),
                "search_errors": search_errors,
                "harness_errors": harness_errors,
                "resume_events": resume_events,
            }

    found, round_errors = _search(services, queries)
    search_errors.extend(round_errors)

    new_papers: list[Paper] = []
    for paper in dedupe_papers(found):
        if paper.paper_id in seen_ids:
            continue
        seen_ids.add(paper.paper_id)
        new_papers.append(paper)

    papers = (existing_papers + new_papers)[: config.max_papers]
    added = max(len(papers) - len(existing_papers), 0)
    write_json(
        config.output_dir / "papers.json",
        [paper.to_dict() for paper in papers],
    )

    return {
        "papers": papers,
        "seen_paper_ids": sorted(seen_ids),
        "seen_queries": seen_queries + list(queries),
        "new_papers_last_round": added,
        "search_errors": search_errors,
        "harness_errors": harness_errors,
        "resume_events": resume_events,
    }


def _search(
    services: AgentServices, queries: list[str]
) -> tuple[list[Paper], list[dict[str, str]]]:
    if not queries:
        return [], []
    limit = services.config.per_query_limit
    unique_queries = list(dict.fromkeys(queries))
    # Per-client query cap: a slow/rate-limited client (Semantic Scholar) only
    # handles its first ``query_cap`` queries -- the core material+reaction ones,
    # which come first -- so it does not serialize the whole field-query fan-out.
    tasks = [
        (query, client)
        for index, query in enumerate(unique_queries)
        for client in services.search_clients
        if getattr(client, "query_cap", None) is None or index < client.query_cap
    ]

    def _one(task: tuple[str, Any]) -> tuple[list[Paper], dict[str, str] | None]:
        query, client = task
        try:
            return client.search(query, limit), None
        except Exception as exc:
            return [], {
                "client": client.name,
                "query": query,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    max_workers = max(1, min(services.config.search_max_concurrency, len(tasks)))
    papers: list[Paper] = []
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for found, error in executor.map(_one, tasks):
            papers.extend(found)
            if error is not None:
                errors.append(error)
    return papers, errors
