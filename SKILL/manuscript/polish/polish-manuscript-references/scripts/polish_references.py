#!/usr/bin/env python3
"""Normalize main numeric references in a DOCX from config."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main", "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006", "w14": "http://schemas.microsoft.com/office/word/2010/wordml"}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


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


def first_run_rpr(p: ET.Element | None) -> ET.Element | None:
    if p is None:
        return None
    run = p.find("./w:r", NS)
    if run is None:
        return None
    rpr = run.find("./w:rPr", NS)
    return deepcopy(rpr) if rpr is not None else None


def make_paragraph(text: str, ppr: ET.Element | None, rpr: ET.Element | None) -> ET.Element:
    p = ET.Element(qn("w", "p"))
    if ppr is not None:
        p.append(deepcopy(ppr))
    r = ET.SubElement(p, qn("w", "r"))
    if rpr is not None:
        r.append(deepcopy(rpr))
    t = ET.SubElement(r, qn("w", "t"))
    if text.startswith(" ") or text.endswith(" "):
        t.set(XML_SPACE, "preserve")
    t.text = text
    return p


def restore_namespaces(serialized: bytes, original: bytes) -> bytes:
    text = serialized.decode("utf-8")
    original_text = original.decode("utf-8", errors="replace")
    old = re.search(r"<w:document\b[^>]*>", original_text)
    new = re.search(r"<w:document\b[^>]*>", text)
    if not old or not new:
        return serialized
    old_decls = re.findall(r'\sxmlns:([A-Za-z0-9_]+)="([^"]+)"', old.group(0))
    existing = set(re.findall(r'\sxmlns:([A-Za-z0-9_]+)=', new.group(0)))
    additions = "".join(f' xmlns:{p}="{u}"' for p, u in old_decls if p not in existing)
    return text.replace(new.group(0), new.group(0)[:-1] + additions + ">", 1).encode("utf-8") if additions else serialized


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


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalize_references(body: ET.Element, config: dict[str, Any]) -> tuple[list[int], list[str]]:
    references = {str(k): str(v) for k, v in config.get("references", {}).items()}
    heading = str(config.get("main_references_heading") or "References")
    stop = str(config.get("stop_at_heading") or "Supporting Information")
    in_refs = False
    changed: list[int] = []
    unresolved: list[str] = []
    for idx, child in enumerate(list(body)):
        if child.tag != qn("w", "p"):
            continue
        text = compact_text(combined_text(child))
        if text == heading:
            in_refs = True
            continue
        if in_refs and text == stop:
            break
        if not in_refs:
            continue
        match = re.match(r"^\[(\d+)\]\s+", text)
        if not match:
            continue
        num = match.group(1)
        if num not in references:
            unresolved.append(num)
            continue
        new_text = f"[{num}] {references[num]}"
        new_p = make_paragraph(new_text, paragraph_ppr(child), first_run_rpr(child))
        body.remove(child)
        body.insert(idx, new_p)
        changed.append(int(num))
    return changed, unresolved


def run(args: argparse.Namespace) -> dict[str, Any]:
    input_docx = Path(args.input_docx)
    output_docx = Path(args.output_docx)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    with zipfile.ZipFile(input_docx, "r") as zin:
        original_xml = zin.read("word/document.xml")
    root = ET.fromstring(original_xml)
    body = root.find(".//w:body", NS)
    if body is None:
        raise ValueError("DOCX body not found.")
    changed, unresolved = normalize_references(body, config)
    serialized = restore_namespaces(ET.tostring(root, encoding="utf-8", xml_declaration=True), original_xml)
    write_docx(input_docx, output_docx, serialized)
    report = {
        "schema_version": 1,
        "input_docx": str(input_docx),
        "output_docx": str(output_docx),
        "config": str(Path(args.config)),
        "normalized_reference_numbers": changed,
        "unresolved_reference_numbers": unresolved,
        "validation": {"ok": not unresolved, "unresolved_reference_numbers": unresolved},
        "warnings": [] if not unresolved else [f"Missing reference config for: {', '.join(unresolved)}"],
    }
    report_path = Path(args.report_json) if args.report_json else output_docx.with_suffix(".reference_polish_report.json")
    write_json(report_path, report)
    print(f"Wrote {output_docx}")
    print(f"Wrote {report_path}")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-docx", required=True)
    parser.add_argument("--output-docx", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--report-json", default="")
    return parser.parse_args()


if __name__ == "__main__":
    result = run(parse_args())
    raise SystemExit(0 if result["validation"]["ok"] else 2)
