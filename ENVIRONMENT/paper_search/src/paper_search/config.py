from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import dotenv_values, load_dotenv
from omegaconf import DictConfig, OmegaConf, SCMode


def base_dir() -> Path:
    """Root for all SearchAgent data. ``$SEARCHAGENT_HOME`` or ``~/.SearchAgent``."""
    env = os.environ.get("SEARCHAGENT_HOME")
    return (Path(env) if env else Path.home() / ".SearchAgent").expanduser()


def make_session_id(material: str, reaction: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{material}_{reaction}").strip("-").lower()
    return f"{slug or 'run'}_{datetime.now().strftime('%y%m%d_%H%M%S')}"


def resolve_output_dir(
    out: Path | None,
    material: str,
    reaction: str,
    session: str | None = None,
) -> Path:
    """Pick the run output directory.

    Explicit ``--out`` wins. Otherwise each run gets its own session folder under
    ``<base>/sessions/`` (``--session`` reuses a named one for resume).
    """
    if out is not None:
        return out
    session_id = session or make_session_id(material, reaction)
    return base_dir() / "sessions" / session_id


DEFAULT_CONFIG_FILENAME = "config.yaml"
DEFAULT_GROBID_URL = '${oc.env:PAPER_SEARCH_GROBID_URL,""}'
DEFAULT_GROBID_START_CMD = '${oc.env:PAPER_SEARCH_GROBID_START_CMD,""}'
DEFAULT_OPENDATALOADER_CMD = (
    '${oc.env:PAPER_SEARCH_OPENDATALOADER_CMD,'
    '"opendataloader-pdf {input} {output_dir}"}'
)


@dataclass(slots=True)
class SemanticScholarConfig:
    api_key: str | None = '${oc.env:SEMANTIC_SCHOLAR_API_KEY,""}'
    # Semantic Scholar allows only ~1 request/second (cumulative across all
    # endpoints), even with a key, and is serialized globally. Min seconds
    # between requests; kept > 1.0 to pre-empt 429s (one 429 backoff costs far
    # more than a little extra spacing).
    min_request_interval: float = 1.5
    # S2 is the slowest, most rate-limited client. Cap how many of a round's
    # queries it runs (the first N, i.e. the core material+reaction queries);
    # Crossref/OpenAlex -- fast, high limits -- cover the rest, including the
    # Tier-B field queries. 0/None = no cap (run every query). The three indexes
    # overlap heavily, so discovery loss is minimal.
    max_queries_per_round: int = 4


@dataclass(slots=True)
class ElsevierConfig:
    # Elsevier (ScienceDirect) full-text API. With a key — and institutional
    # entitlement, optionally via an inst token — the api.elsevier.com TDM links
    # that Crossref surfaces for Elsevier articles return the full article XML
    # instead of a metadata-only "coredata" stub. Leave blank to skip.
    api_key: str | None = '${oc.env:ELSEVIER_API_KEY,""}'
    inst_token: str | None = '${oc.env:ELSEVIER_INSTTOKEN,""}'


@dataclass(slots=True)
class ScihubConfig:
    # Sci-Hub fallback resolver. On by default: it queries third-party mirrors
    # and is contacted only as a last resort to recover papers left without
    # usable primary full text. Legality and availability vary by
    # jurisdiction — set false to disable.
    enabled: bool = True


@dataclass(slots=True)
class SearchConfig:
    per_query_limit: int = 10
    max_papers: int = 30
    # Max concurrent (query, client) search requests.
    max_concurrency: int = 4


@dataclass(slots=True)
class HttpRetryConfig:
    max_attempts: int = 4
    backoff_seconds: list[float] = field(default_factory=lambda: [5.0, 15.0, 60.0])
    retry_statuses: list[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])
    respect_retry_after: bool = True
    max_sleep_seconds: float = 120.0


@dataclass(slots=True)
class HttpConfig:
    timeout: int = 30
    retry: HttpRetryConfig = field(default_factory=HttpRetryConfig)


@dataclass(slots=True)
class ExecutionConfig:
    resume: bool = True
    # Opt-in LangGraph checkpointer (in-memory) for streaming/inspection.
    # Off by default; artifact-based resume is the primary mechanism.
    checkpoint: bool = False


