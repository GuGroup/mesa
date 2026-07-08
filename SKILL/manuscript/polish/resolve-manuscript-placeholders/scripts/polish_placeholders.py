#!/usr/bin/env python3
"""Remove or replace unresolved manuscript placeholders in a DOCX."""

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
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
}
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


def make_paragraph(text: str, ppr: ET.Element | None = None) -> ET.Element:
    p = ET.Element(qn("w", "p"))
    if ppr is not None:
        p.append(deepcopy(ppr))
    r = ET.SubElement(p, qn("w", "r"))
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
    old_root = old.group(0)
    new_root = new.group(0)
    old_decls = re.findall(r'\sxmlns:([A-Za-z0-9_]+)="([^"]+)"', old_root)
    existing = set(re.findall(r'\sxmlns:([A-Za-z0-9_]+)=', new_root))
    additions = "".join(f' xmlns:{p}="{u}"' for p, u in old_decls if p not in existing)
    return text.replace(new_root, new_root[:-1] + additions + ">", 1).encode("utf-8") if additions else serialized


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


def apply_policies(body: ET.Element, policies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for policy in policies:
        placeholder = str(policy.get("placeholder") or "")
        action = str(policy.get("action") or "")
        heading = compact_text(policy.get("heading") or "")
        replacement = str(policy.get("replacement_text") or "")
        children = list(body)
        for idx, child in enumerate(children):
            if child.tag != qn("w", "p"):
                continue
            text = compact_text(combined_text(child))
            if placeholder not in text:
                continue
            if action == "remove_placeholder_paragraph":
                body.remove(child)
                actions.append({"placeholder": placeholder, "action": action, "removed": [text]})
            elif action == "remove_heading_and_placeholder":
                removed = [text]
                if idx > 0 and heading and compact_text(combined_text(children[idx - 1])) == heading:
                    body.remove(children[idx - 1])
                    removed.insert(0, heading)
                body.remove(child)
                actions.append({"placeholder": placeholder, "action": action, "removed": removed})
            elif action == "replace_with_text":
                new_p = make_paragraph(replacement, paragraph_ppr(child))
                body.remove(child)
                body.insert(idx, new_p)
                actions.append({"placeholder": placeholder, "action": action, "replacement_text": replacement})
            else:
                raise ValueError(f"Unsupported placeholder action: {action}")
            break
    return actions


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
    actions = apply_policies(body, config.get("policies", []))
    serialized = restore_namespaces(ET.tostring(root, encoding="utf-8", xml_declaration=True), original_xml)
    write_docx(input_docx, output_docx, serialized)
    with zipfile.ZipFile(output_docx, "r") as zout:
        check_root = ET.fromstring(zout.read("word/document.xml"))
        text = "\n".join(compact_text(combined_text(p)) for p in check_root.findall(".//w:body/w:p", NS))
        placeholders = sorted(set(re.findall(r"\{\{[^{}]+\}\}", text)))
    report = {
        "schema_version": 1,
        "input_docx": str(input_docx),
        "output_docx": str(output_docx),
        "config": str(Path(args.config)),
        "actions": actions,
        "validation": {"ok": not placeholders, "remaining_placeholders": placeholders},
        "warnings": [] if not placeholders else [f"Remaining placeholders: {', '.join(placeholders)}"],
    }
    report_path = Path(args.report_json) if args.report_json else output_docx.with_suffix(".placeholder_polish_report.json")
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
