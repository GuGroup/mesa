from __future__ import annotations

from pathlib import Path
from typing import Any

from paper_search.http import HttpClient
from paper_search.models import DownloadedSource, Paper, ParseRun, SourceLink, SurfaceClaim
from paper_search.utils import read_json, sha256_file, write_json


class PaperCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def paper_dir(self, paper: Paper) -> Path:
        return self.root / "papers" / paper.paper_id

    def write_metadata(self, paper: Paper) -> None:
        write_json(self.paper_dir(paper) / "metadata.json", paper.to_dict())

    def read_papers(self) -> list[Paper] | None:
        path = self.root / "papers.json"
        if not path.exists():
            return None
        return [Paper(**item) for item in read_json(path)]

    def sources_dir(self, paper: Paper) -> Path:
        return self.paper_dir(paper) / "sources"

    def read_resolved_links(self, paper: Paper) -> list[SourceLink] | None:
        path = self.sources_dir(paper) / "resolved_links.json"
        if not path.exists():
            return None
        return [SourceLink(**item) for item in read_json(path)]

    def read_downloaded_source(self, paper: Paper) -> DownloadedSource | None:
        path = self.sources_dir(paper) / "source_manifest.json"
        if not path.exists():
            return None
        data = read_json(path)
        data["local_path"] = Path(data["local_path"])
        source = DownloadedSource(**data)
        return source if source.local_path.exists() else None

    def read_download_errors(self, paper: Paper) -> list[dict[str, str]]:
        path = self.sources_dir(paper) / "download_errors.json"
        if not path.exists():
            return []
        return read_json(path)

    def parses_dir(self, paper: Paper) -> Path:
        return self.paper_dir(paper) / "parses"

    def read_parse_runs(self, paper: Paper) -> list[ParseRun] | None:
        path = self.parses_dir(paper) / "parse_manifest.json"
        if not path.exists():
            return None
        runs = []
        for item in read_json(path):
            item["output_path"] = Path(item["output_path"])
            runs.append(ParseRun(**item))
        return runs

    def extraction_dir(self, paper: Paper) -> Path:
        return self.paper_dir(paper) / "extraction"

    def read_surface_claims(self, paper: Paper) -> list[SurfaceClaim] | None:
        path = self.extraction_dir(paper) / "surface_claims.json"
        if not path.exists():
            return None
        return [SurfaceClaim(**item) for item in read_json(path)]


ELSEVIER_API_HOST = "api.elsevier.com"