@dataclass(slots=True)
class GrobidConfig:
    url: str | None = DEFAULT_GROBID_URL
    start_cmd: str | None = DEFAULT_GROBID_START_CMD
    startup_timeout: float = 120.0
    shutdown_timeout: float = 10.0


@dataclass(slots=True)
class OpenDataLoaderConfig:
    cmd: str | None = DEFAULT_OPENDATALOADER_CMD


@dataclass(slots=True)
class ParserConfig:
    grobid: GrobidConfig = field(default_factory=GrobidConfig)
    opendataloader: OpenDataLoaderConfig = field(default_factory=OpenDataLoaderConfig)
    # Content-quality gate: reject parses whose extracted body text is shorter
    # than this many characters. Title-only / metadata stubs (e.g. an
    # unauthenticated Elsevier "coredata" response) are then marked
    # full_text_unavailable instead of masquerading as parsed full text.
    # Calibrated against real Elsevier responses: coredata stub ~120 chars,
    # abstract-only ~1.6k, full article body ~25k. 2000 rejects stubs and
    # abstract-only while clearing real full text. Set to 0 to disable the gate.
    min_full_text_chars: int = 2000


@dataclass(slots=True)
class LlmCacheConfig:
    # Cache full prompt -> completion pairs on disk (free identical re-runs).
    response_cache: bool = True
    # Defaults to <output_dir>/llm_cache.db when None.
    response_cache_path: str | None = None
    # Provider-side prompt caching for the shared corpus prefix
    # (Anthropic ephemeral cache_control; OpenAI prefix caching is automatic).
    prompt_cache: bool = True


@dataclass(slots=True)
class LlmConfig:
    # none | anthropic | openai | openai-oauth
    provider: str = '${oc.env:PAPER_SEARCH_PROVIDER,"none"}'
    model: str | None = '${oc.env:PAPER_SEARCH_MODEL,""}'
    base_url: str | None = '${oc.env:OPENAI_BASE_URL,""}'
    api_key_env: str | None = None
    temperature: float = 0.0
    max_tokens: int = 4096
    cache: LlmCacheConfig = field(default_factory=LlmCacheConfig)


@dataclass(slots=True)
class AgentLoopConfig:
    # Bounded gap-driven re-search loop. max_search_rounds=1 => single pass.
    max_search_rounds: int = 3
    # Stop the loop if a round adds fewer than this many new relevant papers.
    min_new_papers_to_continue: int = 1
    # Pre-download relevance filter: "strict" | "lenient" (default) | "off".
    # lenient = topical relevance + keep-on-uncertainty (recall over precision);
    # strict = require surface-evidence signals; off = keep every paper.
    # (Legacy bool also accepted: true -> lenient, false -> off.)
    relevance_filter: Any = "lenient"
    # Field-level breadth: how far beyond the target material to search/keep.
    #   "off"      -> target material only (original behavior)
    #   "reaction" -> also same-reaction papers on other systems (default)
    #   "reaction+family" -> also related material families for the reaction
    # Broader scope finds transferable descriptor/method evidence but costs more
    # search + PaperQA. Field papers are tagged relation_to_target downstream.
    field_scope: str = "reaction"


@dataclass(slots=True)
class PaperQAConfig:
    # Used only when llm.provider != none.
    enabled: bool = True
    # Use PaperQA's agentic evidence gathering (agent_query) over our corpus
    # for claim validation; falls back to a single aquery pass on error.
    agentic: bool = True
    agent_evidence_n: int = 5
    search_count: int = 8
    agent_timesteps: int | None = None
    # litellm model strings; default derived from llm.provider/model.
    llm: str | None = None
    summary_llm: str | None = None
    # PaperQA embedding. Default auto-selected: OpenAI when a key is present,
    # otherwise a local sentence-transformers model (Anthropic-only setups).
    embedding: str | None = None
    temperature: float = 0.0
    evidence_k: int = 10
    answer_max_sources: int = 5
    # Cap on PaperQA queries during claim validation (one per unique surface).
    validation_max_queries: int = 25


