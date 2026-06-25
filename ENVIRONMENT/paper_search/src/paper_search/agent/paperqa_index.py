from __future__ import annotations

import asyncio
import importlib.util
import os
import pickle
from pathlib import Path
from typing import Any, Final

from paper_search.agent.llm import (
    DEFAULT_MODELS,
    openai_api_key,
    openai_base_url,
    normalize_provider,
)
from paper_search.config import LlmConfig, PaperQAConfig

OPENAI_EMBEDDING_KEY_ENV: Final = "OPENAI_EMBEDDING_KEY"


def litellm_model(provider: str, model: str | None) -> str:
    name = model or DEFAULT_MODELS.get(provider) or DEFAULT_MODELS["openai"]
    if provider == "anthropic" and not name.startswith("anthropic/"):
        return f"anthropic/{name}"
    if provider == "openai-oauth" and not name.startswith("openai/"):
        return f"openai/{name}"
    return name


def default_embedding() -> str:
    if _optional_env(OPENAI_EMBEDDING_KEY_ENV):
        return "text-embedding-3-small"
    if importlib.util.find_spec("sentence_transformers") is None:
        raise RuntimeError(
            "No OPENAI_EMBEDDING_KEY set and local embeddings are not installed. "
            "Either set OPENAI_EMBEDDING_KEY, install the extra "
            "(`uv sync --extra local-embeddings` / "
            "`pip install 'paper-search[local-embeddings]'`), or set "
            "`paperqa.embedding` explicitly in config."
        )
    return "st-multi-qa-MiniLM-L6-cos-v1"


def embedding_config(embedding: str) -> dict[str, Any] | None:
    if not _is_openai_embedding(embedding):
        return None
    api_key = _optional_env(OPENAI_EMBEDDING_KEY_ENV)
    if api_key is None:
        raise RuntimeError(
            "OpenAI PaperQA embeddings require OPENAI_EMBEDDING_KEY. "
            "Set paperqa.embedding to a local st-* model to avoid OpenAI embeddings."
        )
    return {"kwargs": {"api_key": api_key}}


def _is_openai_embedding(embedding: str) -> bool:
    name = embedding.strip().lower()
    if name.startswith("litellm-"):
        name = name.removeprefix("litellm-")
    if name.startswith("openai/"):
        name = name.removeprefix("openai/")
    return name.startswith("text-embedding-")


def _optional_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def litellm_config(
    llm: LlmConfig, model: str, temperature: float
) -> dict[str, Any] | None:
    provider = normalize_provider(llm)
    if provider not in ("openai", "openai-oauth"):
        return None
    base_url = openai_base_url(llm)
    api_key = openai_api_key(llm)
    if provider == "openai" and base_url is None and llm.api_key_env is None:
        return None
    params: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "cache_control_injection_points": [{"location": "message", "role": "system"}],
    }
    if base_url is not None:
        params["api_base"] = base_url
    if api_key is not None:
        params["api_key"] = api_key
    return {
        "name": model,
        "model_list": [{"model_name": model, "litellm_params": params}],
    }


def resolve_models(llm: LlmConfig, pq: PaperQAConfig) -> tuple[str, str, str]:
    provider = normalize_provider(llm)
    base = pq.llm or litellm_model(provider, llm.model)
    summary = pq.summary_llm or base
    embedding = pq.embedding or default_embedding()
    return base, summary, embedding


def build_settings(
    llm: LlmConfig, pq: PaperQAConfig, work_dir: Path | None = None
) -> Any:
    from paperqa import Settings

    base, summary, embedding = resolve_models(llm, pq)
    from paper_search.agent.llm import effective_temperature

    temperature = effective_temperature(base, pq.temperature)
    base_config = litellm_config(llm, base, temperature)
    summary_config = litellm_config(llm, summary, temperature)
    embed_config = embedding_config(embedding)
    settings = Settings(
        llm=base,
        llm_config=base_config,
        summary_llm=summary,
        summary_llm_config=summary_config,
        embedding=embedding,
        embedding_config=embed_config,
        temperature=temperature,
    )
    settings.agent.agent_llm = base
    settings.agent.agent_llm_config = base_config
    settings.answer.evidence_k = pq.evidence_k
    settings.answer.answer_max_sources = pq.answer_max_sources
    # We pass an explicit citation/docname/dockey for every document (see
    # _aadd_documents), so PaperQA's own DOI metadata enrichment is redundant.
    # Leaving it on re-queries Crossref/Semantic Scholar per paper, which both
    # trips Semantic Scholar's 1 req/s 429 limit during indexing and leaks
    # unclosed aiohttp sessions on exit. Disable it.
    try:
        settings.parsing.use_doc_details = False
    except Exception:
        pass
    try:
        settings.agent.search_count = pq.search_count
        settings.agent.agent_evidence_n = pq.agent_evidence_n
        if pq.agent_timesteps is not None:
            settings.agent.max_timesteps = pq.agent_timesteps
    except Exception:
        pass
    # Scope PaperQA's agent tantivy index to this run's paperqa/ folder. By
    # default index_directory is the shared ~/.pqa/indexes and paper_directory
    # is the process CWD with recurse_subdirectories=True -- so agent_query
    # crawls the entire project tree, prunes deleted files (noisy "Removing ...
    # from index" logs), and lets one run's corpus leak into another's search.
    # Pinning both to work_dir keeps the index per-session and limited to the
    # .txt documents we wrote there.
    if work_dir is not None:
        try:
            settings.agent.index.paper_directory = str(work_dir)
            settings.agent.index.index_directory = str(work_dir / "index")
            settings.agent.index.recurse_subdirectories = False
        except Exception:
            pass
    return settings


