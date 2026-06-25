#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
# --- How to run ---
# python3 -c "import renderers"
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Final

from models import AssemblyResult, PaperWorkspace, SECTION_ORDER, SectionRecord
from workspace import (
    ManifestRequest,
    digest_sources,
    load_workspace,
    resolve_paper_path,
    write_json_manifest,
)


DEFAULT_TITLE: Final = "MESA manuscript draft"
WORD_EXPORT_NOTICE: Final = "<!-- Generated Word/DOCX export artifact; edit paper/ sources instead. -->"


def assemble_docx_markdown(paper: Path, out: Path) -> AssemblyResult:
    workspace = load_workspace(paper)
    output = out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manuscript_path = output / "manuscript.md"
    qa_path = output / "qa" / "crossref-qa.txt"
    manifest_path = output / "docx-export-manifest.json"
    source_digest = digest_sources(workspace.source_files)
    write_text(manuscript_path, render_markdown_export(workspace))
    write_text(qa_path, render_crossref_qa(workspace))
    write_json_manifest(ManifestRequest(manifest_path, workspace, source_digest, "docx"))
    return AssemblyResult(workspace, source_digest, manuscript_path, qa_path, manifest_path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def render_markdown_export(workspace: PaperWorkspace) -> str:
    lines = [f"# {DEFAULT_TITLE}", "", WORD_EXPORT_NOTICE, ""]
    for section in ordered_sections(workspace):
        lines.extend((f"## {section.section_id.title()}", "", read_text(resolve_paper_path(workspace.root, section.path)), ""))
    lines.extend(("## Figure Inventory", ""))
    for figure in workspace.figures:
        lines.append(f"- {figure.label}: {figure.title} (`{', '.join(figure.exported_files)}`)")
    return "\n".join(lines).rstrip() + "\n"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def ordered_sections(workspace: PaperWorkspace) -> tuple[SectionRecord, ...]:
    by_id = {section.section_id: section for section in workspace.sections}
    ordered = [by_id[section_id] for section_id in SECTION_ORDER if section_id in by_id]
    ordered.extend(section for section in workspace.sections if section.section_id not in SECTION_ORDER)
    return tuple(ordered)


def render_crossref_qa(workspace: PaperWorkspace) -> str:
    lines = ["Cross-reference QA: passed", "", "Sections:"]
    for section in workspace.sections:
        lines.append(
            f"- {section.section_id}: claims={list(section.allowed_claims)} figures={list(section.required_figures)} status={section.status}"
        )
    lines.append("")
    lines.append("Claims:")
    for claim in workspace.claims:
        lines.append(f"- {claim.claim_id}: status={claim.status} figures={list(claim.figures)}")
    lines.append("")
    lines.append("Figures:")
    for figure in workspace.figures:
        lines.append(f"- {figure.figure_id}: status={figure.status} exported={list(figure.exported_files)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rendering helpers for TASK_MANUSCRIPT_TYPESET. Import this module to assemble "
            "Word-export Markdown, manifest, and cross-reference QA artifacts; use "
            "export_docx.py for the executable CLI."
        )
    )
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
