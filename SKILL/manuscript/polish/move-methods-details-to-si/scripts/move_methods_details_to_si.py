#!/usr/bin/env python3
"""Move detailed geometry-optimization Methods text into SI by compressing Methods in a DOCX."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16se": "http://schemas.microsoft.com/office/word/2015/wordml/symex",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16": "http://schemas.microsoft.com/office/word/2018/wordml",
    "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
    "w16sdtdh": "http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "v": "urn:schemas-microsoft-com:vml",
    "o": "urn:schemas-microsoft-com:office:office",
    "w10": "urn:schemas-microsoft-com:office:word",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
DEFAULT_CONFIG = {
    "start_patterns": [r"^Geometry optimization\b"],
    "continuation_patterns": [
        r"^Relaxations used\b",
        r"^A total of \d+ .* structures were relaxed\b",
        r"\bconverg",
        r"\brelax",
    ],
    "replacement_text": (
        "Geometry optimization Geometry optimizations were performed consistently for the modeled structures; "
        "the detailed relaxation settings and convergence information are provided in the Supporting Information."
    ),
}


def qn(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def compact_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def combined_text(p: ET.Element) -> str:
    return "".join(t.text or "" for t in p.findall(".//w:t", NS))


def paragraph_ppr(p: ET.Element | None) -> ET.Element | None:
    if p is None:
        return None
    ppr = p.find("./w:pPr", NS)
    return deepcopy(ppr) if ppr is not None else None


def make_paragraph(text: str, ppr: ET.Element | None = None) -> ET.Element:
    p = ET.Element(qn("w", "p"))
    if ppr is not None:
        p.append(deepcopy(ppr))
    run = ET.SubElement(p, qn("w", "r"))
    t = ET.SubElement(run, qn("w", "t"))
    if text.startswith(" ") or text.endswith(" "):
        t.set(XML_SPACE, "preserve")
    t.text = text
    return p


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def restore_document_namespace_declarations(serialized: bytes, original: bytes) -> bytes:
    text = serialized.decode("utf-8")
    original_text = original.decode("utf-8", errors="replace")
    original_root_match = re.search(r"<w:document\b[^>]*>", original_text)
    new_root_match = re.search(r"<w:document\b[^>]*>", text)
    if not original_root_match or not new_root_match:
        return serialized
    original_root = original_root_match.group(0)
    new_root = new_root_match.group(0)
    original_decls = re.findall(r'\sxmlns:([A-Za-z0-9_]+)="([^"]+)"', original_root)
    existing = set(re.findall(r'\sxmlns:([A-Za-z0-9_]+)=', new_root))
    additions = "".join(f' xmlns:{prefix}="{uri}"' for prefix, uri in original_decls if prefix not in existing)
    if not additions:
        return serialized
    return text.replace(new_root, new_root[:-1] + additions + ">", 1).encode("utf-8")


def write_docx(template: Path, output: Path, document_xml: bytes) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(template, "r") as zin:
        infos = zin.infolist()
        parts = {info.filename: zin.read(info.filename) for info in infos}
    parts["word/document.xml"] = document_xml
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in infos:
            if info.filename in parts:
                zout.writestr(info, parts.pop(info.filename))
        for filename, payload in parts.items():
            zout.writestr(filename, payload)


def load_config(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return DEFAULT_CONFIG
    data = json.loads(path.read_text(encoding="utf-8"))
    config = dict(DEFAULT_CONFIG)
    if isinstance(data, dict):
        config.update(data)
    return config


def matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def find_detail_block(body: ET.Element, config: dict[str, Any]) -> tuple[int, int]:
    children = list(body)
    start = None
    end = None
    start_patterns = [str(item) for item in config.get("start_patterns", [])]
    continuation_patterns = [str(item) for item in config.get("continuation_patterns", [])]
    for idx, child in enumerate(children):
        if child.tag != qn("w", "p"):
            continue
        text = compact_text(combined_text(child))
        if matches_any(text, start_patterns):
            start = idx
            end = idx + 1
            continue
        if start is not None and end == idx:
            if matches_any(text, continuation_patterns):
                end = idx + 1
                continue
            break
    if start is None or end is None or end <= start:
        raise ValueError("Could not locate the configured Methods detail block.")
    return start, end


def move_details(input_docx: Path, output_docx: Path, config: dict[str, Any]) -> dict[str, Any]:
    if input_docx.resolve() == output_docx.resolve():
        raise SystemExit("Refusing to overwrite the input DOCX.")
    with zipfile.ZipFile(input_docx, "r") as zin:
        original_xml = zin.read("word/document.xml")
    document = ET.fromstring(original_xml)
    body = document.find(".//w:body", NS)
    if body is None:
        raise ValueError("DOCX document body not found.")
    replacement = str(config.get("replacement_text") or DEFAULT_CONFIG["replacement_text"])
    start, end = find_detail_block(body, config)
    children = list(body)
    removed = [compact_text(combined_text(child)) for child in children[start:end] if child.tag == qn("w", "p")]
    ppr = paragraph_ppr(children[start])
    for child in children[start:end]:
        body.remove(child)
    body.insert(start, make_paragraph(replacement, ppr))
    serialized = ET.tostring(document, encoding="utf-8", xml_declaration=True)
    serialized = restore_document_namespace_declarations(serialized, original_xml)
    write_docx(input_docx, output_docx, serialized)

    with zipfile.ZipFile(output_docx, "r") as zout:
        root = ET.fromstring(zout.read("word/document.xml"))
    all_text = "\n".join(compact_text(combined_text(p)) for p in root.findall(".//w:body/w:p", NS))
    removed_present_counts = {paragraph: all_text.count(paragraph) for paragraph in removed if paragraph}
    validation = {
        "removed_paragraph_count": len(removed),
        "replacement_present": replacement in all_text,
        "removed_paragraphs_not_duplicated": all(count <= 1 for count in removed_present_counts.values()),
    }
    validation["ok"] = bool(removed) and bool(validation["replacement_present"]) and bool(validation["removed_paragraphs_not_duplicated"])
    return {
        "schema_version": 1,
        "input_docx": str(input_docx),
        "output_docx": str(output_docx),
        "mode": "replace-geometry-optimization-block",
        "removed_paragraphs": removed,
        "replacement_paragraph": replacement,
        "config": config,
        "validation": validation,
        "warnings": [] if validation["ok"] else ["Move validation failed; inspect DOCX text manually."],
    }


def report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Methods To SI Move Report", "", f"- Output DOCX: `{report['output_docx']}`", f"- ok: `{report['validation']['ok']}`", ""]
    lines.extend(["## Replacement", "", report["replacement_paragraph"], ""])
    lines.extend(["## Removed Paragraphs", ""])
    for paragraph in report["removed_paragraphs"]:
        lines.append(f"- {paragraph}")
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-docx", required=True, help="DOCX with SI details already inserted.")
    parser.add_argument("--output-docx", required=True, help="Output DOCX with compressed Methods.")
    parser.add_argument("--report-json", default="", help="Optional report JSON path.")
    parser.add_argument("--report-md", default="", help="Optional report Markdown path.")
    parser.add_argument("--config", default="", help="Optional JSON config with start_patterns, continuation_patterns, and replacement_text.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = move_details(Path(args.input_docx), Path(args.output_docx), load_config(Path(args.config) if args.config else None))
    output = Path(args.output_docx)
    report_json = Path(args.report_json) if args.report_json else output.with_suffix(".methods_to_si_report.json")
    report_md = Path(args.report_md) if args.report_md else output.with_suffix(".methods_to_si_report.md")
    write_json(report_json, report)
    write_text(report_md, report_markdown(report))
    print(f"Wrote {output}")
    print(f"Wrote {report_json}")
    print(f"Wrote {report_md}")
    if not report["validation"]["ok"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
