#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
# --- How to run ---
# python3 -c "import workspace"
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from models import BLOCKED_FIGURE_STATUSES, ContractFiles, PaperWorkspace, TypesetError
from yaml_contract import parse_claims, parse_figures, parse_sections, validate_notation


@dataclass(frozen=True)  # noqa: SLOTS_OK -- verifier uses Python 3.9, where dataclass slots are unavailable.
class ManifestRequest:
    path: Path
    workspace: PaperWorkspace
    source_digest: str
    mode: str


def load_workspace(paper: Path) -> PaperWorkspace:
    root = paper.resolve()
    if not root.is_dir():
        raise TypesetError(f"paper root does not exist or is not a directory: {paper}")

    files = contract_files(root)
    for path in files.as_tuple():
        require_file(path, root)

    sections = parse_sections(files.sections)
    claims = parse_claims(files.claims)
    figures = parse_figures(files.figures)
    validate_notation(files.notation)
    workspace = PaperWorkspace(root, sections, claims, figures, ())
    validate_crossrefs(workspace)
    sources = collect_sources(workspace, files.as_tuple())
    return PaperWorkspace(root, sections, claims, figures, tuple(sorted(sources)))


def contract_files(root: Path) -> ContractFiles:
    return ContractFiles(
        root / "manuscript" / "outline.md",
        root / "manuscript" / "section-contracts.yaml",
        root / "manuscript" / "references.bib",
        root / "logic" / "claim-matrix.yaml",
        root / "logic" / "figure-map.yaml",
        root / "logic" / "notation.yaml",
    )


def require_file(path: Path, root: Path) -> None:
    if not path.is_file():
        raise TypesetError(f"required file is missing: {path.relative_to(root)}")


def collect_sources(workspace: PaperWorkspace, required: tuple[Path, ...]) -> set[Path]:
    sources = set(required)
    for section in workspace.sections:
        sources.add(resolve_paper_path(workspace.root, section.path))
        sources.update(resolve_paper_path(workspace.root, path) for path in section.required_sources)
    for claim in workspace.claims:
        sources.update(resolve_paper_path(workspace.root, path) for path in claim.evidence_paths)
    for figure in workspace.figures:
        paths = figure.source_files + figure.exported_files + figure.qa_files
        sources.update(resolve_paper_path(workspace.root, path) for path in paths)
    for path in tuple(sources):
        require_file(path, workspace.root)
    return sources


def validate_crossrefs(workspace: PaperWorkspace) -> None:
    claim_ids = frozenset(claim.claim_id for claim in workspace.claims)
    figures_by_id = {figure.figure_id: figure for figure in workspace.figures}
    for section in workspace.sections:
        for claim_id in section.allowed_claims:
            if claim_id not in claim_ids:
                raise TypesetError(f"section {section.section_id} allows unknown claim {claim_id}")
        for figure_id in section.required_figures:
            figure = figures_by_id.get(figure_id)
            if figure is None:
                raise TypesetError(f"section {section.section_id} requires unknown figure {figure_id}")
            if figure.status in BLOCKED_FIGURE_STATUSES:
                raise TypesetError(f"section {section.section_id} requires unavailable figure {figure_id}")
    for claim in workspace.claims:
        for figure_id in claim.figures:
            if figure_id not in figures_by_id:
                raise TypesetError(f"claim {claim.claim_id} references unknown figure {figure_id}")


def resolve_paper_path(root: Path, path_text: str) -> Path:
    requested = Path(path_text)
    if requested.is_absolute() or requested.parts[:1] != ("paper",):
        raise TypesetError(f"path must be paper-relative: {path_text}")
    paper_root = root.resolve()
    resolved = (paper_root.joinpath(*requested.parts[1:])).resolve()
    try:
        resolved.relative_to(paper_root)
    except ValueError as exc:
        raise TypesetError(f"path escapes paper root: {path_text}") from exc
    return resolved


def digest_sources(paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def assert_fresh_generated_state(output: Path, source_digest: str) -> None:
    manifest = output / "build-manifest.json"
    pdf = output / "manuscript.pdf"
    if not manifest.is_file() or not pdf.exists():
        return
    try:
        previous = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TypesetError(f"existing build manifest is malformed: {manifest}") from exc
    previous_digest = previous.get("source_digest")
    if previous_digest != source_digest:
        raise TypesetError("existing manuscript.pdf is stale relative to current paper sources; rebuild without --check-only")


def write_json_manifest(request: ManifestRequest) -> None:
    workspace = request.workspace
    data = {
        "claims": [claim.claim_id for claim in workspace.claims],
        "figures": [figure.figure_id for figure in workspace.figures],
        "mode": request.mode,
        "paper": str(workspace.root),
        "sections": [section.section_id for section in workspace.sections],
        "source_digest": request.source_digest,
        "sources": [str(path) for path in workspace.source_files],
    }
    request.path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Workspace loading, cross-reference checks, source digesting, and manifest "
            "writing helpers for TASK_MANUSCRIPT_TYPESET. Import this module from "
            "build/export code; use build_typst.py or export_docx.py for executable CLIs."
        )
    )
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
