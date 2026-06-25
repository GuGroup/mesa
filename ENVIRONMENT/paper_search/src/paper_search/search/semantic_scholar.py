from __future__ import annotations

import threading
import time
from typing import Callable
from urllib.parse import urlencode

from paper_search.http import HttpClient
from paper_search.models import Paper
from paper_search.utils import doi_to_paper_id, normalize_doi


class SemanticScholarSearch:
    name = "semantic_scholar"

    def __init__(
        self,
        http: HttpClient,
        api_key: str | None = None,
        min_request_interval: float = 1.5,
        query_cap: int | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.http = http
        self.api_key = api_key
        # Semantic Scholar allows only 1 request/second (cumulative across all
        # endpoints), even with an API key. Serialize + space out requests so
        # concurrent searches from the thread pool do not get rejected.
        self.min_request_interval = min_request_interval
        # Max queries this client handles per round; the search node dispatches
        # only the first ``query_cap`` queries to it (Crossref/OpenAlex cover the
        # rest). None/0 = no cap.
        self.query_cap = query_cap or None
        self._sleeper = sleeper
        self._monotonic = monotonic
        self._rate_lock = threading.Lock()
        self._last_request = 0.0

    def _throttle(self) -> None:
        if self.min_request_interval <= 0:
            return
        # Hold the lock across the sleep so requests are serialized globally.
        with self._rate_lock:
            wait = self.min_request_interval - (self._monotonic() - self._last_request)
            if wait > 0:
                self._sleeper(wait)
            self._last_request = self._monotonic()

    def search(self, query: str, limit: int = 20) -> list[Paper]:
        params = {
            "query": query,
            "limit": str(limit),
            "fields": (
                "paperId,title,year,venue,abstract,url,externalIds,citationCount,"
                "influentialCitationCount,authors,publicationTypes,"
                "fieldsOfStudy,isOpenAccess,openAccessPdf"
            ),
        }
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?{urlencode(params)}"
        headers = {"x-api-key": self.api_key} if self.api_key else None
        self._throttle()
        data = self.http.get(url, headers=headers).json()
        papers: list[Paper] = []
        for item in data.get("data", []):
            title = item.get("title") or ""
            if not title:
                continue
            external_ids = item.get("externalIds") or {}
            doi = normalize_doi(external_ids.get("DOI"))
            open_access_pdf = item.get("openAccessPdf") or {}
            papers.append(
                Paper(
                    paper_id=doi_to_paper_id(doi, title),
                    doi=doi,
                    title=title,
                    year=item.get("year"),
                    journal=item.get("venue"),
                    url=item.get("url"),
                    abstract=item.get("abstract"),
                    source_databases=[self.name],
                    relevance_score=item.get("citationCount"),
                    authors=_authors(item),
                    publication_type=_first(item.get("publicationTypes")),
                    external_ids=_external_ids(external_ids, doi),
                    topics=[str(topic) for topic in item.get("fieldsOfStudy") or []],
                    citation_count=item.get("citationCount"),
                    influential_citation_count=item.get("influentialCitationCount"),
                    is_open_access=item.get("isOpenAccess"),
                    oa_url=open_access_pdf.get("url"),
                    provider_metadata={
                        self.name: {
                            "paper_id": item.get("paperId"),
                            "open_access_pdf_status": open_access_pdf.get("status"),
                        }
                    },
                )
            )
        return papers


def _authors(item: dict) -> list[str]:
    output: list[str] = []
    for author in item.get("authors") or []:
        name = author.get("name")
        if name:
            output.append(name)
    return output


def _first(values: object) -> str | None:
    if isinstance(values, list) and values:
        return str(values[0])
    if isinstance(values, str):
        return values
    return None


def _external_ids(external_ids: dict, doi: str | None) -> dict[str, str]:
    output: dict[str, str] = {}
    if doi:
        output["doi"] = doi
    for key, value in external_ids.items():
        if value:
            output[key.lower()] = str(value)
    return output