@dataclass(slots=True)
class ResearchConfig:
    prompt: str | None = None
    collaboration_context: str | None = None
    decision_criteria: list[str] = field(default_factory=list)
    target_properties: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    calculation_preferences: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AppConfig:
    email: str | None = '${oc.env:PAPER_SEARCH_EMAIL,""}'
    semantic_scholar: SemanticScholarConfig = field(
        default_factory=SemanticScholarConfig
    )
    elsevier: ElsevierConfig = field(default_factory=ElsevierConfig)
    scihub: ScihubConfig = field(default_factory=ScihubConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    http: HttpConfig = field(default_factory=HttpConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    parsers: ParserConfig = field(default_factory=ParserConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    paperqa: PaperQAConfig = field(default_factory=PaperQAConfig)
    agent: AgentLoopConfig = field(default_factory=AgentLoopConfig)
    research: ResearchConfig = field(default_factory=ResearchConfig)


@dataclass(slots=True)
class PipelineConfig:
    output_dir: Path
    email: str | None = None
    semantic_scholar_api_key: str | None = None
    semantic_scholar_min_interval: float = 1.5
    semantic_scholar_max_queries: int = 4
    elsevier_api_key: str | None = None
    elsevier_inst_token: str | None = None
    scihub_enabled: bool = True
    grobid_url: str | None = None
    grobid_start_cmd: str | None = None
    opendataloader_cmd: str | None = None
    min_full_text_chars: int = 2000
    per_query_limit: int = 10
    max_papers: int = 30
    search_max_concurrency: int = 4
    timeout: int = 30
    http_retry: HttpRetryConfig = field(default_factory=HttpRetryConfig)
    resume: bool = True
    checkpoint: bool = False
    max_search_rounds: int = 3
    min_new_papers_to_continue: int = 1
    relevance_filter: Any = "lenient"
    field_scope: str = "reaction"
    grobid_startup_timeout: float = 30.0
    grobid_shutdown_timeout: float = 10.0
    llm: LlmConfig = field(default_factory=LlmConfig)
    paperqa: PaperQAConfig = field(default_factory=PaperQAConfig)
    research: ResearchConfig = field(default_factory=ResearchConfig)

    @classmethod
    def from_sources(
        cls,
        output_dir: Path,
        config_path: Path | None = None,
        email: str | None = None,
        grobid_url: str | None = None,
        grobid_start_cmd: str | None = None,
        opendataloader_cmd: str | None = None,
        per_query_limit: int | None = None,
        max_papers: int | None = None,
        timeout: int | None = None,
        research_prompt: str | None = None,
        research: ResearchConfig | None = None,
        resume: bool | None = None,
        llm_provider: str | None = None,
        llm_model: str | None = None,
        cwd: Path | None = None,
    ) -> "PipelineConfig":
        config = load_config(config_path=config_path, cwd=cwd)
        apply_research_overrides(config, research)
        apply_cli_overrides(
            config,
            email=email,
            grobid_url=grobid_url,
            grobid_start_cmd=grobid_start_cmd,
            opendataloader_cmd=opendataloader_cmd,
            per_query_limit=per_query_limit,
            max_papers=max_papers,
            timeout=timeout,
            research_prompt=research_prompt,
            resume=resume,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )
        return cls.from_omegaconf(config, output_dir=output_dir)

    @classmethod
    def from_omegaconf(
        cls,
        config: DictConfig,
        output_dir: Path,
    ) -> "PipelineConfig":
        app_config = OmegaConf.to_container(
            config,
            resolve=True,
            structured_config_mode=SCMode.INSTANTIATE,
        )
        if not isinstance(app_config, AppConfig):
            raise TypeError("Pipeline config must resolve to AppConfig.")
        return cls.from_app_config(app_config, output_dir=output_dir)

    @classmethod
    def from_app_config(
        cls,
        config: AppConfig,
        output_dir: Path,
    ) -> "PipelineConfig":
        return cls(
            output_dir=output_dir,
            email=_optional(config.email),
            semantic_scholar_api_key=_optional(config.semantic_scholar.api_key),
            semantic_scholar_min_interval=config.semantic_scholar.min_request_interval,
            semantic_scholar_max_queries=config.semantic_scholar.max_queries_per_round,
            elsevier_api_key=_optional(config.elsevier.api_key),
            elsevier_inst_token=_optional(config.elsevier.inst_token),
            scihub_enabled=config.scihub.enabled,
            grobid_url=_optional(config.parsers.grobid.url),
            grobid_start_cmd=_optional(config.parsers.grobid.start_cmd),
            opendataloader_cmd=_optional(config.parsers.opendataloader.cmd),
            min_full_text_chars=config.parsers.min_full_text_chars,
            per_query_limit=config.search.per_query_limit,
            max_papers=config.search.max_papers,
            search_max_concurrency=config.search.max_concurrency,
            timeout=config.http.timeout,
            http_retry=config.http.retry,
            resume=config.execution.resume,
            checkpoint=config.execution.checkpoint,
            max_search_rounds=config.agent.max_search_rounds,
            min_new_papers_to_continue=config.agent.min_new_papers_to_continue,
            relevance_filter=config.agent.relevance_filter,
            field_scope=config.agent.field_scope,
            grobid_startup_timeout=config.parsers.grobid.startup_timeout,
            grobid_shutdown_timeout=config.parsers.grobid.shutdown_timeout,
            llm=config.llm,
            paperqa=config.paperqa,
            research=config.research,
        )


def load_config(
    config_path: Path | None = None,
    cwd: Path | None = None,
) -> DictConfig:
    cwd = cwd or Path.cwd()
    load_dotenv_sources(cwd)
    config = OmegaConf.structured(AppConfig)
    discovered_path = config_path or discover_config_path(cwd)
    if discovered_path is not None:
        config = OmegaConf.merge(config, OmegaConf.load(discovered_path))
    return config


def discover_config_path(cwd: Path | None = None) -> Path | None:
    candidate = (cwd or Path.cwd()) / DEFAULT_CONFIG_FILENAME
    return candidate if candidate.exists() else None


def load_dotenv_sources(cwd: Path | None = None) -> bool:
    loaded = load_workdir_dotenv(cwd)
    return load_home_dotenv(preserve_existing=True) or loaded


def load_workdir_dotenv(cwd: Path | None = None) -> bool:
    env_path = (cwd or Path.cwd()) / ".env"
    if not env_path.exists():
        return False
    return bool(load_dotenv(dotenv_path=env_path, override=False))


def load_home_dotenv(preserve_existing: bool = True) -> bool:
    env_path = Path.home() / ".env"
    if not env_path.exists():
        return False
    if not preserve_existing:
        return bool(load_dotenv(dotenv_path=env_path, override=False))
    values = dotenv_values(env_path)
    loaded = False
    for key, value in values.items():
        if value is None or key in os.environ:
            continue
        os.environ[key] = value
        loaded = True
    return loaded


def apply_research_overrides(
    config: DictConfig, research: ResearchConfig | None = None
) -> None:
    if research is None:
        return
    overrides = {
        "research.prompt": research.prompt,
        "research.collaboration_context": research.collaboration_context,
    }
    for key, value in overrides.items():
        if value is not None:
            OmegaConf.update(config, key, value, merge=False)
    list_overrides = {
        "research.decision_criteria": research.decision_criteria,
        "research.target_properties": research.target_properties,
        "research.constraints": research.constraints,
        "research.calculation_preferences": research.calculation_preferences,
    }
    for key, value in list_overrides.items():
        if value:
            OmegaConf.update(config, key, value, merge=False)


def apply_cli_overrides(
    config: DictConfig,
    email: str | None = None,
    grobid_url: str | None = None,
    grobid_start_cmd: str | None = None,
    opendataloader_cmd: str | None = None,
    per_query_limit: int | None = None,
    max_papers: int | None = None,
    timeout: int | None = None,
    research_prompt: str | None = None,
    resume: bool | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> None:
    overrides = {
        "email": email,
        "search.per_query_limit": per_query_limit,
        "search.max_papers": max_papers,
        "http.timeout": timeout,
        "parsers.grobid.url": grobid_url,
        "parsers.grobid.start_cmd": grobid_start_cmd,
        "parsers.opendataloader.cmd": opendataloader_cmd,
        "research.prompt": research_prompt,
        "execution.resume": resume,
        "llm.provider": llm_provider,
        "llm.model": llm_model,
    }
    for key, value in overrides.items():
        if value is not None:
            OmegaConf.update(config, key, value, merge=False)


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None
