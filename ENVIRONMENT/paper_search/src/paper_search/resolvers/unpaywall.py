from __future__ import annotations

from paper_search.http import HttpClient
from paper_search.models import SourceLink
from paper_search.utils import guess_source_type, quote_doi


class UnpaywallResolver:
    name = "unpaywall"

    def __init__(self, http: HttpClient, email: str | None) -> None:
        self.http = http
        self.email = email

    def resolve(self, doi: str | None) -> list[SourceLink]:
        if not doi or not self.email:
            return []
        url = f"https://api.unpaywall.org/v2/{quote_doi(doi)}?email={self.email}"
        data = self.http.get(url).json()
        locations = []
        best = data.get("best_oa_location")
        if best:
            locations.append(best)
        locations.extend(data.get("oa_locations") or [])

        links: list[SourceLink] = []
        seen: set[str] = set()
        for location in locations:
            for key in ("url_for_pdf", "url_for_landing_page", "url"):
                source_url = location.get(key)
                if not source_url or source_url in seen:
                    continue
                seen.add(source_url)
                source_type = guess_source_type(source_url)
                if source_type == "unknown":
                    continue
                links.append(
                    SourceLink(
                        url=source_url,
                        source_type=source_type,
                        resolver=self.name,
                        license=location.get("license"),
                        version=location.get("version"),
                        host_type=location.get("host_type"),
                        evidence=location.get("evidence"),
                        is_best=location is best,
                    )
                )
        return links
