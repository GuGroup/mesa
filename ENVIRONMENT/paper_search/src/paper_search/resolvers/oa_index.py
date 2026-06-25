from __future__ import annotations

from paper_search.models import Paper, SourceLink
from paper_search.utils import guess_source_type

# Resolver-style label for links the search index already surfaced.
NAME = "oa_index"


def oa_links_from_paper(paper: Paper) -> list[SourceLink]:
    """Build SourceLinks from OA locations the search providers already returned.

    OpenAlex and Semantic Scholar hand back a direct open-access PDF URL
    (``paper.oa_url``) and, for OpenAlex, a primary-location ``pdf_url``. The
    DOI-based resolvers (Unpaywall / Crossref) never see these, so preprints on
    arXiv / ChemRxiv / bioRxiv -- whose DataCite DOIs are often absent from
    Crossref and Unpaywall -- would otherwise resolve to nothing. Surface those
    links here as primary OA sources, in priority order (provider PDF, then the
    generic OA url, then any landing page), keeping only those that look like a
    PDF or XML so the downloader does not save a landing-page HTML stub.
    """
    candidates: list[str] = []
    for meta in paper.provider_metadata.values():
        if isinstance(meta, dict) and meta.get("pdf_url"):
            candidates.append(meta["pdf_url"])
    if paper.oa_url:
        candidates.append(paper.oa_url)
    for meta in paper.provider_metadata.values():
        if isinstance(meta, dict) and meta.get("landing_page_url"):
            candidates.append(meta["landing_page_url"])

    links: list[SourceLink] = []
    seen: set[str] = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        source_type = guess_source_type(url)
        if source_type == "unknown":
            continue
        links.append(
            SourceLink(
                url=url,
                source_type=source_type,
                resolver=NAME,
                evidence="search_index_oa",
                is_best=not links,
            )
        )
    return links
