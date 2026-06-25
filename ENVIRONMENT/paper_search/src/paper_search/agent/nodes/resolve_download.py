from __future__ import annotations

from typing import Any

from paper_search.agent.nodes._helpers import append_stage_error, new_record
from paper_search.agent.services import AgentServices
from paper_search.agent.state import GraphState
from paper_search.models import Paper, SourceLink
from paper_search.resolvers import oa_links_from_paper
from paper_search.utils import write_json


def resolve_download_node(state: GraphState, *, services: AgentServices) -> dict[str, Any]:
    config = services.config
    papers = state.get("papers", [])
    harness_errors = list(state.get("harness_errors", []))
    resume_events = list(state.get("resume_events", []))
    graded = state.get("graded", {})

    # Cumulative across loop rounds: keep prior records, add only new papers.
    processed: list[dict[str, Any]] = list(state.get("processed", []))
    processed_ids = {record["paper"]["paper_id"] for record in processed}
    downloaded_sources: dict[str, Any] = dict(state.get("downloaded_sources", {}))

    for paper in papers:
        if paper.paper_id in processed_ids:
            continue
        processed_ids.add(paper.paper_id)

        if graded.get(paper.paper_id, True) is False:
            record = new_record(paper)
            record["status"] = "filtered_irrelevant"
            processed.append(record)
            continue

        record = new_record(paper)

        try:
            services.cache.write_metadata(paper)
        except Exception as exc:
            append_stage_error(record, harness_errors, "metadata", paper, exc)

        links = _resolve_links(
            services, config, paper, record, harness_errors, resume_events
        )
        if links is None:
            record["status"] = "resolve_error"
            processed.append(record)
            continue
        record["resolved_link_count"] = len(links)

        try:
            source = services.downloader.download_first_available(paper, links)
        except Exception as exc:
            source = None
            append_stage_error(record, harness_errors, "download", paper, exc)
            record["status"] = "download_error"

        record["downloaded_source"] = source.to_dict() if source else None
        if not source:
            download_errors: list[dict[str, str]] = []
            # Only consult the on-disk error log when resuming; with --no-resume
            # this run's own download attempt is authoritative and a stale log
            # must not flip the status.
            if config.resume:
                try:
                    download_errors = services.cache.read_download_errors(paper)
                except Exception as exc:
                    append_stage_error(
                        record, harness_errors, "resume_download_errors", paper, exc
                    )
            record["download_errors"] = download_errors
            if download_errors and record["status"] == "full_text_unavailable":
                record["status"] = "download_failed"
            processed.append(record)
            continue

        downloaded_sources[paper.paper_id] = source.to_dict()
        record["status"] = "downloaded"
        processed.append(record)

    return {
        "processed": processed,
        "downloaded_sources": downloaded_sources,
        "harness_errors": harness_errors,
        "resume_events": resume_events,
    }


def _resolve_links(
    services: AgentServices,
    config: Any,
    paper: Paper,
    record: dict[str, Any],
    harness_errors: list[dict[str, str]],
    resume_events: list[dict[str, Any]],
) -> list[SourceLink] | None:
    cached_links = None
    if config.resume:
        try:
            cached_links = services.cache.read_resolved_links(paper)
        except Exception as exc:
            append_stage_error(record, harness_errors, "resume_resolve", paper, exc)
    if cached_links is not None:
        resume_events.append(
            {
                "stage": "resolve",
                "paper_id": paper.paper_id,
                "status": "reused_resolved_links",
            }
        )
        return cached_links

    try:
        links, resolver_errors = _resolve(services, paper)
        # Don't cache a total resolver failure (zero links because every
        # resolver errored): persisting [] would make resume treat a transient
        # outage as a permanent "no primary link" verdict. Genuine empties (no
        # errors) are still cached so resume can reuse them.
        if links or not resolver_errors:
            write_json(
                services.cache.sources_dir(paper) / "resolved_links.json",
                [link.to_dict() for link in links],
            )
    except Exception as exc:
        append_stage_error(record, harness_errors, "resolve", paper, exc)
        return None
    record["resolver_errors"] = resolver_errors
    return links


def _resolve(
    services: AgentServices, paper: Paper
) -> tuple[list[SourceLink], list[dict[str, str]]]:
    # Primary (OA / TDM / configured publisher) resolvers only. Fallback
    # resolvers such as Sci-Hub are deferred to the parse node, which retries
    # them once for any paper that ends up without usable full text -- whether it
    # had no primary link at all, or downloaded a stub / failed to parse. See
    # resolve_fallback_links.
    primary = [r for r in services.resolvers if not getattr(r, "fallback", False)]
    errors: list[dict[str, str]] = []
    # Lead with the OA links the search index already surfaced (arXiv / ChemRxiv
    # / bioRxiv preprints and other OA whose DOIs the DOI-based resolvers miss),
    # then append the DOI-resolver links. Dedupe keeps the first occurrence.
    links = oa_links_from_paper(paper)
    links.extend(_run_resolvers(primary, paper, errors))
    return _dedupe_links(links), errors


def resolve_fallback_links(
    services: AgentServices, paper: Paper
) -> tuple[list[SourceLink], list[dict[str, str]]]:
    """Resolve via fallback resolvers only (e.g. Sci-Hub).

    Used by the parse node to recover papers that finished without usable full
    text. Returns ([], []) when no fallback resolver is configured, such as when
    Sci-Hub is disabled.
    """
    fallback = [r for r in services.resolvers if getattr(r, "fallback", False)]
    errors: list[dict[str, str]] = []
    links = _run_resolvers(fallback, paper, errors)
    return _dedupe_links(links), errors


def _run_resolvers(
    resolvers: list[Any], paper: Paper, errors: list[dict[str, str]]
) -> list[SourceLink]:
    links: list[SourceLink] = []
    for resolver in resolvers:
        try:
            links.extend(resolver.resolve(paper.doi))
        except Exception as exc:
            errors.append(
                {
                    "resolver": resolver.name,
                    "doi": paper.doi or "",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
    return links


def _dedupe_links(links: list[SourceLink]) -> list[SourceLink]:
    seen: set[str] = set()
    output: list[SourceLink] = []
    for link in links:
        if link.url in seen:
            continue
        seen.add(link.url)
        output.append(link)
    return output
