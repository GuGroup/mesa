


from __future__ import annotations



import re

from html.parser import HTMLParser

from typing import Any

from urllib.parse import urljoin



from paper_search.http import HttpClient

from paper_search.models import SourceLink

from paper_search.utils import guess_source_type





class _PdfUrlExtractor(HTMLParser):

    """Lightweight HTML parser that extracts a PDF download URL from

    a Sci-Hub HTML page, matching scidownl's selector logic."""



    _CAPTCHA_TITLE_RE = re.compile(r"robot", re.IGNORECASE)



    def __init__(self) -> None:

        super().__init__()

        self.pdf_url: str | None = None

        self._title_text: str | None = None

        self._in_title = False

        self._captcha_div = False



    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:

        attr_dict = dict(attrs)



        if tag == "title":

            self._in_title = True

            return



        # captcha detection: <div class="question">...</div>

        if tag == "div" and attr_dict.get("class") == "question":

            self._captcha_div = True



        # Newer Sci-Hub markup: <object type="application/pdf" data="...">.

        # Preferred over the legacy <embed>, matching scidownl's current

        # primary selector.

        if tag == "object" and attr_dict.get("type") == "application/pdf":

            data = attr_dict.get("data")

            if data:

                self.pdf_url = data



        # Legacy markup: <embed id="pdf" src="...">. Only fill in if a newer

        # <object> tag has not already provided the URL.

        if tag == "embed" and attr_dict.get("id") == "pdf":

            src = attr_dict.get("src")

            if src and not self.pdf_url:

                self.pdf_url = src



        # Last-resort fallback: <iframe src="...">

        if tag == "iframe":

            src = attr_dict.get("src")

            if src and not self.pdf_url:

                self.pdf_url = src



    def handle_endtag(self, tag: str) -> None:

        if tag == "title":

            self._in_title = False



    def handle_data(self, data: str) -> None:

        if self._in_title and data.strip():

            self._title_text = data.strip()



    @property

    def is_captcha(self) -> bool:

        if self._captcha_div:

            return True

        if self._title_text and self._CAPTCHA_TITLE_RE.search(self._title_text):

            return True

        return False





class _Resp:

    """Transport-agnostic response (curl_cffi or stdlib HttpClient)."""



    __slots__ = ("status", "content", "url", "content_type")



    def __init__(

        self, status: int, content: bytes, url: str, content_type: str | None

    ) -> None:

        self.status = status

        self.content = content

        self.url = url

        self.content_type = content_type





# Aggregator pages listing the currently-live Sci-Hub domains. Sci-Hub rotates

# TLDs (sci-hub.se went DNS-dead, .al/.box/.mk/.su appeared), so a hardcoded

# list goes stale; scidownl solves this with `domain.update --mode crawl`

# against a source page. We mirror that: scrape the source, regex out the

# domains, and fall back to the seed list when discovery yields nothing.

_MIRROR_SOURCES = ("https://www.sci-hub.pub/",)

_MIRROR_RE = re.compile(r"https?://(?:www\.)?sci-hub\.[a-z]{2,}", re.IGNORECASE)

_MIRROR_EXCLUDE_RE = re.compile(r"sci-hub\.(?:pub|wordpress)", re.IGNORECASE)





def parse_mirror_domains(html: str) -> list[str]:

    """Extract normalized ``https://sci-hub.<tld>`` mirror URLs from a source

    page, deduped in first-seen order (scidownl's crawl-mode regex)."""

    seen: set[str] = set()

    out: list[str] = []

    for match in _MIRROR_RE.finditer(html):

        raw = match.group(0)

        if _MIRROR_EXCLUDE_RE.search(raw):

            continue

        # Normalize scheme + drop www. so https/http/www variants collapse.

        host = raw.split("://", 1)[1].lower()

        if host.startswith("www."):

            host = host[4:]

        url = f"https://{host}"

        if url not in seen:

            seen.add(url)

            out.append(url)

    return out





def _new_curl_session(impersonate: str) -> Any | None:

    """A ``curl_cffi`` browser-impersonating session, or ``None`` if the

    optional dependency is not installed."""

    try:

        from curl_cffi import requests as cffi_requests

    except Exception:

        return None

    try:

        return cffi_requests.Session(impersonate=impersonate)

    except Exception:

        return None





