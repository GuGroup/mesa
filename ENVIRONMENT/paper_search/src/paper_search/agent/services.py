from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from paper_search.agent import llm as llm_layer
from paper_search.cache import PaperCache, SourceDownloader
from paper_search.config import PipelineConfig
from paper_search.http import HttpClient, RetryPolicy
from paper_search.parsers.router import ParserRouter
from paper_search.resolvers import (
    CrossrefTdmResolver,
    SciHubResolver,
    ScihubClient,
    UnpaywallResolver,
)
from paper_search.search import CrossrefSearch, OpenAlexSearch, SemanticScholarSearch
from paper_search.servers import ManagedServerConfig


@dataclass
class AgentServices:
    """Long-lived dependencies shared across graph nodes.

    Built once per run and injected into nodes via functools.partial so the
    LangGraph state itself stays data-only.
    """

    config: PipelineConfig
    http: HttpClient
    cache: PaperCache
    downloader: SourceDownloader
    search_clients: list[Any]
    resolvers: list[Any]
    parser_router: ParserRouter
    chat_model: Any | None
    provider: str
    full_mode: bool
    scihub_client: Any | None = None

    @classmethod
    def create(cls, config: PipelineConfig) -> "AgentServices":
        user_agent = (
            f"paper-search/0.1 (mailto:{config.email})"
            if config.email
            else "paper-search/0.1"
        )
        http = HttpClient(
            user_agent=user_agent,
            timeout=config.timeout,
            retry_policy=_retry_policy(config),
        )
        # Search indexes get a gentle, fail-fast retry: the shared [5,15,60]s
        # schedule is for publisher 5xx and is ruinous for a search index's
        # bursty 429s (one 429 -> up to 80s; a round of queries -> minutes). A
        # search hiccup should fail that one (query, client) fast and let the
        # other indexes cover it, not stall the pipeline.
        search_http = HttpClient(
            user_agent=user_agent,
            timeout=config.timeout,
            retry_policy=_search_retry_policy(),
        )
        cache = PaperCache(config.output_dir)
        # One browser-impersonating Sci-Hub client, shared by the resolver (page
        # crawl) and the downloader (PDF fetch) so DDoS-Guard cookies and the TLS
        # fingerprint carry across both requests. Built only when Sci-Hub is on.
        scihub_client = (
            ScihubClient(timeout=config.timeout) if config.scihub_enabled else None
        )
        downloader = SourceDownloader(
            http,
            cache,
            resume=config.resume,
            elsevier_api_key=config.elsevier_api_key,
            elsevier_inst_token=config.elsevier_inst_token,
            scihub_client=scihub_client,
        )

        server_config = None
        if config.grobid_url or config.grobid_start_cmd:
            server_config = ManagedServerConfig(
                start_cmd=config.grobid_start_cmd,
                base_url=config.grobid_url,
                startup_timeout=config.grobid_startup_timeout,
                shutdown_timeout=config.grobid_shutdown_timeout,
            )
        parser_router = ParserRouter(
            grobid_server_config=server_config,
            opendataloader_cmd=config.opendataloader_cmd,
        )

        full_mode = llm_layer.provider_enabled(config.llm)
        chat_model = None
        if full_mode:
            if config.llm.cache.response_cache:
                cache_path = config.llm.cache.response_cache_path or str(
                    config.output_dir / "llm_cache.db"
                )
                llm_layer.configure_response_cache(cache_path)
            chat_model = llm_layer.build_chat_model(config.llm)
            if chat_model is None:
                full_mode = False

        return cls(
            config=config,
            http=http,
            cache=cache,
            downloader=downloader,
            search_clients=[
                CrossrefSearch(search_http, mailto=config.email),
                OpenAlexSearch(search_http, mailto=config.email),
                SemanticScholarSearch(
                    search_http,
                    api_key=config.semantic_scholar_api_key,
                    min_request_interval=config.semantic_scholar_min_interval,
                    query_cap=config.semantic_scholar_max_queries,
                ),
            ],
            resolvers=[
                UnpaywallResolver(http, email=config.email),
                CrossrefTdmResolver(http, mailto=config.email),
                # Sci-Hub is configurable and enabled by default. It is only
                # used as last-resort recovery for papers without usable full text.
                *(
                    [SciHubResolver(client=scihub_client)]
                    if config.scihub_enabled
                    else []
                ),
            ],
            parser_router=parser_router,
            chat_model=chat_model,
            provider=llm_layer.normalize_provider(config.llm),
            full_mode=full_mode,
            scihub_client=scihub_client,
        )

    def __enter__(self) -> "AgentServices":
        self.parser_router.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.parser_router.close()
        if self.scihub_client is not None:
            self.scihub_client.close()


def _retry_policy(config: PipelineConfig) -> RetryPolicy:
    retry = config.http_retry
    return RetryPolicy(
        max_attempts=retry.max_attempts,
        backoff_seconds=tuple(retry.backoff_seconds),
        retry_statuses=frozenset(retry.retry_statuses),
        respect_retry_after=retry.respect_retry_after,
        max_sleep_seconds=retry.max_sleep_seconds,
    )


def _search_retry_policy() -> RetryPolicy:
    # Short, fail-fast backoff for search indexes (Crossref/OpenAlex/S2): honor
    # Retry-After (usually ~1s) but cap the wait at 8s, instead of the shared
    # publisher 5/15/60s. A bursty 429 on one index then costs seconds, not
    # minutes; the other indexes cover the gap.
    return RetryPolicy(
        max_attempts=3,
        backoff_seconds=(2.0, 4.0, 8.0),
        retry_statuses=frozenset({429, 500, 502, 503, 504}),
        respect_retry_after=True,
        max_sleep_seconds=8.0,
    )