class SourceDownloader:
    def __init__(
        self,
        http: HttpClient,
        cache: PaperCache,
        resume: bool = True,
        elsevier_api_key: str | None = None,
        elsevier_inst_token: str | None = None,
        scihub_client: Any | None = None,
    ) -> None:
        self.http = http
        self.cache = cache
        self.resume = resume
        self.elsevier_api_key = elsevier_api_key
        self.elsevier_inst_token = elsevier_inst_token
        # Optional browser-impersonating client (curl_cffi) for Sci-Hub. Sci-Hub
        # storage URLs only return PDF bytes to the same fingerprinted session
        # that fetched the landing page, so those links cannot use self.http.
        self.scihub_client = scihub_client

    def download_first_available(
        self,
        paper: Paper,
        links: list[SourceLink],
        force: bool = False,
    ) -> DownloadedSource | None:
        errors: list[dict[str, str]] = []
        # force bypasses the resume cache so a recovery attempt (e.g. Sci-Hub
        # after an OA stub) can replace a previously cached, low-value source.
        if self.resume and not force:
            try:
                cached = self.cache.read_downloaded_source(paper)
                if cached:
                    return cached
            except Exception as exc:
                errors.append(
                    {
                        "url": "source_manifest.json",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
        ordered = sorted(links, key=lambda item: 0 if item.source_type == "oa_xml" else 1)
        for index, link in enumerate(ordered):
            try:
                return self._download(paper, link, index)
            except Exception as exc:
                errors.append(
                    {
                        "url": link.url,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
        if errors:
            write_json(self.cache.sources_dir(paper) / "download_errors.json", errors)
        return None

    def _fetch_link(self, link: SourceLink) -> tuple[bytes, str | None, str]:
        """Return ``(body, content_type, final_url)`` for a resolved link.

        Sci-Hub links go through the impersonating curl_cffi session (carrying
        the landing-page cookies/fingerprint); everything else uses the stdlib
        HttpClient.
        """
        if link.resolver == "scihub" and self.scihub_client is not None:
            return self.scihub_client.fetch(link.url)
        headers, accept = self._request_overrides(link)
        response = self.http.get(link.url, headers=headers, accept=accept)
        content_type = response.headers.get("content-type", link.content_type)
        return response.body, content_type, response.url

    def _download(self, paper: Paper, link: SourceLink, index: int) -> DownloadedSource:
        body, content_type, source_url = self._fetch_link(link)
        _validate_body(link, source_url, body, content_type)
        extension = _extension(link.source_type, content_type)
        sources_dir = self.cache.sources_dir(paper)
        sources_dir.mkdir(parents=True, exist_ok=True)
        output_path = sources_dir / f"original_{index}.{extension}"
        output_path.write_bytes(body)
        downloaded = DownloadedSource(
            paper_id=paper.paper_id,
            source_type=link.source_type,
            resolver=link.resolver,
            source_url=source_url,
            local_path=output_path,
            checksum=sha256_file(output_path),
            license=link.license,
            content_type=content_type,
        )
        write_json(sources_dir / "source_manifest.json", downloaded.to_dict())
        return downloaded

    def _request_overrides(
        self, link: SourceLink
    ) -> tuple[dict[str, str] | None, str]:
        """Per-link request headers and Accept override.

        Elsevier's full-text API returns a metadata-only ``coredata`` stub
        unless the request is authenticated. When a key is configured, attach
        ``X-ELS-APIKey`` (and an institutional token if present) and ask for the
        article XML so api.elsevier.com TDM links resolve to full text.
        """
        default_accept = "application/pdf,application/xml,text/xml,*/*"
        if self.elsevier_api_key and ELSEVIER_API_HOST in link.url.lower():
            headers = {"X-ELS-APIKey": self.elsevier_api_key}
            if self.elsevier_inst_token:
                headers["X-ELS-Insttoken"] = self.elsevier_inst_token
            return headers, "text/xml,application/xml,*/*"
        return None, default_accept


_PDF_MAGIC = b"%PDF-"


def _sniff_content_kind(body: bytes) -> str:
    """Classify a downloaded body by its leading bytes.

    A blocked/captcha mirror, an OA landing page, or an unauthenticated stub
    endpoint frequently answers ``200`` with an HTML page (or an empty body)
    instead of the article. Saving that as ``original_N.pdf`` makes a failed
    download masquerade as full text: the parser then fails with a confusing
    "missing %PDF- header" and the paper is silently lost. Sniff the content so
    such responses are rejected at the download boundary instead.

    Returns one of: ``empty`` | ``pdf`` | ``html`` | ``xml`` | ``other``.
    """
    if not body.strip():
        return "empty"
    if _PDF_MAGIC in body[:1024]:
        return "pdf"
    text = (
        body[:2048]
        .lstrip(b"\xef\xbb\xbf \t\r\n")
        .decode("latin-1", "replace")
        .lstrip()
        .lower()
    )
    if text.startswith("<!doctype html") or text.startswith("<html"):
        return "html"
    if text.startswith("<?xml") or text.startswith("<"):
        return "xml"
    return "other"


def _validate_body(
    link: SourceLink, url: str, body: bytes, content_type: str | None
) -> None:
    """Reject a downloaded body that does not match the resolved source type.

    Raises ``RuntimeError`` so :meth:`download_first_available` records the
    failure and moves on to the next link/mirror, rather than persisting a stub
    that later fails to parse. The error is the honest verdict for this link.
    """
    kind = _sniff_content_kind(body)
    if kind == "empty":
        raise RuntimeError(
            f"Empty response body from {url} (content-type={content_type!r}); "
            "treating as a failed download"
        )
    if link.source_type == "oa_pdf" and kind != "pdf":
        raise RuntimeError(
            f"Expected a PDF from {url} but got {kind} content "
            f"(content-type={content_type!r}); treating as a failed download"
        )
    if link.source_type == "oa_xml" and kind != "xml":
        raise RuntimeError(
            f"Expected XML from {url} but got {kind} content "
            f"(content-type={content_type!r}); treating as a failed download"
        )


def _extension(source_type: str, content_type: str | None) -> str:
    content_type = (content_type or "").lower()
    if source_type == "oa_xml" or "xml" in content_type:
        return "xml"
    return "pdf"
