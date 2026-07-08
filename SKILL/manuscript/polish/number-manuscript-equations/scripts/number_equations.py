#!/usr/bin/env python3
"""Add configured equation numbers to DOCX equation paragraphs."""

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
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def qn(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def normalize_text(text: str) -> str:
    replacements = {
        "\u2212": "-",
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2192": "->",
        "\u27f6": "->",
        "\u21cc": "<->",
        "\u21c4": "<->",
        "\u2194": "<->",
        "\u00a0": " ",
        "\u2001": " ",
        "\u2002": " ",
        "\u2003": " ",
        "\u2004": " ",
        "\u2005": " ",
        "\u2006": " ",
        "\u2009": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"\s+", "", text)


def strip_trailing_equation_number(text: str) -> str:
    return re.sub(r"\s*\(\d+\)\s*$", "", text)


def paragraph_text(p: ET.Element) -> str:
    parts = []
    for el in p.iter():
        if el.tag in (qn("w", "t"), qn("m", "t")) and el.text:
            parts.append(el.text)
    return "".join(parts)


def is_display_equation_paragraph(p: ET.Element) -> bool:
    return p.find("./m:oMathPara", NS) is not None or p.find("./m:oMath", NS) is not None


def is_equation_number_table(tbl: ET.Element) -> bool:
    texts = []
    for t in tbl.findall(".//w:t", NS):
        if t.text:
            texts.append(t.text)
    return any(re.fullmatch(r"\s*\(\d+\)\s*", text or "") for text in texts)


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


def matcher_matches(matcher: Any, text: str) -> bool:
    norm = normalize_text(strip_trailing_equation_number(text))
    if isinstance(matcher, str):
        return norm == normalize_text(matcher)
    if not isinstance(matcher, dict):
        return False
    if "exact" in matcher:
        return norm == normalize_text(str(matcher["exact"]))
    if "contains" in matcher:
        return normalize_text(str(matcher["contains"])) in norm
    if "regex" in matcher:
        return re.search(str(matcher["regex"]), norm) is not None
    return False


def find_group(paragraphs: list[ET.Element], texts: list[str], lines: list[Any], start_at: int) -> list[int] | None:
    if not lines:
        return None
    max_start = len(paragraphs) - len(lines)
    for start in range(start_at, max_start + 1):
        indexes = []
        for offset, matcher in enumerate(lines):
            index = start + offset
            if not matcher_matches(matcher, texts[index]):
                break
            indexes.append(index)
        if len(indexes) == len(lines):
            return indexes
    return None


def remove_existing_number_artifacts(p: ET.Element, remove_tab_stops: bool = False) -> int:
    removed = 0
    for run in list(p.findall("./w:r", NS)):
        text = "".join(t.text or "" for t in run.findall(".//w:t", NS))
        if re.fullmatch(r"\s*\(\d+\)\s*", text or ""):
            p.remove(run)
            removed += 1
            continue
        children = list(run)
        if (
            len(children) == 2
            and children[0].tag == qn("w", "tab")
            and children[1].tag == qn("w", "t")
            and re.fullmatch(r"\(\d+\)", children[1].text or "")
        ):
            p.remove(run)
            removed += 1
    if remove_tab_stops:
        ppr = p.find("./w:pPr", NS)
        tabs = ppr.find("./w:tabs", NS) if ppr is not None else None
        if tabs is not None:
            for tab in list(tabs.findall("./w:tab", NS)):
                if tab.attrib.get(qn("w", "val")) == "right":
                    tabs.remove(tab)
            if len(list(tabs)) == 0:
                ppr.remove(tabs)
    return removed


def ensure_right_tab(p: ET.Element, right_tab_twips: int) -> None:
    ppr = p.find("./w:pPr", NS)
    if ppr is None:
        ppr = ET.Element(qn("w", "pPr"))
        p.insert(0, ppr)
    tabs = ppr.find("./w:tabs", NS)
    if tabs is None:
        tabs = ET.SubElement(ppr, qn("w", "tabs"))
    target = str(right_tab_twips)
    for tab in tabs.findall("./w:tab", NS):
        if tab.attrib.get(qn("w", "val")) == "right" and tab.attrib.get(qn("w", "pos")) == target:
            return
    tab = ET.SubElement(tabs, qn("w", "tab"))
    tab.set(qn("w", "val"), "right")
    tab.set(qn("w", "pos"), target)


def set_paragraph_alignment(p: ET.Element, value: str) -> None:
    ppr = p.find("./w:pPr", NS)
    if ppr is None:
        ppr = ET.Element(qn("w", "pPr"))
        p.insert(0, ppr)
    jc = ppr.find("./w:jc", NS)
    if jc is None:
        jc = ET.SubElement(ppr, qn("w", "jc"))
    jc.set(qn("w", "val"), value)


def append_number(p: ET.Element, number: int, placement: dict[str, Any]) -> int:
    style = str(placement.get("style", "spaces"))
    remove_existing_number_artifacts(p, remove_tab_stops=style != "right_tab")
    if style == "right_tab":
        ensure_right_tab(p, int(placement.get("right_tab_twips", 9360)))
        run = ET.Element(qn("w", "r"))
        run.append(ET.Element(qn("w", "tab")))
        t = ET.SubElement(run, qn("w", "t"))
        t.set(XML_SPACE, "preserve")
        t.text = f"({number})"
    else:
        run = ET.Element(qn("w", "r"))
        t = ET.SubElement(run, qn("w", "t"))
        t.set(XML_SPACE, "preserve")
        if "target_column" in placement:
            current_text = strip_trailing_equation_number(paragraph_text(p))
            min_spaces = max(1, int(placement.get("min_space_count", 4)))
            max_spaces = max(min_spaces, int(placement.get("max_space_count", 48)))
            target_column = max(1, int(placement.get("target_column", 72)))
            space_count = min(max_spaces, max(min_spaces, target_column - len(current_text)))
        else:
            space_count = max(1, int(placement.get("space_count", 24)))
        t.text = f"{' ' * space_count}({number})"
    p.append(run)
    return 1


def table_borders_none(tbl_pr: ET.Element) -> None:
    borders = ET.SubElement(tbl_pr, qn("w", "tblBorders"))
    for name in ["top", "left", "bottom", "right", "insideH", "insideV"]:
        border = ET.SubElement(borders, qn("w", name))
        border.set(qn("w", "val"), "nil")


def make_table_cell(width_twips: int, valign: str | None = None) -> ET.Element:
    tc = ET.Element(qn("w", "tc"))
    tc_pr = ET.SubElement(tc, qn("w", "tcPr"))
    tc_w = ET.SubElement(tc_pr, qn("w", "tcW"))
    tc_w.set(qn("w", "w"), str(width_twips))
    tc_w.set(qn("w", "type"), "dxa")
    if valign:
        va = ET.SubElement(tc_pr, qn("w", "vAlign"))
        va.set(qn("w", "val"), valign)
    return tc


def make_text_paragraph(text: str, alignment: str | None = None) -> ET.Element:
    p = ET.Element(qn("w", "p"))
    if alignment:
        set_paragraph_alignment(p, alignment)
    r = ET.SubElement(p, qn("w", "r"))
    t = ET.SubElement(r, qn("w", "t"))
    if text.startswith(" ") or text.endswith(" "):
        t.set(XML_SPACE, "preserve")
    t.text = text
    return p


def make_equation_number_table(group_paragraphs: list[ET.Element], number: int, placement: dict[str, Any]) -> ET.Element:
    table_width = int(placement.get("table_width_twips", 9360))
    side_width = int(placement.get("side_width_twips", 900))
    center_width = max(1440, table_width - (2 * side_width))

    tbl = ET.Element(qn("w", "tbl"))
    tbl_pr = ET.SubElement(tbl, qn("w", "tblPr"))
    tbl_w = ET.SubElement(tbl_pr, qn("w", "tblW"))
    tbl_w.set(qn("w", "w"), str(table_width))
    tbl_w.set(qn("w", "type"), "dxa")
    layout = ET.SubElement(tbl_pr, qn("w", "tblLayout"))
    layout.set(qn("w", "type"), "fixed")
    table_borders_none(tbl_pr)

    grid = ET.SubElement(tbl, qn("w", "tblGrid"))
    for width in [side_width, center_width, side_width]:
        col = ET.SubElement(grid, qn("w", "gridCol"))
        col.set(qn("w", "w"), str(width))

    tr = ET.SubElement(tbl, qn("w", "tr"))
    left = make_table_cell(side_width, "center")
    center = make_table_cell(center_width, "center")
    right = make_table_cell(side_width, "center")

    left.append(make_text_paragraph(""))
    for paragraph in group_paragraphs:
        copied = deepcopy(paragraph)
        remove_existing_number_artifacts(copied, remove_tab_stops=True)
        set_paragraph_alignment(copied, "center")
        center.append(copied)
    right.append(make_text_paragraph(f"({number})", "right"))

    tr.extend([left, center, right])
    return tbl


def target_offset(line_count: int, number_on: str) -> int:
    if number_on == "first":
        return 0
    if number_on == "middle":
        return max(0, (line_count - 1) // 2)
    return line_count - 1


def matcher_list_matches(matchers: list[Any], text: str) -> bool:
    return any(matcher_matches(matcher, text) for matcher in matchers)


def auto_groups(paragraphs: list[ET.Element], texts: list[str], config: dict[str, Any]) -> list[dict[str, Any]]:
    exclude = config.get("exclude_lines", [])
    default_number_on = str(config.get("number_on", "middle"))
    if default_number_on not in {"first", "middle", "last"}:
        default_number_on = "middle"
    groups: list[dict[str, Any]] = []
    current: list[int] = []

    for index, paragraph in enumerate(paragraphs):
        text = strip_trailing_equation_number(texts[index])
        include = is_display_equation_paragraph(paragraph) and bool(normalize_text(text))
        if include and isinstance(exclude, list) and matcher_list_matches(exclude, text):
            include = False
        if include:
            current.append(index)
            continue
        if current:
            groups.append(
                {
                    "label": f"auto_equation_group_{len(groups) + 1}",
                    "paragraph_indexes": current,
                    "number_on": default_number_on,
                }
            )
            current = []
    if current:
        groups.append(
            {
                "label": f"auto_equation_group_{len(groups) + 1}",
                "paragraph_indexes": current,
                "number_on": default_number_on,
            }
        )
    return groups


def number_equations(body: ET.Element, config: dict[str, Any]) -> dict[str, Any]:
    body_children = list(body)
    paragraphs = [p for p in body_children if p.tag == qn("w", "p")]
    texts = [paragraph_text(p) for p in paragraphs]
    groups = config.get("groups", [])
    start_number = int(config.get("start_number", 1))
    placement = config.get("placement", {})
    if not isinstance(placement, dict):
        placement = {"style": "spaces", "space_count": 24}
    next_number = start_number
    search_start = 0
    matched = []
    warnings = []
    changed = 0

    mode = str(config.get("mode", "auto" if not groups else "explicit"))
    if mode == "auto":
        resolved_groups = auto_groups(paragraphs, texts, config)
    else:
        resolved_groups = []
        for group in groups:
            lines = group.get("lines", []) if isinstance(group, dict) else []
            label = str(group.get("label") or f"group_{len(matched) + len(warnings) + 1}") if isinstance(group, dict) else "group"
            indexes = find_group(paragraphs, texts, lines, search_start)
            if indexes is None:
                warnings.append({"label": label, "warning": "equation group not found"})
                continue
            resolved = dict(group)
            resolved["label"] = label
            resolved["paragraph_indexes"] = indexes
            resolved_groups.append(resolved)
            search_start = indexes[-1] + 1

    table_replacements: list[dict[str, Any]] = []
    for group in resolved_groups:
        indexes = group["paragraph_indexes"]
        label = str(group.get("label") or f"group_{len(matched) + len(warnings) + 1}")
        number = int(group.get("number", next_number))
        if "number" not in group:
            next_number += 1
        number_on = str(group.get("number_on", config.get("number_on", "middle")))
        if number_on not in {"first", "middle", "last"}:
            number_on = "middle"
        target_index = indexes[target_offset(len(indexes), number_on)]
        style = str(placement.get("style", "three_column_table"))
        if style == "three_column_table":
            table_replacements.append({"indexes": indexes, "number": number, "placement": placement})
            changed += 1
        else:
            changed += append_number(paragraphs[target_index], number, placement)
        matched.append(
            {
                "label": label,
                "number": number,
                "paragraph_indexes": indexes,
                "target_paragraph_index": target_index,
                "number_on": number_on,
                "matched_text": [texts[i] for i in indexes],
            }
        )

    if table_replacements:
        for replacement in sorted(table_replacements, key=lambda item: item["indexes"][0], reverse=True):
            indexes = replacement["indexes"]
            group_paragraphs = [paragraphs[i] for i in indexes]
            first_child_index = list(body).index(group_paragraphs[0])
            tbl = make_equation_number_table(group_paragraphs, replacement["number"], replacement["placement"])
            for paragraph in group_paragraphs:
                body.remove(paragraph)
            body.insert(first_child_index, tbl)

    return {
        "mode": mode,
        "matched_groups": matched,
        "unmatched_group_count": len(warnings),
        "changed_group_count": changed,
        "warnings": warnings,
        "validation": {"ok": not warnings},
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    input_docx = Path(args.input_docx)
    output_docx = Path(args.output_docx)
    config_path = Path(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    with zipfile.ZipFile(input_docx, "r") as zin:
        original_xml = zin.read("word/document.xml")
    root = ET.fromstring(original_xml)
    body = root.find(".//w:body", NS)
    if body is None:
        raise ValueError("DOCX body not found.")
    result = number_equations(body, config)
    serialized = restore_namespaces(ET.tostring(root, encoding="utf-8", xml_declaration=True), original_xml)
    write_docx(input_docx, output_docx, serialized)
    report = {
        "schema_version": 1,
        "input_docx": str(input_docx),
        "output_docx": str(output_docx),
        "config": str(config_path),
        **result,
    }
    report_path = Path(args.report_json) if args.report_json else output_docx.with_suffix(".equation_number_report.json")
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