class ScihubClient:

    """Browser-impersonating transport for Sci-Hub.



    Drives both the landing-page crawl and the PDF download through one session

    so DDoS-Guard cookies + the TLS fingerprint carry across the two requests

    (see module docstring). Mirrors are tried in order until one yields a PDF

    URL. With ``curl_cffi`` present it impersonates Chrome; otherwise it uses the

    supplied stdlib ``HttpClient`` (no POST fallback, no impersonation).

    """



    _MIRRORS = [

        "https://sci-hub.se",

        "https://sci-hub.ru",

        "https://sci-hub.st",

        "https://sci-hub.wf",

    ]



    def __init__(

        self,

        *,

        session: Any | None = None,

        http: HttpClient | None = None,

        timeout: int = 30,

        mirrors: list[str] | None = None,

        impersonate: str = "chrome",

        discover: bool = True,

    ) -> None:

        self.timeout = timeout

        self.mirrors = list(mirrors) if mirrors else list(self._MIRRORS)

        # Explicit mirrors (e.g. from tests) are authoritative; only auto-discover

        # when the caller did not pin a list. Discovery runs once, lazily.

        self._discover = discover and not mirrors

        self._discovered = False

        self._http = http

        self._session = session

        if self._session is None and self._http is None:

            self._session = _new_curl_session(impersonate)

            if self._session is None:

                # No curl_cffi and no injected client: degrade to stdlib so the

                # resolver still functions (as it did before this change).

                self._http = HttpClient()



    @classmethod

    def from_http(cls, http: HttpClient, **kwargs: Any) -> "ScihubClient":

        """Stdlib-backed client (used by tests and as the no-curl_cffi fallback)."""

        return cls(http=http, **kwargs)



    @property

    def impersonating(self) -> bool:

        return self._session is not None



    def _get(self, url: str) -> _Resp:

        if self._session is not None:

            r = self._session.get(url, timeout=self.timeout)

            return _Resp(

                r.status_code,

                r.content,

                getattr(r, "url", url),

                r.headers.get("content-type") if getattr(r, "headers", None) else None,

            )

        assert self._http is not None

        # One attempt: a dead/blocked mirror should fail fast so the next mirror

        # is tried, not consume the retry/backoff budget.

        resp = self._http.get(url, max_attempts=1)

        return _Resp(resp.status, resp.body, resp.url, resp.headers.get("content-type"))



    def _post(self, url: str, data: dict[str, str]) -> _Resp | None:

        # The stdlib HttpClient is GET-only; the POST empty-body fallback only

        # applies to the curl_cffi backend.

        if self._session is None:

            return None

        r = self._session.post(url, data=data, timeout=self.timeout)

        return _Resp(

            r.status_code,

            r.content,

            getattr(r, "url", url),

            r.headers.get("content-type") if getattr(r, "headers", None) else None,

        )



    def _ensure_mirrors(self) -> None:

        """Refresh the mirror list from the aggregator source once per client.



        Discovered domains lead (they are the current live set); the seed list is

        appended as a fallback. Best-effort: any failure keeps the seed list.

        """

        if self._discovered or not self._discover:

            return

        self._discovered = True

        discovered: list[str] = []

        for source in _MIRROR_SOURCES:

            try:

                resp = self._get(source)

            except Exception:

                continue

            if resp.status != 200 or not resp.content:

                continue

            discovered.extend(

                parse_mirror_domains(resp.content.decode("utf-8", errors="replace"))

            )

        if not discovered:

            return

        merged = list(discovered)

        for mirror in self.mirrors:

            if mirror not in merged:

                merged.append(mirror)

        self.mirrors = merged



    def resolve_pdf_link(self, doi: str | None) -> SourceLink | None:

        if not doi:

            return None

        self._ensure_mirrors()

        for mirror in self.mirrors:

            page_url = f"{mirror}/{doi}"

            try:

                resp = self._get(page_url)

            except Exception:

                continue



            # DDoS-Guard / form-based mirrors answer GET with an empty 200; retry

            # via POST in the same session (scidownl's _fetch fallback).

            if resp.status == 200 and len(resp.content) == 0:

                try:

                    alt = self._post(mirror, {"request": doi})

                except Exception:

                    alt = None

                if alt is not None:

                    resp = alt



            if resp.status != 200 or not resp.content:

                continue



            html = resp.content.decode("utf-8", errors="replace")

            extractor = _PdfUrlExtractor()

            extractor.feed(html)

            if extractor.is_captcha:

                continue  # try the next mirror



            raw_url = extractor.pdf_url

            if not raw_url:

                continue



            url = _absolutize(raw_url, page_url)

            # Guess off the path only (Sci-Hub appends a #navpanes/view fragment

            # that hides the .pdf suffix). Default to oa_pdf so the parser router

            # accepts it; a bare "pdf" is treated as unsupported and never parsed.

            source_type = guess_source_type(url.split("#", 1)[0])

            if source_type == "unknown":

                source_type = "oa_pdf"



            return SourceLink(

                url=url,

                source_type=source_type,

                resolver="scihub",

                evidence=f"scihub_mirror:{mirror}",

            )

        return None



    def fetch(self, url: str) -> tuple[bytes, str | None, str]:

        """Download bytes through the impersonating session so the PDF request

        carries the same fingerprint/cookies as the landing-page crawl."""

        resp = self._get(url)

        return resp.content, resp.content_type, resp.url



    def close(self) -> None:

        if self._session is not None:

            try:

                self._session.close()

            except Exception:

                pass





def _absolutize(raw_url: str, page_url: str) -> str:

    if raw_url.startswith("//"):

        return "https:" + raw_url

    if raw_url.startswith("/"):

        return urljoin(page_url, raw_url)

    return raw_url





class SciHubResolver:

    """Fallback resolver that retrieves PDFs via Sci-Hub mirrors."""



    name = "scihub"

    # Contacted only when the OA/publisher resolvers found nothing (see the parse

    # node's recovery pass), so a slow/blocked mirror never delays a paper that

    # already has an open-access source.

    fallback = True



    def __init__(

        self, http: HttpClient | None = None, client: ScihubClient | None = None

    ) -> None:

        if client is not None:

            self.client = client

        elif http is not None:

            # Backward-compatible: an injected HttpClient drives the stdlib

            # backend (used by tests).

            self.client = ScihubClient.from_http(http)

        else:

            self.client = ScihubClient()



    def resolve(self, doi: str | None) -> list[SourceLink]:

        link = self.client.resolve_pdf_link(doi)

        return [link] if link else []
