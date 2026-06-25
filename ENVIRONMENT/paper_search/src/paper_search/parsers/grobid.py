from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from paper_search.http import DEFAULT_USER_AGENT
from paper_search.models import ParseRun
from paper_search.parsers.xml_blocks import blocks_to_dicts, parse_xml_blocks
from paper_search.utils import write_json


class GrobidParser:
    name = "grobid"

    def __init__(self, endpoint: str | None = None, timeout: int = 120) -> None:
        self.endpoint = _endpoint(endpoint) if endpoint else None
        self.timeout = timeout

    def parse(self, paper_id: str, source_path: Path, output_dir: Path) -> ParseRun:
        if not self.endpoint:
            return ParseRun(
                paper_id=paper_id,
                parser_name=self.name,
                output_format="tei_xml",
                output_path=output_dir / "grobid.tei.xml",
                status="not_configured",
                error=(
                    "GROBID endpoint is not configured. This is optional; PDF "
                    "parsing can continue with OpenDataLoader."
                ),
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "grobid.tei.xml"
        try:
            output_path.write_bytes(self._process_pdf(source_path))
            blocks = parse_xml_blocks(output_path, paper_id, self.name)
            blocks_path = output_dir / "grobid.blocks.json"
            write_json(blocks_path, blocks_to_dicts(blocks))
            return ParseRun(
                paper_id=paper_id,
                parser_name=self.name,
                output_format="tei_xml",
                output_path=output_path,
                status="ok",
                parse_quality={
                    "block_count": len(blocks),
                    "section_count": len({block.section for block in blocks if block.section}),
                    "figure_caption_count": sum(
                        1 for block in blocks if block.block_type == "figure_caption"
                    ),
                },
            )
        except (RuntimeError, ET.ParseError) as exc:
            # ET.ParseError (a SyntaxError, not a RuntimeError) is raised when
            # GROBID returns HTTP 200 with a non-TEI body (e.g. an HTML error
            # page). Catch it here so the router still falls back to
            # OpenDataLoader instead of killing the paper with a parse_error.
            return ParseRun(
                paper_id=paper_id,
                parser_name=self.name,
                output_format="tei_xml",
                output_path=output_path,
                status="failed",
                error=str(exc),
            )

    def _process_pdf(self, source_path: Path) -> bytes:
        boundary = f"----paper-search-{uuid.uuid4().hex}"
        data = _multipart_pdf(source_path, boundary)
        request = Request(
            self.endpoint or "",
            data=data,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/xml,text/xml,*/*",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except HTTPError as exc:
            body = exc.read()
            raise RuntimeError(f"GROBID HTTP {exc.code}: {body[:300]!r}") from exc
        except URLError as exc:
            raise RuntimeError(f"GROBID request failed: {exc.reason}") from exc


def _endpoint(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/api/processFulltextDocument"):
        return endpoint
    return f"{endpoint}/api/processFulltextDocument"


def _multipart_pdf(source_path: Path, boundary: str) -> bytes:
    content = source_path.read_bytes()
    lines = [
        f"--{boundary}\r\n".encode(),
        (
            'Content-Disposition: form-data; name="input"; '
            f'filename="{source_path.name}"\r\n'
        ).encode(),
        b"Content-Type: application/pdf\r\n\r\n",
        content,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(lines)
