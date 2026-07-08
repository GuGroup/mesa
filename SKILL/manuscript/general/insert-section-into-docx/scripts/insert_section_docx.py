#!/usr/bin/env python3
"""Insert structured manuscript section JSON into a DOCX skeleton."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile
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
MAIN_FIGURE_CAPTION_RE = re.compile(r"^Fig\.?\s+(\d+)\s*\|")


def qn(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def compact_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def combined_text(p: ET.Element) -> str:
    return "".join(t.text or "" for t in p.findall(".//w:t", NS))


def is_paragraph(child: ET.Element) -> bool:
    return child.tag == qn("w", "p")


def has_drawing(p: ET.Element) -> bool:
    return bool(p.findall(".//w:drawing", NS))


def is_empty_paragraph(p: ET.Element) -> bool:
    return compact_text(combined_text(p)) == "" and not has_drawing(p)


def main_figure_caption_number(p: ET.Element) -> str | None:
    match = MAIN_FIGURE_CAPTION_RE.match(compact_text(combined_text(p)))
    if match is None:
        return None
    return match.group(1)


def find_paragraph_index(body: ET.Element, needle: str) -> int | None:
    target = compact_text(needle)
    for idx, child in enumerate(list(body)):
        if child.tag != qn("w", "p"):
            continue
        text = compact_text(combined_text(child))
        if text == target or target in text:
            return idx
    return None


def paragraph_ppr(p: ET.Element | None) -> ET.Element | None:
    if p is None:
        return None
    ppr = p.find("./w:pPr", NS)
    return deepcopy(ppr) if ppr is not None else None


def body_end_index(body: ET.Element) -> int:
    children = list(body)
    for idx, child in enumerate(children):
        if child.tag == qn("w", "sectPr"):
            return idx
    return len(children)


def ensure_ppr(p: ET.Element, ppr: ET.Element | None = None) -> ET.Element:
    if ppr is not None:
        clone = deepcopy(ppr)
        p.append(clone)
        return clone
    return ET.SubElement(p, qn("w", "pPr"))


def set_alignment(ppr: ET.Element, value: str) -> None:
    for existing in list(ppr.findall("./w:jc", NS)):
        ppr.remove(existing)
    jc = ET.SubElement(ppr, qn("w", "jc"))
    jc.set(qn("w", "val"), value)


def add_text_run(
    p: ET.Element,
    text: str,
    bold: bool = False,
    italic: bool = False,
    font_size_pt: float | int | None = None,
) -> None:
    if text == "":
        return
    run = ET.SubElement(p, qn("w", "r"))
    if bold or italic or font_size_pt:
        rpr = ET.SubElement(run, qn("w", "rPr"))
        if bold:
            ET.SubElement(rpr, qn("w", "b"))
        if italic:
            ET.SubElement(rpr, qn("w", "i"))
        if font_size_pt:
            value = str(int(round(float(font_size_pt) * 2)))
            sz = ET.SubElement(rpr, qn("w", "sz"))
            sz.set(qn("w", "val"), value)
            sz_cs = ET.SubElement(rpr, qn("w", "szCs"))
            sz_cs.set(qn("w", "val"), value)
    t = ET.SubElement(run, qn("w", "t"))
    if text.startswith(" ") or text.endswith(" "):
        t.set(XML_SPACE, "preserve")
    t.text = text


def make_paragraph(
    text: str,
    ppr: ET.Element | None = None,
    *,
    bold: bool = False,
    italic: bool = False,
    font_size_pt: float | int | None = None,
    align: str = "",
) -> ET.Element:
    p = ET.Element(qn("w", "p"))
    ppr_new = ensure_ppr(p, ppr)
    if align:
        set_alignment(ppr_new, align)
    add_text_run(p, text, bold=bold, italic=italic, font_size_pt=font_size_pt)
    return p


def make_omml_paragraph(latex: str, ppr: ET.Element | None, pandoc: Path) -> ET.Element:
    with tempfile.TemporaryDirectory(prefix="mesa-pandoc-equation-") as tmpdir:
        tmp = Path(tmpdir)
        md_path = tmp / "equation.md"
        docx_path = tmp / "equation.docx"
        md_path.write_text(f"$$\n{latex}\n$$\n", encoding="utf-8")
        proc = subprocess.run(
            [
                str(pandoc),
                str(md_path),
                "-f",
                "markdown+tex_math_dollars",
                "-t",
                "docx",
                "-o",
                str(docx_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip()
            raise RuntimeError(f"Pandoc failed to convert LaTeX equation to DOCX OMML: {detail}")
        with ZipFile(docx_path, "r") as zf:
            root = ET.fromstring(zf.read("word/document.xml"))

    source_p = None
    for candidate in root.findall(".//w:p", NS):
        if candidate.find(".//m:oMath", NS) is not None:
            source_p = candidate
            break
    if source_p is None:
        raise RuntimeError("Pandoc DOCX output did not contain an OMML equation.")

    p = deepcopy(source_p)
    existing_ppr = p.find("./w:pPr", NS)
    if existing_ppr is not None:
        p.remove(existing_ppr)
    ppr_new = deepcopy(ppr) if ppr is not None else ET.Element(qn("w", "pPr"))
    set_alignment(ppr_new, "center")
    p.insert(0, ppr_new)
    for omath_para_pr in p.findall(".//m:oMathParaPr", NS):
        for existing in list(omath_para_pr.findall("./m:jc", NS)):
            omath_para_pr.remove(existing)
        jc = ET.SubElement(omath_para_pr, qn("m", "jc"))
        jc.set(qn("m", "val"), "center")
    return p


def make_section_intro_paragraph(title: str, text: str, ppr: ET.Element | None = None) -> ET.Element:
    p = ET.Element(qn("w", "p"))
    ensure_ppr(p, ppr)
    add_text_run(p, title, bold=True)
    if title:
        add_text_run(p, " ")
    add_text_run(p, text)
    return p


def make_empty_paragraph(ppr: ET.Element | None = None) -> ET.Element:
    p = ET.Element(qn("w", "p"))
    if ppr is not None:
        p.append(deepcopy(ppr))
    return p


def split_paragraphs(text: str) -> list[str]:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = [compact_text(part) for part in re.split(r"\n\s*\n+", normalized)]
    return [part for part in parts if part]


def normalize_equations(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    equations: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        latex = str(item.get("latex") or "").strip()
        if not latex:
            continue
        equations.append(
            {
                "label": compact_text(item.get("label") or "Equation"),
                "latex": latex,
                "explanation": compact_text(item.get("explanation") or ""),
            }
        )
    return equations


def normalize_content_blocks(item: dict[str, Any]) -> list[dict[str, str]]:
    raw = item.get("content_blocks")
    blocks: list[dict[str, str]] = []
    if raw is not None:
        if not isinstance(raw, list):
            raise ValueError("Section content_blocks must be a list when provided.")
        for block in raw:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "").strip().lower()
            if block_type == "paragraph":
                text = compact_text(block.get("text"))
                if text:
                    blocks.append({"type": "paragraph", "text": text})
            elif block_type == "equation":
                latex = str(block.get("latex") or "").strip()
                if not latex:
                    continue
                blocks.append(
                    {
                        "type": "equation",
                        "label": compact_text(block.get("label") or "Equation"),
                        "latex": latex,
                        "explanation": compact_text(block.get("explanation") or ""),
                    }
                )
            else:
                raise ValueError(f"Unsupported content block type: {block_type}")
    else:
        for paragraph in split_paragraphs(str(item.get("text") or "")):
            blocks.append({"type": "paragraph", "text": paragraph})
        for equation in normalize_equations(item.get("equations")):
            blocks.append({"type": "equation", **equation})
    if not any(block["type"] == "paragraph" for block in blocks):
        raise ValueError("Section must contain at least one paragraph block.")
    return blocks


def normalize_paragraph_style(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    style: dict[str, Any] = {}
    if "bold" in raw:
        style["bold"] = bool(raw.get("bold"))
    if "italic" in raw:
        style["italic"] = bool(raw.get("italic"))
    if raw.get("font_size_pt") not in (None, ""):
        try:
            size = float(raw.get("font_size_pt"))
        except (TypeError, ValueError) as exc:
            raise ValueError("paragraph_style.font_size_pt must be numeric.") from exc
        if not 1 <= size <= 200:
            raise ValueError("paragraph_style.font_size_pt must be between 1 and 200.")
        style["font_size_pt"] = size
    align = compact_text(raw.get("align")).lower()
    if align:
        if align not in {"left", "center", "right", "both"}:
            raise ValueError("paragraph_style.align must be left, center, right, or both.")
        style["align"] = align
    return style


def normalize_sections(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("sections")
    if not isinstance(raw, list):
        raise ValueError("Section JSON must contain a sections list.")
    sections: list[dict[str, Any]] = []
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            continue
        section_id = str(item.get("section_id") or f"section_{index}")
        title = compact_text(item.get("small_title") or item.get("title") or section_id.replace("_", " ").title())
        render_title = bool(item.get("render_title", True))
        paragraph_style = normalize_paragraph_style(item.get("paragraph_style"))
        blocks = normalize_content_blocks(item)
        sections.append(
            {
                "section_id": section_id,
                "title": title,
                "render_title": render_title,
                "paragraph_style": paragraph_style,
                "blocks": blocks,
                "paragraphs": [block["text"] for block in blocks if block["type"] == "paragraph"],
                "equations": [
                    {
                        "label": block.get("label", ""),
                        "latex": block.get("latex", ""),
                        "explanation": block.get("explanation", ""),
                    }
                    for block in blocks
                    if block["type"] == "equation"
                ],
            }
        )
    if not sections:
        raise ValueError("No sections were found in the section JSON.")
    return sections


def split_aligned_latex(latex: str) -> list[str]:
    match = re.fullmatch(r"\s*\\begin\{aligned\}(?P<body>.*)\\end\{aligned\}\s*", latex, flags=re.DOTALL)
    if match is None:
        return [latex]
    body = match.group("body").strip()
    rows = []
    for raw_row in re.split(r"\\\\(?:\s*\[[^\]]+\])?", body):
        row = raw_row.strip()
        if not row:
            continue
        row = row.replace("&", "").strip()
        if row:
            rows.append(row)
    return rows or [latex]


def rendered_equation_count(section: dict[str, Any]) -> int:
    total = 0
    for block in section["blocks"]:
        if block["type"] == "equation":
            total += len(split_aligned_latex(block["latex"]))
    return total


def render_sections(
    sections: list[dict[str, Any]],
    heading_ppr: ET.Element | None,
    body_ppr: ET.Element | None,
    equation_ppr: ET.Element | None,
    equation_mode: str,
    pandoc: Path | None,
) -> list[ET.Element]:
    paragraphs: list[ET.Element] = []
    for section_index, section in enumerate(sections):
        if section_index:
            paragraphs.append(make_empty_paragraph(body_ppr))
        intro_ppr = body_ppr if body_ppr is not None else heading_ppr
        used_intro = False
        paragraph_style = section.get("paragraph_style", {})
        for block in section["blocks"]:
            if block["type"] == "paragraph":
                if not used_intro:
                    if section.get("render_title", True):
                        paragraphs.append(make_section_intro_paragraph(section["title"], block["text"], intro_ppr))
                    else:
                        paragraphs.append(
                            make_paragraph(
                                block["text"],
                                intro_ppr,
                                bold=bool(paragraph_style.get("bold", False)),
                                italic=bool(paragraph_style.get("italic", False)),
                                font_size_pt=paragraph_style.get("font_size_pt"),
                                align=str(paragraph_style.get("align", "")),
                            )
                        )
                    used_intro = True
                else:
                    paragraphs.append(
                        make_paragraph(
                            block["text"],
                            body_ppr,
                            bold=bool(paragraph_style.get("bold", False)),
                            italic=bool(paragraph_style.get("italic", False)),
                            font_size_pt=paragraph_style.get("font_size_pt"),
                            align=str(paragraph_style.get("align", "")),
                        )
                    )
            elif block["type"] == "equation":
                explanation = block["explanation"]
                eq_ppr = equation_ppr if equation_ppr is not None else body_ppr
                rendered_equations = split_aligned_latex(block["latex"])
                paragraphs.append(make_empty_paragraph(body_ppr))
                for latex in rendered_equations:
                    if equation_mode == "omml":
                        if pandoc is None:
                            raise RuntimeError("Pandoc is required for --equation-mode omml.")
                        paragraphs.append(make_omml_paragraph(latex, eq_ppr, pandoc))
                    else:
                        paragraphs.append(make_paragraph(latex, eq_ppr, align="center"))
                paragraphs.append(make_empty_paragraph(body_ppr))
                if explanation:
                    paragraphs.append(make_paragraph(explanation, body_ppr))
    return paragraphs


def resolve_pandoc(explicit: str = "") -> Path | None:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise FileNotFoundError(f"Pandoc executable not found: {path}")
        return path
    found = shutil.which("pandoc")
    if found:
        return Path(found)
    repo_root = Path(__file__).resolve().parents[3]
    local = repo_root / "DEPENDENCY" / "tools" / "pandoc" / "bin" / "pandoc"
    if local.exists():
        return local
    return None


def restore_document_namespace_declarations(serialized: bytes, original: bytes) -> bytes:
    """Keep Word root namespace declarations that ElementTree drops as unused."""
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
    additions = "".join(
        f' xmlns:{prefix}="{uri}"'
        for prefix, uri in original_decls
        if prefix not in existing
    )
    if not additions:
        return serialized
    return text.replace(new_root, new_root[:-1] + additions + ">", 1).encode("utf-8")


def used_namespace_uris(root: ET.Element) -> set[str]:
    uris: set[str] = set()
    for node in root.iter():
        if node.tag.startswith("{"):
            uris.add(node.tag[1:].split("}", 1)[0])
        for attr in node.attrib:
            if attr.startswith("{"):
                uris.add(attr[1:].split("}", 1)[0])
    return uris


def normalize_mc_ignorable(root: ET.Element) -> None:
    ignorable_attr = qn("mc", "Ignorable")
    used = used_namespace_uris(root)
    preferred = ["w14", "w15", "w16se", "w16cid", "w16", "w16cex", "w16sdtdh", "wp14"]
    active = [prefix for prefix in preferred if NS.get(prefix) in used]
    if active:
        root.set(ignorable_attr, " ".join(active))
    elif ignorable_attr in root.attrib:
        del root.attrib[ignorable_attr]


def collect_main_figure_blocks(body: ET.Element) -> list[dict[str, Any]]:
    children = list(body)
    blocks: list[dict[str, Any]] = []
    last_end = 0
    for idx, child in enumerate(children):
        if not is_paragraph(child):
            continue
        number = main_figure_caption_number(child)
        if number is None:
            continue
        start = idx
        while start > last_end:
            previous = children[start - 1]
            if not is_paragraph(previous):
                break
            if main_figure_caption_number(previous) is not None:
                break
            if has_drawing(previous) or is_empty_paragraph(previous):
                start -= 1
                continue
            break
        elements = children[start : idx + 1]
        blocks.append(
            {
                "figure_number": f"Fig. {number}",
                "caption": compact_text(combined_text(child)),
                "start_index": start,
                "end_index": idx + 1,
                "elements": elements,
            }
        )
        last_end = idx + 1
    return blocks


def distribute_main_figures(body: ET.Element, inserted_elements: list[ET.Element]) -> dict[str, Any]:
    figure_blocks = collect_main_figure_blocks(body)
    movable = []
    for block in figure_blocks:
        figure_number = block["figure_number"]
        anchor = None
        for paragraph in inserted_elements:
            if not is_paragraph(paragraph):
                continue
            text = compact_text(combined_text(paragraph))
            if re.search(rf"\b{re.escape(figure_number)}\b", text):
                anchor = paragraph
                break
        if anchor is not None:
            movable.append({**block, "anchor": anchor})

    for block in reversed(movable):
        for element in reversed(block["elements"]):
            try:
                body.remove(element)
            except ValueError:
                pass

    moved = []
    anchor_tails: dict[int, ET.Element] = {}
    for block in movable:
        anchor = block["anchor"]
        tail = anchor_tails.get(id(anchor), anchor)
        children = list(body)
        if tail not in children:
            continue
        insert_at = children.index(tail) + 1
        for offset, element in enumerate(block["elements"]):
            body.insert(insert_at + offset, element)
        anchor_tails[id(anchor)] = block["elements"][-1]
        moved.append(
            {
                "figure_number": block["figure_number"],
                "caption": block["caption"],
                "inserted_after": compact_text(combined_text(anchor))[:180],
                "moved_element_count": len(block["elements"]),
            }
        )

    return {
        "enabled": True,
        "available_main_figures": [
            {"figure_number": block["figure_number"], "caption": block["caption"]}
            for block in figure_blocks
        ],
        "moved": moved,
        "unmoved": [
            {"figure_number": block["figure_number"], "caption": block["caption"]}
            for block in figure_blocks
            if block["figure_number"] not in {item["figure_number"] for item in moved}
        ],
    }


def insert_section_blocks(
    body: ET.Element,
    sections: list[dict[str, Any]],
    placeholder: str,
    title_placeholder: str,
    keep_title_placeholder: bool,
    equation_mode: str,
    pandoc: Path | None,
    distribute_figures: bool,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []

    title_idx = find_paragraph_index(body, title_placeholder) if title_placeholder else None
    placeholder_idx = find_paragraph_index(body, placeholder)

    title_p = list(body)[title_idx] if title_idx is not None else None
    placeholder_p = list(body)[placeholder_idx] if placeholder_idx is not None else None
    heading_ppr = paragraph_ppr(title_p)
    body_ppr = paragraph_ppr(placeholder_p)
    equation_ppr = deepcopy(body_ppr) if body_ppr is not None else None
    blocks = render_sections(sections, heading_ppr, body_ppr, equation_ppr, equation_mode, pandoc)

    removed_title_placeholder = False
    if title_p is not None and not keep_title_placeholder and title_p is not placeholder_p:
        body.remove(title_p)
        removed_title_placeholder = True

    placeholder_idx = find_paragraph_index(body, placeholder)
    if placeholder_idx is None:
        warnings.append(f"Placeholder not found: {placeholder}; inserted before document section properties.")
        insert_at = body_end_index(body)
        mode = "before-section-properties"
    else:
        body.remove(list(body)[placeholder_idx])
        insert_at = placeholder_idx
        mode = "replace-placeholder"

    for offset, paragraph in enumerate(blocks):
        body.insert(insert_at + offset, paragraph)

    figure_distribution = {"enabled": False, "available_main_figures": [], "moved": [], "unmoved": []}
    if distribute_figures:
        figure_distribution = distribute_main_figures(body, blocks)

    return {
        "mode": mode,
        "placeholder": placeholder,
        "title_placeholder": title_placeholder,
        "removed_title_placeholder": removed_title_placeholder,
        "inserted_paragraph_count": len(blocks),
        "equation_mode": equation_mode,
        "pandoc": str(pandoc) if pandoc is not None else "",
        "figure_distribution": figure_distribution,
    }, warnings


def validate_docx_parts(parts: dict[str, bytes]) -> None:
    required = ["word/document.xml", "[Content_Types].xml"]
    missing = [part for part in required if part not in parts]
    if missing:
        raise ValueError(f"DOCX is missing required part(s): {', '.join(missing)}")


def write_docx(template: Path, output: Path, document_xml: bytes) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(template, "r") as zin:
        infos = zin.infolist()
        parts = {info.filename: zin.read(info.filename) for info in infos}
    parts["word/document.xml"] = document_xml
    with ZipFile(output, "w", ZIP_DEFLATED) as zout:
        for info in infos:
            if info.filename in parts:
                zout.writestr(info, parts.pop(info.filename))
        for filename, payload in parts.items():
            zout.writestr(filename, payload)


def report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Manuscript Section DOCX Insertion Report",
        "",
        f"- Output DOCX: `{report['output_docx']}`",
        f"- Placeholder: `{report['placeholder']}`",
        f"- Sections inserted: {len(report['sections'])}",
        f"- Equation blocks inserted: {report['equation_count']}",
        f"- Rendered equations inserted: {report['rendered_equation_count']}",
        f"- Equation mode: `{report['equation_mode']}`",
        f"- Inserted paragraphs: {report['inserted_paragraph_count']}",
        f"- Figure distribution: `{report.get('figure_distribution', {}).get('enabled', False)}`",
        "",
        "## Sections",
        "",
        "| Section ID | Title | Render Title | Paragraphs | Equation Blocks | Rendered Equations |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    for section in report["sections"]:
        lines.append(
            f"| {section['section_id']} | {section['title']} | {section.get('render_title', True)} | {section['paragraph_count']} | {section['equation_count']} | {section['rendered_equation_count']} |"
        )
    if report["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report["warnings"])
    distribution = report.get("figure_distribution", {})
    if distribution.get("enabled"):
        lines.extend(["", "## Figure Distribution", ""])
        if distribution.get("moved"):
            lines.append("Moved main figures:")
            lines.extend(
                f"- {item['figure_number']}: after `{item['inserted_after']}`"
                for item in distribution.get("moved", [])
            )
        if distribution.get("unmoved"):
            lines.append("")
            lines.append("Unmoved main figures:")
            lines.extend(f"- {item['figure_number']}" for item in distribution.get("unmoved", []))
    return "\n".join(lines).rstrip() + "\n"


def build_report(
    args: argparse.Namespace,
    data: dict[str, Any],
    sections: list[dict[str, Any]],
    insertion: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    section_rows = [
        {
            "section_id": section["section_id"],
            "title": section["title"],
            "render_title": section.get("render_title", True),
            "paragraph_style": section.get("paragraph_style", {}),
            "paragraph_count": len(section["paragraphs"]),
            "equation_count": len(section["equations"]),
            "rendered_equation_count": rendered_equation_count(section),
        }
        for section in sections
    ]
    return {
        "schema_version": 1,
        "template_docx": str(Path(args.template)),
        "section_json": str(Path(args.section_json)),
        "output_docx": str(Path(args.output)),
        "source_schema_version": data.get("schema_version"),
        "strategy_id": data.get("strategy_id", ""),
        "placeholder": args.placeholder,
        "title_placeholder": args.title_placeholder,
        "mode": insertion["mode"],
        "removed_title_placeholder": insertion["removed_title_placeholder"],
        "inserted_paragraph_count": insertion["inserted_paragraph_count"],
        "equation_mode": insertion["equation_mode"],
        "pandoc": insertion["pandoc"],
        "figure_distribution": insertion.get("figure_distribution", {"enabled": False}),
        "sections": section_rows,
        "equation_count": sum(row["equation_count"] for row in section_rows),
        "rendered_equation_count": sum(row["rendered_equation_count"] for row in section_rows),
        "warnings": warnings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, help="Input DOCX skeleton/template.")
    parser.add_argument("--section-json", required=True, help="Structured manuscript section JSON.")
    parser.add_argument("--output", required=True, help="Output DOCX path.")
    parser.add_argument("--placeholder", default="{{METHOD_TEXT}}", help="Paragraph placeholder replaced by section blocks.")
    parser.add_argument("--title-placeholder", default="{{METHODS_SMALL_TITLE}}", help="Optional title placeholder used for heading style.")
    parser.add_argument("--keep-title-placeholder", action="store_true", help="Keep the title placeholder paragraph instead of removing it.")
    parser.add_argument("--equation-mode", choices=["omml", "text"], default="omml", help="Render equations as Word OMML via Pandoc or plain centered text.")
    parser.add_argument("--pandoc", default="", help="Optional path to the Pandoc executable for --equation-mode omml.")
    parser.add_argument("--distribute-figures", action="store_true", help="Move existing main figure drawing/caption blocks after inserted paragraphs that first mention each figure.")
    parser.add_argument("--report-json", help="Insertion report JSON path. Defaults beside output DOCX.")
    parser.add_argument("--report-md", help="Insertion report Markdown path. Defaults beside output DOCX.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    template = Path(args.template)
    section_json = Path(args.section_json)
    output = Path(args.output)
    if template.resolve() == output.resolve():
        raise SystemExit("Refusing to overwrite the template DOCX. Choose a different --output path.")

    data = read_json(section_json)
    if not isinstance(data, dict):
        raise SystemExit("Section JSON must be a JSON object.")
    sections = normalize_sections(data)
    pandoc = resolve_pandoc(args.pandoc) if args.equation_mode == "omml" else None
    if args.equation_mode == "omml" and pandoc is None:
        raise SystemExit(
            "Pandoc is required for --equation-mode omml. Install pandoc or pass --equation-mode text."
        )

    with ZipFile(template, "r") as zin:
        parts = {info.filename: zin.read(info.filename) for info in zin.infolist()}
    validate_docx_parts(parts)

    document = ET.fromstring(parts["word/document.xml"])
    body = document.find(".//w:body", NS)
    if body is None:
        raise SystemExit("DOCX document body not found.")

    insertion, warnings = insert_section_blocks(
        body,
        sections,
        args.placeholder,
        args.title_placeholder,
        args.keep_title_placeholder,
        args.equation_mode,
        pandoc,
        args.distribute_figures,
    )

    normalize_mc_ignorable(document)
    serialized = ET.tostring(document, encoding="utf-8", xml_declaration=True)
    serialized = restore_document_namespace_declarations(serialized, parts["word/document.xml"])
    write_docx(template, output, serialized)

    report_json = Path(args.report_json) if args.report_json else output.with_suffix(".insertion_report.json")
    report_md = Path(args.report_md) if args.report_md else output.with_suffix(".insertion_report.md")
    report = build_report(args, data, sections, insertion, warnings)
    write_json(report_json, report)
    write_text(report_md, report_markdown(report))

    print(f"Wrote {output}")
    print(f"Wrote {report_json}")
    print(f"Wrote {report_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
