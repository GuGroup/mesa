from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from paper_search.models import DownloadedSource, Paper
from paper_search.utils import read_json


def stage_error(stage: str, paper: Paper | None, exc: BaseException) -> dict[str, str]:
    error = {
        "stage": stage,
        "error_type": type(exc).__name__,
        "error": str(exc),
    }
    if paper is not None:
        error["paper_id"] = paper.paper_id
    return error


def append_stage_error(
    paper_record: dict[str, Any],
    harness_errors: list[dict[str, str]],
    stage: str,
    paper: Paper,
    exc: BaseException,
) -> None:
    error = stage_error(stage, paper, exc)
    paper_record["stage_errors"].append(error)
    harness_errors.append(error)


def research_context_dict(research: object) -> dict[str, Any]:
    data = asdict(research)
    return {key: value for key, value in data.items() if value not in (None, "", [], {})}


def new_record(paper: Paper) -> dict[str, Any]:
    return {
        "paper": paper.to_dict(),
        "resolver_errors": [],
        "resolved_link_count": 0,
        "downloaded_source": None,
        "download_errors": [],
        "parse_runs": [],
        "claim_count": 0,
        "stage_errors": [],
        "status": "full_text_unavailable",
    }


def papers_by_id(papers: list[Paper]) -> dict[str, Paper]:
    return {paper.paper_id: paper for paper in papers}


def downloaded_source_from_dict(data: dict[str, Any]) -> DownloadedSource:
    payload = dict(data)
    payload["local_path"] = Path(payload["local_path"])
    return DownloadedSource(**payload)


def blocks_to_text(blocks_path: str | Path, max_chars: int = 60000) -> str:
    """Concatenate parsed block text (with light section headers) into one string."""
    blocks = read_json(Path(blocks_path))
    parts: list[str] = []
    last_section: str | None = None
    for block in blocks:
        text = (block.get("text") or "").strip()
        if not text:
            continue
        section = block.get("section")
        if section and section != last_section:
            parts.append(f"\n## {section}\n")
            last_section = section
        parts.append(text)
    joined = "\n".join(parts).strip()
    return joined[:max_chars]
