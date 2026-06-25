from __future__ import annotations

from urllib.parse import urlencode

from paper_search.http import HttpClient
from paper_search.models import Paper
from paper_search.utils import doi_to_paper_id, normalize_doi


class CrossrefSearch:
    name = "crossref"

    def __init__(self, http: HttpClient, mailto: str | None = None) -> None:
        self.http = http
        self.mailto = mailto

    def search(self, query: str, limit: int = 20) -> list[Paper]:
        params = {
            "query.bibliographic": query,
            "rows": str(limit),
            "select": (
                "DOI,title,published-print,published-online,container-title,"
                "publisher,URL,abstract,score,author,type,subject,"
                "is-referenced-by-count"
            ),
        }
        if self.mailto:
            params["mailto"] = self.mailto
        url = f"https://api.crossref.org/works?{urlencode(params)}"
        data = self.http.get(url).json()
        items = data.get("message", {}).get("items", [])
        papers: list[Paper] = []
        for item in items:
            title = _first(item.get("title")) or ""
            if not title:
                continue
            doi = normalize_doi(item.get("DOI"))
            paper_id = doi_to_paper_id(doi, title)
            papers.append(
                Paper(
                    paper_id=paper_id,
                    doi=doi,
                    title=title,
                    year=_year(item),
                    journal=_first(item.get("container-title")),
                    publisher=item.get("publisher"),
                    url=item.get("URL"),
                    abstract=item.get("abstract"),
                    source_databases=[self.name],
                    relevance_score=item.get("score"),
                    authors=_authors(item.get("author")),
                    publication_type=item.get("type"),
                    external_ids={"doi": doi} if doi else {},
                    topics=[str(topic) for topic in item.get("subject") or []],
                    citation_count=item.get("is-referenced-by-count"),
                    provider_metadata={
                        self.name: {
                            "score": item.get("score"),
                            "type": item.get("type"),
                        }
                    },
                )
            )
        return papers


def _first(value: object) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str):
        return value
    return None


def _year(item: dict) -> int | None:
    for key in ("published-print", "published-online"):
        date_parts = item.get(key, {}).get("date-parts")
        if date_parts and date_parts[0]:
            try:
                return int(date_parts[0][0])
            except (TypeError, ValueError):
                return None
    return None


def _authors(authors: object) -> list[str]:
    if not isinstance(authors, list):
        return []
    output: list[str] = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        name = " ".join(
            part
            for part in (
                author.get("given"),
                author.get("family"),
            )
            if part
        )
        if name:
            output.append(name)
    return output
