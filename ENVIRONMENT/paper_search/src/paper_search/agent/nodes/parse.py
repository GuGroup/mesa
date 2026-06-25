from __future__ import annotations

from typing import Any

from paper_search.agent.nodes._helpers import (
    append_stage_error,
    blocks_to_text,
    downloaded_source_from_dict,
    papers_by_id,
)
from paper_search.agent.nodes.resolve_download import resolve_fallback_links
from paper_search.agent.services import AgentServices
from paper_search.agent.state import GraphState
from paper_search.models import Paper
from paper_search.parsers.router import best_blocks_path

# Statuses that mean "this paper has no usable full text yet" -- the trigger for
# a one-shot Sci-Hub recovery attempt (when the fallback resolver is enabled).
_NEEDS_FULLTEXT = {
    "full_text_unavailable",
    "download_failed",
    "download_error",
    "parse_error",
    "parse_failed_or_not_configured",
}


def parse_node(state: GraphState, *, services: AgentServices) -> dict[str, Any]:
    config = services.config
    processed = state.get("processed", [])
    downloaded_sources = state.get("downloaded_sources", {})
    harness_errors = list(state.get("harness_errors", []))
    resume_events = list(state.get("resume_events", []))
    by_id = papers_by_id(state.get("papers", []))

    blocks_paths: dict[str, str] = dict(state.get("blocks_paths", {}))
    parsed_texts: dict[str, str] = dict(state.get("parsed_texts", {}))

    for record in processed:
        if record["status"] != "downloaded":
            continue
        paper = by_id[record["paper"]["paper_id"]]
        source_data = downloaded_sources.get(paper.paper_id)
        if source_data is None:
            continue
        source = downloaded_source_from_dict(source_data)

        cached_parse_runs = None
        if config.resume:
            try:
                cached_parse_runs = services.cache.read_parse_runs(paper)
            except Exception as exc:
                append_stage_error(record, harness_errors, "resume_parse", paper, exc)
        cached_blocks_path = (
            best_blocks_path(cached_parse_runs) if cached_parse_runs else None
        )
        if cached_parse_runs is not None and cached_blocks_path is not None:
            parse_runs = cached_parse_runs
            resume_events.append(
                {
                    "stage": "parse",
                    "paper_id": paper.paper_id,
                    "status": "reused_successful_parse",
                }
            )
        else:
            try:
                parse_runs = services.parser_router.parse(
                    paper, source, services.cache.parses_dir(paper)
                )
            except Exception as exc:
                append_stage_error(record, harness_errors, "parse", paper, exc)
                record["status"] = "parse_error"
                continue

        _gate_and_record(services, paper, parse_runs, record, blocks_paths, parsed_texts)

    _recover_fulltext(
        services, processed, by_id, blocks_paths, parsed_texts, harness_errors
    )

    return {
        "processed": processed,
        "blocks_paths": blocks_paths,
        "parsed_texts": parsed_texts,
        "harness_errors": harness_errors,
        "resume_events": resume_events,
    }


def _gate_and_record(
    services: AgentServices,
    paper: Paper,
    parse_runs: list[Any],
    record: dict[str, Any],
    blocks_paths: dict[str, str],
    parsed_texts: dict[str, str],
) -> bool:
    """Apply the content-quality gate to a parse result and update the record.

    A title-only / metadata-stub parse (e.g. an unauthenticated Elsevier
    "coredata" response that carries only the title and DOI) must not pass as
    full text and silently yield zero evidence. Read the body once; if it is
    below the configured floor, mark the paper full_text_unavailable and skip
    extraction. A read failure here is non-fatal and intentionally not recorded:
    blocks_to_text and the extractor read the same blocks file, so a genuine
    parse failure surfaces once in extraction rather than being double-counted.
    Set parsers.min_full_text_chars to 0 to disable the gate. Returns True when
    usable full text was obtained.
    """
    record["parse_runs"] = [run.to_dict() for run in parse_runs]
    blocks_path = best_blocks_path(parse_runs)
    if blocks_path is None:
        record["status"] = "parse_failed_or_not_configured"
        return False

    blocks_paths[paper.paper_id] = str(blocks_path)
    try:
        text: str | None = blocks_to_text(str(blocks_path))
    except Exception:
        text = None

    if text is not None:
        record["parsed_char_count"] = len(text)
        if len(text) < services.config.min_full_text_chars:
            record["status"] = "full_text_unavailable"
            return False

    record["status"] = "parsed"
    if services.full_mode and text is not None:
        parsed_texts[paper.paper_id] = text
    return True


def _recover_fulltext(
    services: AgentServices,
    processed: list[dict[str, Any]],
    by_id: dict[str, Paper],
    blocks_paths: dict[str, str],
    parsed_texts: dict[str, str],
    harness_errors: list[dict[str, str]],
) -> None:
    """Retry the fallback resolver (Sci-Hub) once for papers still without full
    text -- whether they had no primary link, downloaded a stub, or failed to parse.

    No-op unless a fallback resolver is configured (Sci-Hub can be disabled). The
    fallback download forces past the resume cache so it replaces the low-value
    source, and the result is run through the same content-quality gate.
    """
    if not any(getattr(r, "fallback", False) for r in services.resolvers):
        return

    for record in processed:
        if record["status"] not in _NEEDS_FULLTEXT or record.get("fallback_attempted"):
            continue
        paper = by_id.get(record["paper"]["paper_id"])
        if paper is None or not paper.doi:
            continue
        record["fallback_attempted"] = True

        links, errors = resolve_fallback_links(services, paper)
        if errors:
            record["resolver_errors"] = record.get("resolver_errors", []) + errors
        if not links:
            continue

        try:
            source = services.downloader.download_first_available(
                paper, links, force=True
            )
        except Exception as exc:
            append_stage_error(record, harness_errors, "fallback_download", paper, exc)
            continue
        if not source:
            continue

        record["downloaded_source"] = source.to_dict()
        record["recovered_via"] = source.resolver
        try:
            parse_runs = services.parser_router.parse(
                paper, source, services.cache.parses_dir(paper)
            )
        except Exception as exc:
            append_stage_error(record, harness_errors, "fallback_parse", paper, exc)
            record["status"] = "parse_error"
            continue

        _gate_and_record(services, paper, parse_runs, record, blocks_paths, parsed_texts)
