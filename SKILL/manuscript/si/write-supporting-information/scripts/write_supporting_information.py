#!/usr/bin/env python3
"""Write minimal Supporting Information section JSON from a manuscript DOCX."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.numeric_precision import format_numeric_precision, overprecise_decimal_literals


SCHEMA_VERSION = 1
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
TARGET_PLACEHOLDERS = {
    "si_large_content_title": "{{SI_LARGE_CONTENT_TITLE}}",
    "si_large_content_text": "{{SI_LARGE_CONTENT_TEXT}}",
    "si_small_content_title": "{{SI_SMALL_CONTENT_TITLE}}",
    "si_small_content_text": "{{SI_SMALL_CONTENT_TEXT}}",
    "dft_calculation_details": "{{DENSITY_FUNCTIONAL_THEORY_CALCULATION_DETAILS_TEXT}}",
}


def compact_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def paragraph_text(p: ET.Element) -> str:
    return "".join(t.text or "" for t in p.findall(".//w:t", NS))


def paragraph_style(p: ET.Element) -> str:
    style = p.find("./w:pPr/w:pStyle", NS)
    return style.get(f"{{{NS['w']}}}val") if style is not None else ""


def extract_paragraphs(path: Path) -> list[dict[str, Any]]:
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    paragraphs = []
    for index, p in enumerate(root.findall(".//w:body/w:p", NS), start=1):
        text = compact_text(paragraph_text(p))
        if text:
            paragraphs.append({"index": index, "style": paragraph_style(p), "text": text})
    return paragraphs


def default_outdir(manuscript_docx: Path, strategy_id: str) -> Path:
    parts = list(manuscript_docx.parts)
    for idx, part in enumerate(parts):
        if part == "project" and idx + 1 < len(parts):
            return Path(*parts[: idx + 2]) / "strategy_execution" / f"{strategy_id}_si" / "text"
    return manuscript_docx.parent / f"{strategy_id}_si" / "text"


def extract_si_captions(paragraphs: list[dict[str, Any]]) -> list[str]:
    return [item["text"] for item in paragraphs if re.match(r"^Fig\.\s*S\d+\s*\|", item["text"])]


def extract_geometry_details(paragraphs: list[dict[str, Any]]) -> list[str]:
    details: list[str] = []
    capture = False
    for item in paragraphs:
        text = item["text"]
        if re.match(r"^(Geometry optimization|Computational details|Calculation details|DFT calculation details)\b", text, flags=re.IGNORECASE):
            capture = True
            details.append(text)
            continue
        if capture and re.match(r"^(Relaxations used|A total of \d+ .* structures were relaxed|Convergence|Electronic-structure|Vibrational|Free-energy)\b", text, flags=re.IGNORECASE):
            details.append(text)
            continue
        if capture and re.match(r"^(Electrochemical free-energy formalism|Results and Discussion|References|Supporting Information)\b", text):
            break
    return details


def section_payload(strategy_id: str, manuscript_docx: Path, placeholder_key: str, section_id: str, paragraphs: list[str]) -> dict[str, Any]:
    blocks = [{"type": "paragraph", "text": format_numeric_precision(text)} for text in paragraphs if compact_text(text)]
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": strategy_id,
        "source_manuscript_docx": str(manuscript_docx),
        "target_placeholders": {"text": TARGET_PLACEHOLDERS[placeholder_key]},
        "sections": [
            {
                "section_id": section_id,
                "title": "",
                "small_title": "",
                "render_title": False,
                "text": "\n\n".join(block["text"] for block in blocks),
                "content_blocks": blocks,
            }
        ],
        "missing_details": [],
    }


def build_si(paragraphs: list[dict[str, Any]]) -> dict[str, Any]:
    captions = extract_si_captions(paragraphs)
    geometry_details = extract_geometry_details(paragraphs)
    if captions:
        large_text = "Supplementary figure content provides additional structural views supporting the model and adsorbate configurations discussed in the main text."
        small_text = "Side and top views of the optimized configurations are provided to show the local geometries used for computational analysis."
    else:
        large_text = "No supplementary figure content was detected in the manuscript DOCX."
        small_text = "No supplementary local-geometry figure content was detected in the manuscript DOCX."
    return {
        "si_large_content_title": format_numeric_precision("1. Supplementary figures"),
        "si_large_content_text": format_numeric_precision(large_text),
        "si_small_content_title": format_numeric_precision("1.1. Optimized local geometries"),
        "si_small_content_text": format_numeric_precision(small_text),
        "dft_calculation_details": {"paragraphs": [format_numeric_precision(text) for text in geometry_details]},
        "detected_si_captions": captions,
    }


def validate_si(si: dict[str, Any]) -> dict[str, Any]:
    details = si["dft_calculation_details"]["paragraphs"]
    text = "\n".join(
        [
            si["si_large_content_title"],
            si["si_large_content_text"],
            si["si_small_content_title"],
            si["si_small_content_text"],
            "\n".join(details),
        ]
    )
    forbidden = [
        pattern
        for pattern in [r"\bprocedure\b", r"\bworkflow\b", r"\bdigest\b", r"\bJSON\b", r"\bfuture work\b", r"\blimitation(?:s)?\b"]
        if re.search(pattern, text, flags=re.IGNORECASE)
    ]
    overprecise = overprecise_decimal_literals(text)
    return {
        "ok": bool(si["si_large_content_title"]) and bool(si["si_small_content_title"]) and not forbidden and not overprecise,
        "si_caption_count": len(si["detected_si_captions"]),
        "dft_detail_paragraph_count": len(details),
        "forbidden_patterns": forbidden,
        "overprecise_decimal_literals": overprecise,
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = ["# Supporting Information Text", ""]
    lines.extend([f"## {payload['si_large_content_title']}", "", payload["si_large_content_text"], ""])
    lines.extend([f"## {payload['si_small_content_title']}", "", payload["si_small_content_text"], ""])
    lines.extend(["## 2. Density functional theory calculation details", ""])
    for paragraph in payload["dft_calculation_details"]["paragraphs"]:
        lines.extend([paragraph, ""])
    lines.extend(["## Validation", "", f"- ok: {payload['validation']['ok']}", ""])
    write_text(path, "\n".join(lines))


def run(args: argparse.Namespace) -> dict[str, Any]:
    manuscript_docx = Path(args.manuscript_docx)
    strategy_id = args.strategy_id
    outdir = Path(args.outdir) if args.outdir else default_outdir(manuscript_docx, strategy_id)
    si = build_si(extract_paragraphs(manuscript_docx))
    validation = validate_si(si)
    section_paths = {
        "si_large_content_title": "si_large_content_title_section_text.json",
        "si_large_content_text": "si_large_content_text_section_text.json",
        "si_small_content_title": "si_small_content_title_section_text.json",
        "si_small_content_text": "si_small_content_text_section_text.json",
        "dft_calculation_details": "dft_calculation_details_section_text.json",
    }
    payloads = {
        "si_large_content_title": section_payload(strategy_id, manuscript_docx, "si_large_content_title", "si_large_content_title", [si["si_large_content_title"]]),
        "si_large_content_text": section_payload(strategy_id, manuscript_docx, "si_large_content_text", "si_large_content_text", [si["si_large_content_text"]]),
        "si_small_content_title": section_payload(strategy_id, manuscript_docx, "si_small_content_title", "si_small_content_title", [si["si_small_content_title"]]),
        "si_small_content_text": section_payload(strategy_id, manuscript_docx, "si_small_content_text", "si_small_content_text", [si["si_small_content_text"]]),
        "dft_calculation_details": section_payload(strategy_id, manuscript_docx, "dft_calculation_details", "dft_calculation_details", si["dft_calculation_details"]["paragraphs"]),
    }
    for key, payload in payloads.items():
        write_json(outdir / section_paths[key], payload)
    combined = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": strategy_id,
        "source_manuscript_docx": str(manuscript_docx),
        **si,
        "section_json_paths": section_paths,
        "validation": validation,
    }
    write_json(outdir / "supporting_information_text.json", combined)
    write_markdown(outdir / "supporting_information_text.md", combined)
    if not validation["ok"]:
        raise SystemExit("Supporting Information output failed validation. See supporting_information_text.json.")
    return combined


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manuscript-docx", required=True, help="Assembled manuscript DOCX.")
    parser.add_argument("--strategy-id", default="S1", help="Strategy id used for output naming.")
    parser.add_argument("--outdir", default="", help="Output directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = run(args)
    outdir = Path(args.outdir) if args.outdir else default_outdir(Path(args.manuscript_docx), args.strategy_id)
    print(f"Wrote {outdir / 'supporting_information_text.json'}")
    for path in payload["section_json_paths"].values():
        print(f"Wrote {outdir / path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
