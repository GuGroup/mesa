from __future__ import annotations

from paper_search.http import HttpClient
from paper_search.models import SourceLink
from paper_search.utils import guess_source_type, quote_doi


class CrossrefTdmResolver:
    name = "crossref_tdm"

    def __init__(self, http: HttpClient, mailto: str | None = None) -> None:
        self.http = http
        self.mailto = mailto

    def resolve(self, doi: str | None) -> list[SourceLink]:
        if not doi:
            return []
        url = f"https://api.crossref.org/works/{quote_doi(doi)}"
        if self.mailto:
            url = f"{url}?mailto={self.mailto}"
        data = self.http.get(url).json()
        message = data.get("message", {})
        links: list[SourceLink] = []
        for item in message.get("link") or []:
            source_url = item.get("URL")
            content_type = item.get("content-type")
            if not source_url:
                continue
            source_type = guess_source_type(source_url, content_type)
            if source_type == "unknown":
                continue
            links.append(
                SourceLink(
                    url=source_url,
                    source_type=source_type,
                    resolver=self.name,
                    content_type=content_type,
                    evidence=item.get("intended-application") or "crossref_link",
                )
            )
        return links
