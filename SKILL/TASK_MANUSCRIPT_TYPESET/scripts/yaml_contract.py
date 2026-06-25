#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
# --- How to run ---
# python3 -c "import yaml_contract"
from __future__ import annotations

import argparse
import re
from pathlib import Path

from models import ClaimRecord, FigureRecord, SectionRecord, TypesetError


def parse_sections(source: Path) -> tuple[SectionRecord, ...]:
    text = read_text(source)
    require_version(source, text)
    records = tuple(parse_section_block(source, block) for block in split_record_blocks(text, "sections"))
    if not records:
        raise TypesetError(f"section contract has no sections: {source}")
    return records


def parse_claims(source: Path) -> tuple[ClaimRecord, ...]:
    text = read_text(source)
    require_version(source, text)
    records = tuple(parse_claim_block(source, block) for block in split_record_blocks(text, "claims"))
    if not records:
        raise TypesetError(f"claim matrix has no claims: {source}")
    return records


def parse_figures(source: Path) -> tuple[FigureRecord, ...]:
    text = read_text(source)
    require_version(source, text)
    records = tuple(parse_figure_block(source, block) for block in split_record_blocks(text, "figures"))
    if not records:
        raise TypesetError(f"figure map has no figures: {source}")
    return records


def validate_notation(source: Path) -> None:
    text = read_text(source)
    require_version(source, text)
    for key in ("systems", "methods", "energies", "figures", "abbreviations"):
        if not re.search(rf"(?m)^{re.escape(key)}:\s*$", text):
            raise TypesetError(f"notation file missing required category {key!r}: {source}")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def require_version(source: Path, text: str) -> None:
    if not re.search(r"(?m)^version:\s*1\s*$", text):
        raise TypesetError(f"missing supported version header in {source}")


def split_record_blocks(text: str, key: str) -> tuple[tuple[str, ...], ...]:
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line == f"{key}:"), -1)
    if start < 0:
        return ()
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines[start + 1 :]:
        if line and not line.startswith(" "):
            break
        if line.startswith("  - "):
            if current:
                blocks.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        blocks.append(current)
    return tuple(tuple(block) for block in blocks)


def parse_section_block(source: Path, block: tuple[str, ...]) -> SectionRecord:
    return SectionRecord(
        source,
        required_scalar(block, "id", source),
        required_scalar(block, "path", source),
        required_scalar(block, "status", source),
        parse_list(block, "allowed_claims"),
        parse_list(block, "required_figures"),
        parse_list(block, "required_sources"),
        parse_list(block, "blocked_by"),
    )


def parse_claim_block(source: Path, block: tuple[str, ...]) -> ClaimRecord:
    return ClaimRecord(
        source,
        required_scalar(block, "id", source),
        required_scalar(block, "status", source),
        parse_list(block, "figures"),
        tuple(clean_scalar(match.group(1)) for match in re.finditer(r"^\s+path:\s*(.+)$", "\n".join(block), re.M)),
    )


def parse_figure_block(source: Path, block: tuple[str, ...]) -> FigureRecord:
    return FigureRecord(
        source,
        required_scalar(block, "id", source),
        required_scalar(block, "label", source),
        required_scalar(block, "title", source),
        required_scalar(block, "status", source),
        parse_list(block, "source_files"),
        parse_list(block, "exported_files"),
        parse_list(block, "qa_files"),
    )


def required_scalar(block: tuple[str, ...], key: str, source: Path) -> str:
    value = scalar_value(block, key)
    if not value:
        raise TypesetError(f"missing required field {key!r} in {source}")
    return value


def scalar_value(block: tuple[str, ...], key: str) -> str:
    pattern = re.compile(rf"^\s*(?:-\s*)?{re.escape(key)}:\s*(.+)$")
    for line in block:
        match = pattern.match(line)
        if match:
            return clean_scalar(match.group(1))
    return ""


def parse_list(block: tuple[str, ...], key: str) -> tuple[str, ...]:
    inline = scalar_value(block, key)
    if inline.startswith("[") and inline.endswith("]"):
        body = inline[1:-1].strip()
        if not body:
            return ()
        return tuple(clean_scalar(item) for item in body.split(","))
    values: list[str] = []
    pattern = re.compile(rf"^\s+{re.escape(key)}:\s*$\n((?:\s+- .+\n?)*)", re.M)
    match = pattern.search("\n".join(block))
    if match:
        values.extend(clean_scalar(line.strip()[2:]) for line in match.group(1).splitlines() if line.strip())
    return tuple(values)


def clean_scalar(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Minimal YAML contract parser helpers for TASK_MANUSCRIPT_TYPESET. Import this "
            "module to parse section, claim, figure, and notation contracts; validators "
            "and build/export CLIs perform user-facing checks."
        )
    )
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
