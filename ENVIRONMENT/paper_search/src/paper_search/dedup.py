from __future__ import annotations

from paper_search.models import Paper
from paper_search.utils import normalize_doi, title_key


def dedupe_papers(papers: list[Paper]) -> list[Paper]:
    by_key: dict[str, Paper] = {}
    for paper in papers:
        key = _dedupe_key(paper)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = paper
            continue
        existing.source_databases = sorted(
            set(existing.source_databases).union(paper.source_databases)
        )
        if not existing.doi and paper.doi:
            existing.doi = paper.doi
        if not existing.abstract and paper.abstract:
            existing.abstract = paper.abstract
        if not existing.url and paper.url:
            existing.url = paper.url
        if not existing.journal and paper.journal:
            existing.journal = paper.journal
        if not existing.publisher and paper.publisher:
            existing.publisher = paper.publisher
        if existing.relevance_score is None:
            existing.relevance_score = paper.relevance_score
        if not existing.authors and paper.authors:
            existing.authors = paper.authors
        if not existing.publication_type and paper.publication_type:
            existing.publication_type = paper.publication_type
        existing.external_ids = _merge_dicts(existing.external_ids, paper.external_ids)
        existing.topics = _merge_lists(existing.topics, paper.topics)
        existing.citation_count = _max_optional_int(
            existing.citation_count,
            paper.citation_count,
        )
        existing.influential_citation_count = _max_optional_int(
            existing.influential_citation_count,
            paper.influential_citation_count,
        )
        if existing.is_open_access is not True and paper.is_open_access is not None:
            existing.is_open_access = paper.is_open_access
        if not existing.oa_url and paper.oa_url:
            existing.oa_url = paper.oa_url
        existing.provider_metadata = _merge_dicts(
            existing.provider_metadata,
            paper.provider_metadata,
        )
    return sorted(by_key.values(), key=lambda item: item.year or 0, reverse=True)


def _dedupe_key(paper: Paper) -> str:
    doi = normalize_doi(paper.doi)
    if doi:
        return f"doi:{doi}"
    return f"title:{title_key(paper.title)}"


def _merge_lists(existing: list[str], incoming: list[str]) -> list[str]:
    output = list(existing)
    seen = {item.lower() for item in output}
    for item in incoming:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _merge_dicts(
    existing: dict[str, object],
    incoming: dict[str, object],
) -> dict[str, object]:
    output = dict(existing)
    for key, value in incoming.items():
        if key not in output or output[key] in (None, "", [], {}):
            output[key] = value
    return output


def _max_optional_int(left: int | None, right: int | None) -> int | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)
