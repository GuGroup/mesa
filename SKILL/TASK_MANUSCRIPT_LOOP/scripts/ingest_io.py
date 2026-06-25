from __future__ import annotations

import argparse
from pathlib import Path
from typing import Final

from init_paper_workspace import SEED_FILES
from ingest_records import (
    CANONICAL_STRUCTURE,
    GENERATED_MARKER,
    SVG_GENERATED_MARKER,
    ResultRecord,
    SourceItem,
    WriteContext,
    read_json,
    fail,
    source_ref,
)


INIT_SEED_CONTENTS: Final[frozenset[str]] = frozenset(SEED_FILES.values())


def existing_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def paper_label(path: Path, paper: Path) -> str:
    try:
        return f"paper/{path.relative_to(paper).as_posix()}"
    except ValueError:
        return path.as_posix()


def is_generated_text(text: str) -> bool:
    return text.startswith((GENERATED_MARKER, SVG_GENERATED_MARKER)) or text in INIT_SEED_CONTENTS


def ensure_safe_paper_write_target(path: Path, paper: Path) -> None:
    paper_root = _absolute_path(paper)
    target = _absolute_path(path)
    try:
        relative_target = target.relative_to(paper_root)
    except ValueError:
        fail(f"write target outside paper root: {path}")
    if ".." in relative_target.parts:
        fail(f"write target escapes paper root: {path}")
    candidate = paper_root
    if candidate.is_symlink():
        fail(f"refusing to write through symlink under paper root: {candidate}")
    for part in relative_target.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            fail(f"refusing to write through symlink under paper root: {candidate}")


