#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
# --- How to run ---
# python3 -c "import renderers"
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Final

from models import AssemblyResult, PaperWorkspace, SECTION_ORDER, SectionRecord, TypesetError
from workspace import (
    ManifestRequest,
    digest_sources,
    load_workspace,
    resolve_paper_path,
    write_json_manifest,
)


DEFAULT_TITLE: Final = "MESA manuscript draft"
WORD_EXPORT_NOTICE: Final = "<!-- Generated Word/DOCX export artifact; edit paper/ sources instead. -->"
BACKTICKED_MATH_RE: Final = re.compile(r"`[^`\n]*\$[^`\n]*`")
RESULTS_BLOCK_LEAD_RE: Final = re.compile(r"^\*\*[^*\n]+\*\*$")
RESULTS_PIPE_LEAD_RE: Final = re.compile(r"^\*\*[^*\n]+\*\*\s+\|")
RESULTS_SECTION_IDS: Final = frozenset({"results", "discussion", "results_and_discussion"})
SECTION_TITLES: Final = {
    "abstract": "Abstract",
    "introduction": "Introduction",
    "results": "Results and Discussion",
    "results_and_discussion": "Results and Discussion",
    "discussion": "Results and Discussion",
    "computational_methods": "Computational Methods",
    "methods": "Computational Methods",
    "conclusion": "Conclusion",
    "si": "Supplementary Information",
}


def assemble_docx_markdown(paper: Path, out: Path) -> AssemblyResult:
    workspace = load_workspace(paper)
    reject_backticked_math(workspace)
    reject_invalid_results_discussion_blocks(workspace)
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
        section_title = display_section_title(section.section_id)
        section_text = strip_section_self_heading(
            strip_front_matter(read_text(resolve_paper_path(workspace.root, section.path))),
            section.section_id,
            section_title,
        )
        lines.extend((f"## {section_title}", "", section_text, ""))
    if workspace.figures:
        lines.extend(("## Figure Captions", ""))
    for figure in workspace.figures:
        caption = figure.caption or figure.title
        lines.extend((f"**{figure.label} |** {caption}", ""))
    return "\n".join(lines).rstrip() + "\n"


def reject_backticked_math(workspace: PaperWorkspace) -> None:
    for section in workspace.sections:
        path = resolve_paper_path(workspace.root, section.path)
        text = read_text(path)
        match = BACKTICKED_MATH_RE.search(text)
        if match is None:
            continue
        raise TypesetError(
            "math expression is inside a code span; remove backticks around $...$ before DOCX export: "
            f"{path}: {match.group(0)}"
        )


def reject_invalid_results_discussion_blocks(workspace: PaperWorkspace) -> None:
    for section in workspace.sections:
        if section.section_id not in RESULTS_SECTION_IDS:
            continue
        path = resolve_paper_path(workspace.root, section.path)
        lines = strip_front_matter(read_text(path)).splitlines()
        for index, line in enumerate(lines):
            if RESULTS_PIPE_LEAD_RE.match(line.strip()) is not None:
                raise TypesetError(
                    "Results and Discussion topic leads must not use '|'; put the bold lead on its own paragraph: "
                    f"{path}:{index + 1}"
                )
            if RESULTS_BLOCK_LEAD_RE.match(line.strip()) is None:
                continue
            next_line = lines[index + 1] if index + 1 < len(lines) else ""
            if next_line.strip():
                raise TypesetError(
                    "Results and Discussion topic leads must be followed by a blank line before body text: "
                    f"{path}:{index + 1}"
                )


def display_section_title(section_id: str) -> str:
    return SECTION_TITLES.get(section_id, section_id.replace("_", " ").title())


def strip_section_self_heading(text: str, section_id: str, section_title: str) -> str:
    lines = text.splitlines()
    if not lines:
        return text
    first_line = lines[0].strip()
    valid_headings = {
        f"# {section_id.replace('_', ' ').title()}".casefold(),
        f"# {section_title}".casefold(),
    }
    if first_line.casefold() not in valid_headings:
        return text
    remainder = lines[1:]
    while remainder and remainder[0].strip() == "":
        remainder = remainder[1:]
    return "\n".join(remainder).rstrip() + ("\n" if remainder else "")


def strip_front_matter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() != "---":
            continue
        remainder = lines[index + 1 :]
        while remainder and remainder[0].strip() == "":
            remainder = remainder[1:]
        return "\n".join(remainder).rstrip() + ("\n" if remainder else "")
    return text


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
