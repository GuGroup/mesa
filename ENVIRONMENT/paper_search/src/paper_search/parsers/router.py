from __future__ import annotations

from pathlib import Path

from paper_search.models import DownloadedSource, ParseRun, Paper
from paper_search.parsers.grobid import GrobidParser
from paper_search.parsers.jats import JatsParser
from paper_search.parsers.opendataloader import OpenDataLoaderParser
from paper_search.servers import ManagedServer, ManagedServerConfig
from paper_search.utils import write_json


class ParserRouter:
    def __init__(
        self,
        grobid_url: str | None = None,
        grobid_server_config: ManagedServerConfig | None = None,
        opendataloader_cmd: str | None = None,
    ) -> None:
        self.jats = JatsParser()
        self.grobid = GrobidParser(grobid_url)
        self.grobid_server_config = grobid_server_config
        self.grobid_server: ManagedServer | None = None
        self.grobid_startup_error: str | None = None
        self.grobid_initialized = grobid_url is not None
        self.opendataloader = OpenDataLoaderParser(opendataloader_cmd)

    def __enter__(self) -> "ParserRouter":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        if self.grobid_server is not None:
            self.grobid_server.close()
            self.grobid_server = None

    def parse(
        self,
        paper: Paper,
        source: DownloadedSource,
        output_dir: Path,
    ) -> list[ParseRun]:
        runs: list[ParseRun] = []
        if source.source_type == "oa_xml":
            runs.append(self.jats.parse(paper.paper_id, source.local_path, output_dir))
        elif source.source_type == "oa_pdf":
            self._ensure_grobid()
            runs.append(self.grobid.parse(paper.paper_id, source.local_path, output_dir))
            if self.grobid_startup_error and runs[-1].status == "not_configured":
                runs[-1].error = (
                    "GROBID managed server could not start; continuing with "
                    f"OpenDataLoader. Startup error: {self.grobid_startup_error}"
                )
            runs.append(self.opendataloader.parse(paper.paper_id, source.local_path, output_dir))
        else:
            runs.append(
                ParseRun(
                    paper_id=paper.paper_id,
                    parser_name="router",
                    output_format="none",
                    output_path=output_dir / "none",
                    status="unsupported_source_type",
                    error=f"Unsupported source_type={source.source_type}",
                )
            )
        write_json(output_dir / "parse_manifest.json", [run.to_dict() for run in runs])
        return runs

    def _ensure_grobid(self) -> None:
        if self.grobid_initialized:
            return
        self.grobid_initialized = True
        if self.grobid_server_config is None:
            return
        self.grobid_server = ManagedServer(self.grobid_server_config)
        grobid_url = self.grobid_server.__enter__()
        self.grobid_startup_error = self.grobid_server.startup_error
        self.grobid = GrobidParser(grobid_url)


def best_blocks_path(parse_runs: list[ParseRun]) -> Path | None:
    preferred = ("jats", "grobid", "opendataloader")
    # Skip runs that report zero blocks so an empty-but-"ok" parse (e.g. a GROBID
    # TEI with no body paragraphs) does not win over a later parser that did
    # extract content. Runs without a block_count (default 1) are kept.
    ok_runs = [
        run
        for run in parse_runs
        if run.status == "ok" and run.parse_quality.get("block_count", 1) != 0
    ]
    for parser_name in preferred:
        for run in ok_runs:
            if run.parser_name == parser_name and run.output_path.name.endswith(".blocks.json"):
                return run.output_path
            candidate = run.output_path.with_name(f"{parser_name}.blocks.json")
            if run.parser_name == parser_name and candidate.exists():
                return candidate
    return None