def _absolute_path(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


def safe_write(path: Path, content: str, context: WriteContext) -> None:
    ensure_safe_paper_write_target(path, context.paper)
    current = existing_text(path)
    if current == content:
        return
    if current and not context.force and not is_generated_text(current):
        context.preserved.append(paper_label(path, context.paper))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def safe_append(path: Path, content: str, context: WriteContext) -> None:
    ensure_safe_paper_write_target(path, context.paper)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(content)


def write_structure_from_selected_frame(src: Path, dst: Path, context: WriteContext) -> None:
    selected = src.read_text(encoding="utf-8").splitlines()
    atoms = [line.split(maxsplit=1)[0] for line in selected[2:] if line.strip()]
    positions = [
        parts[1] if len(parts) == 2 else "0.0 0.0 0.0"
        for parts in (line.split(maxsplit=1) for line in selected[2:] if line.strip())
    ]
    species = sorted(set(atoms))
    counts = [str(atoms.count(symbol)) for symbol in species]
    content = "\n".join(
        (
            "Generated from MESA analyzer selected_frames.extxyz",
            "1.0",
            "  1.000000 0.000000 0.000000",
            "  0.000000 1.000000 0.000000",
            "  0.000000 0.000000 1.000000",
            " ".join(species) if species else "X",
            " ".join(counts) if counts else "0",
            "Cartesian",
            *positions,
            "",
        )
    )
    safe_write(dst, content, context)


def write_result_files(paper: Path, record: ResultRecord, context: WriteContext) -> None:
    body = "\n".join(
        (
            f"system_id: {record.system_id}",
            f"method_id: {record.method_id}",
            f"status: {record.status}",
            f"quantity: {record.quantity}",
            f"value: {record.value}",
            f"units: {record.units}",
            "reference_state: gas_phase_CO_plus_clean_Pt111",
            f"source_artifact: {record.source_ref}",
            "notes: Fixture value for contract tests only; not a physical claim.",
            "",
        )
    )
    table = (
        "system,quantity,value,units,status,source_id\n"
        f"{record.system_id},{record.quantity},{record.value},{record.units},{record.status},{record.source_id}\n"
    )
    safe_write(paper / record.result_path.removeprefix("paper/"), body, context)
    safe_write(paper / "inputs/tables/energy_summary.csv", table, context)


def analyzer_items(input_root: Path, paper: Path, context: WriteContext) -> list[SourceItem]:
    items: list[SourceItem] = []
    resolved_input_root = input_root.resolve()
    for summary in sorted((input_root / "analyzer_runs").glob("*/analysis_summary.json")):
        data = read_json(summary)
        output_paths = data.get("output_paths")
        selected_name = "selected_frames.extxyz"
        if isinstance(output_paths, dict):
            selected_name = str(output_paths.get("selected_frames", selected_name))
        selected = (summary.parent / selected_name).resolve()
        try:
            selected.relative_to(resolved_input_root)
        except ValueError:
            fail(f"selected_frames path escapes input root: {selected_name}")
        structure_path = CANONICAL_STRUCTURE
        if selected.exists():
            write_structure_from_selected_frame(selected, paper / structure_path.removeprefix("paper/"), context)
        if not (paper / "inputs/figures/co_pt111_overlay.placeholder.txt").exists():
            safe_write(
                paper / "inputs/figures/co_pt111_overlay.placeholder.txt",
                "Placeholder for analyzer overlay images generated from completed MESA analysis.\n",
                context,
            )
        visual = summary.parent / "visual_review.md"
        items.append(
            SourceItem(
                "structure-co-pt111-final",
                "structure",
                structure_path,
                "TASK_CALCULATION_RESULT_ANALYZER",
                "primary",
                source_ref(summary, input_root),
                "not_applicable",
                "candidate-evidence",
                (),
            )
        )
        items.append(
            SourceItem(
                "figure-analyzer-overlay",
                "figure",
                "paper/inputs/figures/co_pt111_overlay.placeholder.txt",
                "TASK_CALCULATION_RESULT_ANALYZER",
                "supporting",
                source_ref(visual if visual.exists() else summary, input_root),
                "not_applicable",
                "context",
                (),
            )
        )
    return items


def manifest_yaml(items: list[SourceItem]) -> str:
    lines = ["version: 1", "project_id: fixture-co-pt111", "target: nature-family", "sources:"]
    for source in items:
        lines += [
            f"  - id: {source.id}",
            f"    kind: {source.kind}",
            f"    path: {source.path}",
            f"    source_task: {source.source_task}",
            f"    status: {source.status}",
            f"    provenance: {source.provenance}",
            f"    units: {source.units}",
            f"    claim_role: {source.claim_role}",
            "    blockers: []" if not source.blockers else f"    blockers: [{', '.join(source.blockers)}]",
        ]
    return "\n".join(lines) + "\n"


def inventory_markdown(records: list[ResultRecord]) -> str:
    rows = "\n".join(
        f"| {r.source_id} | {r.system_label} | {r.method_label} | {r.quantity_label} | {r.status} | {r.result_path} |"
        for r in records
    )
    return (
        "# Result Inventory\n\n## Primary Results\n\n"
        "| ID | System | Method | Quantity | Status | Source |\n| --- | --- | --- | --- | --- | --- |\n"
        f"{rows}\n\n## Structures\n\n| ID | Description | Status | Source |\n| --- | --- | --- | --- |\n"
        "| structure-co-pt111-final | Final CO/Pt(111) endpoint | converged fixture | paper/inputs/structures/CO_on_Pt111_POSCAR |\n\n"
        "## Known Caveats\n\n- Fixture values are placeholders for contract tests.\n"
        "- No literature or citation state is part of this v1 fixture.\n"
    )


def result_items(records: list[ResultRecord]) -> list[SourceItem]:
    return [
        SourceItem(r.source_id, "result", r.result_path, r.source_task, "primary", r.source_ref, r.units, "candidate-evidence", ())
        for r in records
    ]


def note_items(paper: Path) -> list[SourceItem]:
    if not (paper / "inputs/prior-notes/project-context.md").exists():
        return []
    return [
        SourceItem(
            "note-project-context",
            "note",
            "paper/inputs/prior-notes/project-context.md",
            "manual",
            "supporting",
            "fixture author note",
            "not_applicable",
            "context",
            (),
        )
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "I/O helpers for manuscript output ingestion. This module is imported "
            "by ingest_mesa_outputs.py; run that CLI to normalize completed MESA outputs."
        )
    )
    parser.parse_args()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
