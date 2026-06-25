from __future__ import annotations

from urllib.parse import urlencode

from paper_search.http import HttpClient
from paper_search.models import Paper
from paper_search.utils import doi_to_paper_id, normalize_doi


class OpenAlexSearch:
    name = "openalex"

    def __init__(self, http: HttpClient, mailto: str | None = None) -> None:
        self.http = http
        self.mailto = mailto

    def search(self, query: str, limit: int = 20) -> list[Paper]:
        params = {
            "search": query,
            "per-page": str(limit),
        }
        if self.mailto:
            params["mailto"] = self.mailto
        url = f"https://api.openalex.org/works?{urlencode(params)}"
        data = self.http.get(url).json()
        papers: list[Paper] = []
        for item in data.get("results", []):
            title = item.get("title") or ""
            if not title:
                continue
            doi = normalize_doi(item.get("doi"))
            open_access = item.get("open_access") or {}
            primary_location = item.get("primary_location") or {}
            source = primary_location.get("source") or {}
            papers.append(
                Paper(
                    paper_id=doi_to_paper_id(doi, title),
                    doi=doi,
                    title=title,
                    year=item.get("publication_year"),
                    journal=source.get("display_name"),
                    publisher=source.get("host_organization_name"),
                    url=item.get("id"),
                    abstract=_abstract(item.get("abstract_inverted_index")),
                    source_databases=[self.name],
                    relevance_score=item.get("cited_by_count"),
                    authors=_authors(item),
                    publication_type=item.get("type"),
                    external_ids=_external_ids(item, doi),
                    topics=_topics(item),
                    citation_count=item.get("cited_by_count"),
                    is_open_access=open_access.get("is_oa"),
                    oa_url=open_access.get("oa_url"),
                    provider_metadata={
                        self.name: {
                            "id": item.get("id"),
                            "landing_page_url": primary_location.get("landing_page_url"),
                            "pdf_url": primary_location.get("pdf_url"),
                            "oa_status": open_access.get("oa_status"),
                        }
                    },
                )
            )
        return papers


def _abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    if not inverted_index:
        return None
    positions: list[tuple[int, str]] = []
    for word, indexes in inverted_index.items():
        for index in indexes:
            positions.append((index, word))
    return " ".join(word for _, word in sorted(positions))


def _authors(item: dict) -> list[str]:
    authors: list[str] = []
    for authorship in item.get("authorships") or []:
        author = authorship.get("author") or {}
        name = author.get("display_name")
        if name:
            authors.append(name)
    return authors


def _external_ids(item: dict, doi: str | None) -> dict[str, str]:
    output: dict[str, str] = {}
    ids = item.get("ids") or {}
    if doi:
        output["doi"] = doi
    for key in ("openalex", "pmid", "pmcid", "mag"):
        value = ids.get(key)
        if value:
            output[key] = str(value)
    return output


def _topics(item: dict) -> list[str]:
    output: list[str] = []
    for topic in item.get("topics") or []:
        name = topic.get("display_name")
        if name:
            output.append(name)
    if output:
        return output[:8]
    for concept in item.get("concepts") or []:
        if concept.get("score", 0) < 0.4:
            continue
        name = concept.get("display_name")
        if name:
            output.append(name)
    return output[:8]
