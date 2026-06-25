from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote


DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    doi = DOI_PREFIX_RE.sub("", doi.strip())
    doi = doi.rstrip(".,;")
    return doi.lower() or None


def doi_to_paper_id(doi: str | None, title: str | None = None) -> str:
    if doi:
        digest_input = normalize_doi(doi) or doi
    else:
        digest_input = normalize_text(title or "untitled")
    return hashlib.sha1(digest_input.encode("utf-8")).hexdigest()[:16]


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text).strip().lower()


def title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", normalize_text(title))[:120]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def quote_doi(doi: str) -> str:
    return quote(doi, safe="")


def guess_source_type(url: str, content_type: str | None = None) -> str:
    content_type = (content_type or "").lower()
    lower_url = url.lower()
    # Match the extension on the path only: OA PDF/XML URLs frequently carry a
    # query or fragment (e.g. ".../v1.pdf?c=1631870895000"), which would defeat a
    # bare endswith on the full URL.
    path = lower_url.split("?", 1)[0].split("#", 1)[0]
    if "xml" in content_type or path.endswith(".xml") or "jats" in lower_url:
        return "oa_xml"
    if "pdf" in content_type or path.endswith(".pdf") or "/pdf" in lower_url:
        return "oa_pdf"
    return "unknown"