def _run_async(coro: Any) -> Any:
    try:
        return asyncio.run(coro)
    except RuntimeError:
        # An event loop is already running (rare in the sync graph path).
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _aadd_documents(docs: Any, documents: list[dict[str, Any]], settings: Any, work_dir: Path) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)

    async def _add_all() -> None:
        for doc in documents:
            text = (doc.get("text") or "").strip()
            if not text:
                continue
            paper_id = doc["paper_id"]
            txt_path = work_dir / f"{paper_id}.txt"
            txt_path.write_text(text, encoding="utf-8")
            citation = doc.get("title") or paper_id
            if doc.get("doi"):
                citation = f"{citation}. doi:{doc['doi']}"
            await docs.aadd(
                str(txt_path),
                citation=citation,
                docname=paper_id,
                dockey=doc.get("doi") or paper_id,
                settings=settings,
            )

    _run_async(_add_all())


def build_docs(documents: list[dict[str, Any]], settings: Any, work_dir: Path) -> Any:
    """Index parsed full text into a fresh PaperQA ``Docs`` object.

    ``documents`` items: ``{paper_id, title, doi, text}``. Each is written to a
    ``.txt`` so PaperQA performs its own chunking + embedding.
    """
    from paperqa import Docs

    docs = Docs()
    _aadd_documents(docs, documents, settings, work_dir)
    return docs


def extend_docs(docs: Any, documents: list[dict[str, Any]], settings: Any, work_dir: Path) -> Any:
    """Add documents to an existing ``Docs`` (incremental indexing across rounds)."""
    _aadd_documents(docs, documents, settings, work_dir)
    return docs


def save_docs(docs: Any, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        pickle.dump(docs, handle)


def load_docs(path: str | Path) -> Any:
    with open(path, "rb") as handle:
        return pickle.load(handle)


def _session_to_dict(question: str, session: Any) -> dict[str, Any]:
    contexts = []
    for ctx in getattr(session, "contexts", []) or []:
        text_obj = getattr(ctx, "text", None)
        contexts.append(
            {
                "context": getattr(ctx, "context", ""),
                "score": getattr(ctx, "score", None),
                "source": getattr(text_obj, "name", None) if text_obj else None,
            }
        )
    return {
        "question": question,
        "answer": getattr(session, "answer", "")
        or getattr(session, "formatted_answer", ""),
        "references": getattr(session, "references", ""),
        "contexts": contexts,
    }


def ask(docs: Any, question: str, settings: Any) -> dict[str, Any]:
    """Run a single PaperQA query and return a JSON-friendly result."""
    session = _run_async(docs.aquery(question, settings=settings))
    return _session_to_dict(question, session)


def agent_ask(docs: Any, question: str, settings: Any) -> dict[str, Any]:
    """Run PaperQA's agent (multi-step gather_evidence/gen_answer) over our docs.

    The agent is given our pre-built ``Docs`` so its ``paper_search`` tool ranks
    within the locally resolved full-text corpus (PaperQA OSS does no external
    web discovery). If the agent yields a degenerate answer, fall back to a
    single ``aquery`` pass.
    """
    import inspect

    from paperqa import agent_query

    result = agent_query(question, settings, docs=docs)
    if inspect.isawaitable(result):
        result = _run_async(result)
    session = getattr(result, "session", result)
    payload = _session_to_dict(question, session)
    answer = (payload.get("answer") or "").lower()
    if not payload.get("contexts") and ("cannot answer" in answer or "no papers" in answer):
        return ask(docs, question, settings)
    return payload


def ask_many(
    docs: Any, questions: list[str], settings: Any
) -> list[dict[str, Any]]:
    """Run several PaperQA queries concurrently in one event loop."""
    if not questions:
        return []

    async def _run() -> list[Any]:
        return await asyncio.gather(
            *[docs.aquery(question, settings=settings) for question in questions],
            return_exceptions=True,
        )

    sessions = _run_async(_run())
    results: list[dict[str, Any]] = []
    for question, session in zip(questions, sessions):
        if isinstance(session, Exception):
            results.append({"question": question, "error": str(session)})
        else:
            results.append(_session_to_dict(question, session))
    return results
