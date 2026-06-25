from __future__ import annotations

from typing import Any

from paper_search.agent.nodes._helpers import papers_by_id, stage_error
from paper_search.agent.services import AgentServices
from paper_search.agent.state import GraphState


def paperqa_index_node(state: GraphState, *, services: AgentServices) -> dict[str, Any]:
    """Index parsed full text into a persisted PaperQA Docs object.

    Full mode only. Incremental: across loop rounds it loads the existing index
    and adds only newly-parsed papers, so embeddings are not recomputed.
    """
    if not services.full_mode or not services.config.paperqa.enabled:
        return {}
    parsed_texts = state.get("parsed_texts", {})
    if not parsed_texts:
        return {}

    indexed = list(state.get("indexed_paper_ids", []))
    indexed_set = set(indexed)
    new_ids = [pid for pid in parsed_texts if pid not in indexed_set]
    if not new_ids:
        return {}

    harness_errors = list(state.get("harness_errors", []))
    by_id = papers_by_id(state.get("papers", []))
    index_dir = services.cache.root / "paperqa"
    index_path = index_dir / "index.pkl"

    try:
        from paper_search.agent import paperqa_index as pq

        settings = pq.build_settings(
            services.config.llm, services.config.paperqa, work_dir=index_dir
        )
        documents = []
        for paper_id in new_ids:
            paper = by_id.get(paper_id)
            documents.append(
                {
                    "paper_id": paper_id,
                    "title": paper.title if paper else paper_id,
                    "doi": paper.doi if paper else None,
                    "text": parsed_texts[paper_id],
                }
            )

        if index_path.exists():
            docs = pq.load_docs(index_path)
            pq.extend_docs(docs, documents, settings, index_dir)
        else:
            docs = pq.build_docs(documents, settings, index_dir)
        pq.save_docs(docs, index_path)
        return {
            "paperqa_index_path": str(index_path),
            "indexed_paper_ids": indexed + new_ids,
        }
    except Exception as exc:
        harness_errors.append(stage_error("paperqa_index", None, exc))
        return {"harness_errors": harness_errors}
