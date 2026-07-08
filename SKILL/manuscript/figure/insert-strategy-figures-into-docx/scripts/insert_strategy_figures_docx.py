#!/usr/bin/env python3
"""Insert realized strategy figures and public captions into a DOCX skeleton."""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET

from PIL import Image


NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
}

for prefix, uri in NS.items():
    ET.register_namespace("" if prefix in {"rel", "ct"} else prefix, uri)

EMU_PER_INCH = 914400
IMAGE_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
SKIP_STATES = {"blocked", "skipped", "failed", "excluded", "unrealized"}
SI_LEVELS = {"supplementary", "si", "supporting", "supporting-information", "supporting_information"}
SKIP_LEVELS = {"archive", "unnecessary", "blocked", "skip"}


def qn(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


@dataclass
class FigureBlock:
    figure_id: str
    placement: str
    label: str
    title: str
    caption: str
    extended_caption: str
    caption_text: str
    image_paths: list[str]
    state: str
    level: str


def read_json(path: Path | None) -> Any:
    if path is None:
        return {}
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


def paragraph_style(p: ET.Element) -> str:
    pstyle = p.find("./w:pPr/w:pStyle", NS)
    if pstyle is None:
        return ""
    return pstyle.attrib.get(qn("w", "val"), "")


def find_paragraph_index(body: ET.Element, needle: str) -> int | None:
    for idx, child in enumerate(list(body)):
        if child.tag != qn("w", "p"):
            continue
        text = compact_text(combined_text(child))
        if text == compact_text(needle) or compact_text(needle) in text:
            return idx
    return None


def first_caption_ppr(body: ET.Element, main_placeholder: str) -> ET.Element | None:
    idx = find_paragraph_index(body, main_placeholder)
    if idx is not None:
        ppr = list(body)[idx].find("./w:pPr", NS)
        if ppr is not None:
            return deepcopy(ppr)
    for child in list(body):
        if child.tag == qn("w", "p") and paragraph_style(child) == "a9":
            ppr = child.find("./w:pPr", NS)
            if ppr is not None:
                return deepcopy(ppr)
    ppr = ET.Element(qn("w", "pPr"))
    pstyle = ET.SubElement(ppr, qn("w", "pStyle"))
    pstyle.set(qn("w", "val"), "a9")
    return ppr


def make_text_paragraph(text: str, ppr: ET.Element | None = None, style: str = "") -> ET.Element:
    p = ET.Element(qn("w", "p"))
    if ppr is not None:
        p.append(deepcopy(ppr))
    elif style:
        ppr_new = ET.SubElement(p, qn("w", "pPr"))
        pstyle = ET.SubElement(ppr_new, qn("w", "pStyle"))
        pstyle.set(qn("w", "val"), style)
    run = ET.SubElement(p, qn("w", "r"))
    t = ET.SubElement(run, qn("w", "t"))
    if text.startswith(" ") or text.endswith(" "):
        t.set(XML_SPACE, "preserve")
    t.text = text
    return p


def add_text_run(p: ET.Element, text: str, bold: bool = False) -> None:
    if not text:
        return
    run = ET.SubElement(p, qn("w", "r"))
    if bold:
        rpr = ET.SubElement(run, qn("w", "rPr"))
        ET.SubElement(rpr, qn("w", "b"))
    t = ET.SubElement(run, qn("w", "t"))
    if text.startswith(" ") or text.endswith(" "):
        t.set(XML_SPACE, "preserve")
    t.text = text


def make_caption_paragraph(block: FigureBlock, ppr: ET.Element | None = None) -> ET.Element:
    p = ET.Element(qn("w", "p"))
    if ppr is not None:
        p.append(deepcopy(ppr))
    else:
        ppr_new = ET.SubElement(p, qn("w", "pPr"))
        pstyle = ET.SubElement(ppr_new, qn("w", "pStyle"))
        pstyle.set(qn("w", "val"), "a9")

    title = compact_text(block.title).rstrip(".")
    caption_body = " ".join(
        part for part in [compact_text(block.caption), compact_text(block.extended_caption)] if part
    )
    add_text_run(p, block.label, bold=True)
    add_text_run(p, " | ", bold=True)
    if title:
        add_text_run(p, f"{title}.", bold=True)
        if caption_body:
            add_text_run(p, f" {caption_body}")
    elif caption_body:
        add_text_run(p, caption_body)
    return p


def make_empty_paragraph() -> ET.Element:
    return ET.Element(qn("w", "p"))


def normalize_ext(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    if ext == "jpg":
        return "jpeg"
    return ext or "png"


def content_type_for_ext(ext: str) -> str:
    if ext == "png":
        return "image/png"
    if ext in {"jpeg", "jpg"}:
        return "image/jpeg"
    if ext == "gif":
        return "image/gif"
    raise ValueError(f"Unsupported image extension: {ext}")


def ensure_content_type_defaults(root: ET.Element, extensions: set[str]) -> None:
    existing = {
        child.attrib.get("Extension", "").lower()
        for child in root.findall("ct:Default", NS)
    }
    for ext in sorted(extensions):
        if ext in existing:
            continue
        default = ET.SubElement(root, qn("ct", "Default"))
        default.set("Extension", ext)
        default.set("ContentType", content_type_for_ext(ext))


def restore_document_namespace_declarations(serialized: bytes, original: bytes) -> bytes:
    """Keep Word root namespace declarations that ElementTree drops as unused.

    Word stores compatibility prefixes in mc:Ignorable as attribute text. Generic
    XML serializers can remove those namespace declarations because the prefixes
    are not used as XML names after round-tripping. Word may then open the file in
    recovery mode, so copy missing xmlns declarations from the template root.
    """
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
    new_root_repaired = new_root[:-1] + additions + ">"
    return text.replace(new_root, new_root_repaired, 1).encode("utf-8")


def next_relationship_id(root: ET.Element) -> str:
    max_id = 0
    for rel in root.findall("rel:Relationship", NS):
        match = re.fullmatch(r"rId(\d+)", rel.attrib.get("Id", ""))
        if match:
            max_id = max(max_id, int(match.group(1)))
    return f"rId{max_id + 1}"


def add_image_relationship(root: ET.Element, target: str) -> str:
    rid = next_relationship_id(root)
    rel = ET.SubElement(root, qn("rel", "Relationship"))
    rel.set("Id", rid)
    rel.set("Type", IMAGE_REL_TYPE)
    rel.set("Target", target)
    return rid


def image_extent(path: Path, max_width_in: float, max_height_in: float) -> tuple[int, int]:
    with Image.open(path) as image:
        width_px, height_px = image.size
        dpi = image.info.get("dpi", (96, 96))
    dpi_x = dpi[0] if isinstance(dpi, tuple) and dpi and dpi[0] and dpi[0] > 1 else 96
    dpi_y = dpi[1] if isinstance(dpi, tuple) and len(dpi) > 1 and dpi[1] and dpi[1] > 1 else dpi_x
    width_in = width_px / dpi_x
    height_in = height_px / dpi_y
    scale = min(1.0, max_width_in / width_in, max_height_in / height_in)
    width_in *= scale
    height_in *= scale
    return int(width_in * EMU_PER_INCH), int(height_in * EMU_PER_INCH)


def make_image_paragraph(rel_id: str, image_name: str, cx: int, cy: int, docpr_id: int) -> ET.Element:
    p = ET.Element(qn("w", "p"))
    ppr = ET.SubElement(p, qn("w", "pPr"))
    jc = ET.SubElement(ppr, qn("w", "jc"))
    jc.set(qn("w", "val"), "center")
    run = ET.SubElement(p, qn("w", "r"))
    drawing = ET.SubElement(run, qn("w", "drawing"))
    inline = ET.SubElement(drawing, qn("wp", "inline"))
    for attr in ("distT", "distB", "distL", "distR"):
        inline.set(attr, "0")
    extent = ET.SubElement(inline, qn("wp", "extent"))
    extent.set("cx", str(cx))
    extent.set("cy", str(cy))
    docpr = ET.SubElement(inline, qn("wp", "docPr"))
    docpr.set("id", str(docpr_id))
    docpr.set("name", image_name)
    c_nv = ET.SubElement(inline, qn("wp", "cNvGraphicFramePr"))
    locks = ET.SubElement(c_nv, qn("a", "graphicFrameLocks"))
    locks.set("noChangeAspect", "1")
    graphic = ET.SubElement(inline, qn("a", "graphic"))
    graphic_data = ET.SubElement(graphic, qn("a", "graphicData"))
    graphic_data.set("uri", "http://schemas.openxmlformats.org/drawingml/2006/picture")
    pic = ET.SubElement(graphic_data, qn("pic", "pic"))
    nv_pic_pr = ET.SubElement(pic, qn("pic", "nvPicPr"))
    c_nv_pr = ET.SubElement(nv_pic_pr, qn("pic", "cNvPr"))
    c_nv_pr.set("id", str(docpr_id))
    c_nv_pr.set("name", image_name)
    ET.SubElement(nv_pic_pr, qn("pic", "cNvPicPr"))
    blip_fill = ET.SubElement(pic, qn("pic", "blipFill"))
    blip = ET.SubElement(blip_fill, qn("a", "blip"))
    blip.set(qn("r", "embed"), rel_id)
    stretch = ET.SubElement(blip_fill, qn("a", "stretch"))
    ET.SubElement(stretch, qn("a", "fillRect"))
    sp_pr = ET.SubElement(pic, qn("pic", "spPr"))
    xfrm = ET.SubElement(sp_pr, qn("a", "xfrm"))
    off = ET.SubElement(xfrm, qn("a", "off"))
    off.set("x", "0")
    off.set("y", "0")
    ext = ET.SubElement(xfrm, qn("a", "ext"))
    ext.set("cx", str(cx))
    ext.set("cy", str(cy))
    prst = ET.SubElement(sp_pr, qn("a", "prstGeom"))
    prst.set("prst", "rect")
    ET.SubElement(prst, qn("a", "avLst"))
    return p


def load_location_map(path: Path | None) -> dict[str, dict[str, Any]]:
    data = read_json(path)
    if not data:
        return {}
    entries: list[Any]
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict) and isinstance(data.get("figures"), list):
        entries = data["figures"]
    elif isinstance(data, dict):
        entries = [{"figure_id": key, **(value if isinstance(value, dict) else {"placement": value})} for key, value in data.items()]
    else:
        raise ValueError("Location map must be a JSON object or list.")
    out: dict[str, dict[str, Any]] = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        figure_id = str(item.get("figure_id") or item.get("id") or "")
        if figure_id:
            out[figure_id] = item
    return out


def realization_by_id(realization: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(fig.get("id")): fig for fig in realization.get("figures", []) if isinstance(fig, dict)}


def normalize_placement(value: Any) -> str:
    token = str(value or "").strip().lower().replace(" ", "-")
    if token in {"main", "paper", "manuscript", "body", "results", "must_have", "must-have", "useful"}:
        return "main"
    if token in SI_LEVELS:
        return "si"
    if token in SKIP_LEVELS:
        return "skip"
    return ""


def infer_placement(cap: dict[str, Any], rec: dict[str, Any], loc: dict[str, Any]) -> tuple[str, str]:
    explicit = normalize_placement(loc.get("placement") or loc.get("location") or loc.get("section") or loc.get("level"))
    if explicit:
        return explicit, str(loc.get("level") or rec.get("level") or "")
    level = str(rec.get("level") or cap.get("level") or "").strip()
    placement = normalize_placement(level)
    if placement:
        return placement, level
    return "main", level


def resolve_existing_images(paths: list[Any], fail_on_missing: bool) -> tuple[list[str], list[str]]:
    existing: list[str] = []
    warnings: list[str] = []
    for raw in paths:
        path = Path(str(raw))
        if path.exists():
            existing.append(str(path))
            continue
        message = f"Missing image file: {path}"
        if fail_on_missing:
            raise FileNotFoundError(message)
        warnings.append(message)
    return existing, warnings


def build_caption_text(label: str, title: str, caption: str, extended: str) -> str:
    title = compact_text(title).rstrip(".")
    caption = compact_text(caption)
    extended = compact_text(extended)
    body = " ".join(part for part in [caption, extended] if part)
    if title and body:
        return f"{label} | {title}. {body}"
    if title:
        return f"{label} | {title}"
    return f"{label} | {body}"


def select_figures(
    caption_info: dict[str, Any],
    realization: dict[str, Any],
    location_map: dict[str, dict[str, Any]],
    figure_prefix: str,
    fail_on_missing: bool,
) -> tuple[list[FigureBlock], list[FigureBlock], list[dict[str, Any]], list[str]]:
    real_by_id = realization_by_id(realization)
    main: list[tuple[int, FigureBlock]] = []
    si: list[tuple[int, FigureBlock]] = []
    skipped: list[dict[str, Any]] = []
    warnings: list[str] = []

    for index, cap in enumerate(caption_info.get("captions", [])):
        if not isinstance(cap, dict):
            continue
        figure_id = str(cap.get("figure_id") or "")
        rec = real_by_id.get(figure_id, {})
        state = str(cap.get("state") or rec.get("state") or "").lower()
        if state in SKIP_STATES:
            skipped.append({"figure_id": figure_id, "reason": f"state={state}"})
            continue
        loc = location_map.get(figure_id, {})
        placement, level = infer_placement(cap, rec, loc)
        if placement == "skip":
            skipped.append({"figure_id": figure_id, "reason": "location-map skip"})
            continue
        exported = cap.get("exported_files") or rec.get("exported_files") or []
        image_paths, missing = resolve_existing_images(exported, fail_on_missing)
        warnings.extend(f"{figure_id}: {item}" for item in missing)
        if not image_paths:
            skipped.append({"figure_id": figure_id, "reason": "no existing exported image"})
            continue
        if placement == "si":
            label = ""
        else:
            label = ""
            placement = "main"
        title = compact_text(cap.get("figure_title", ""))
        caption = compact_text(cap.get("caption", ""))
        extended = compact_text(cap.get("extended_caption", ""))
        block = FigureBlock(
            figure_id=figure_id,
            placement=placement,
            label=label,
            title=title,
            caption=caption,
            extended_caption=extended,
            caption_text=build_caption_text(label, title, caption, extended),
            image_paths=image_paths,
            state=state or "realized",
            level=level,
        )
        order = int(loc.get("order", index)) if str(loc.get("order", "")).lstrip("-").isdigit() else index
        (si if placement == "si" else main).append((order, block))

    main_sorted = [b for _, b in sorted(main, key=lambda item: item[0])]
    si_sorted = [b for _, b in sorted(si, key=lambda item: item[0])]
    for idx, block in enumerate(main_sorted, 1):
        block.label = f"{figure_prefix} {idx}"
        block.caption_text = build_caption_text(block.label, block.title, block.caption, block.extended_caption)
    for idx, block in enumerate(si_sorted, 1):
        block.label = f"{figure_prefix} S{idx}"
        block.caption_text = build_caption_text(block.label, block.title, block.caption, block.extended_caption)

    return main_sorted, si_sorted, skipped, warnings


def insert_blocks(
    body: ET.Element,
    blocks: list[FigureBlock],
    index: int,
    mode: str,
    caption_ppr: ET.Element | None,
    rels_root: ET.Element,
    media_payloads: dict[str, bytes],
    used_exts: set[str],
    max_width_in: float,
    max_height_in: float,
    docpr_start: int,
) -> int:
    if not blocks:
        return docpr_start
    paragraphs: list[ET.Element] = []
    docpr_id = docpr_start
    media_counter = len(media_payloads)
    for block in blocks:
        for image_index, image_path_raw in enumerate(block.image_paths, 1):
            image_path = Path(image_path_raw)
            ext = normalize_ext(image_path)
            used_exts.add(ext)
            media_counter += 1
            media_name = f"strategy_{block.figure_id}_{image_index}.{ext}"
            target = f"media/{media_name}"
            media_payloads[f"word/{target}"] = image_path.read_bytes()
            rid = add_image_relationship(rels_root, target)
            cx, cy = image_extent(image_path, max_width_in, max_height_in)
            docpr_id += 1
            paragraphs.append(make_image_paragraph(rid, media_name, cx, cy, docpr_id))
        paragraphs.append(make_caption_paragraph(block, caption_ppr))
        paragraphs.append(make_empty_paragraph())

    if mode == "replace":
        body.remove(list(body)[index])
        insert_at = index
    elif mode == "before":
        insert_at = index
    else:
        insert_at = index + 1
    for offset, paragraph in enumerate(paragraphs):
        body.insert(insert_at + offset, paragraph)
    return docpr_id


def body_end_index(body: ET.Element) -> int:
    children = list(body)
    for idx, child in enumerate(children):
        if child.tag == qn("w", "sectPr"):
            return idx
    return len(children)


def inserted_payload(blocks: list[FigureBlock]) -> list[dict[str, Any]]:
    return [
        {
            "figure_id": block.figure_id,
            "placement": block.placement,
            "label": block.label,
            "title": block.title,
            "caption_text": block.caption_text,
            "image_paths": block.image_paths,
            "state": block.state,
            "level": block.level,
        }
        for block in blocks
    ]


def report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Strategy Figure DOCX Insertion Report",
        "",
        f"- Output DOCX: `{report['output_docx']}`",
        f"- Main figures inserted: {len(report['main_figures'])}",
        f"- SI figures inserted: {len(report['si_figures'])}",
        f"- Skipped figures: {len(report['skipped_figures'])}",
        "",
        "## Inserted Figures",
        "",
        "| Figure | Placement | Label | Title | Images |",
        "| --- | --- | --- | --- | --- |",
    ]
    for block in report["main_figures"] + report["si_figures"]:
        images = "<br>".join(f"`{path}`" for path in block["image_paths"])
        lines.append(f"| {block['figure_id']} | {block['placement']} | {block['label']} | {block['title']} | {images} |")
    if report["skipped_figures"]:
        lines.extend(["", "## Skipped Figures", ""])
        for item in report["skipped_figures"]:
            lines.append(f"- {item.get('figure_id', '')}: {item.get('reason', '')}")
    if report["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report["warnings"])
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Insert realized MESA strategy figures into a DOCX skeleton.")
    parser.add_argument("--template", required=True, help="Input DOCX skeleton/template.")
    parser.add_argument("--caption-info", required=True, help="caption_info.json from strategy-figure-captioner.")
    parser.add_argument("--output", required=True, help="Output DOCX path.")
    parser.add_argument("--realization", help="Optional figure_realization.json for levels and fallback image paths.")
    parser.add_argument("--location-map", help="Optional JSON map with per-figure placement/order.")
    parser.add_argument("--main-placeholder", default="{{FIGURE_NUMBER}} | {{FIGURE_TITLE}} {{FIGURE_CAPTION}}", help="Paragraph text replaced by main figure blocks.")
    parser.add_argument("--si-anchor", default="{{SI_SMALL_CONTENT_TEXT}}", help="Paragraph text used as the SI figure anchor.")
    parser.add_argument("--si-position", choices=["after", "before", "replace"], default="after", help="How to insert SI figure blocks relative to --si-anchor.")
    parser.add_argument("--figure-prefix", default="Fig.", help="Figure label prefix. Defaults to 'Fig.', producing 'Fig. 1' and 'Fig. S1'.")
    parser.add_argument("--max-width-in", type=float, default=6.25, help="Maximum inserted image width in inches.")
    parser.add_argument("--max-height-in", type=float, default=9.0, help="Maximum inserted image height in inches.")
    parser.add_argument("--fail-on-missing-image", action="store_true", help="Fail instead of warning when an exported image path is missing.")
    parser.add_argument("--report-json", help="Insertion report JSON path. Defaults beside output DOCX.")
    parser.add_argument("--report-md", help="Insertion report Markdown path. Defaults beside output DOCX.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    template = Path(args.template)
    output = Path(args.output)
    caption_info_path = Path(args.caption_info)
    realization_path = Path(args.realization) if args.realization else None
    location_map_path = Path(args.location_map) if args.location_map else None
    report_json_path = Path(args.report_json) if args.report_json else output.with_suffix(".insertion_report.json")
    report_md_path = Path(args.report_md) if args.report_md else output.with_suffix(".insertion_report.md")

    caption_info = read_json(caption_info_path)
    realization = read_json(realization_path)
    location_map = load_location_map(location_map_path)
    main_blocks, si_blocks, skipped, warnings = select_figures(
        caption_info,
        realization,
        location_map,
        args.figure_prefix,
        args.fail_on_missing_image,
    )

    with ZipFile(template, "r") as zin:
        parts = {info.filename: zin.read(info.filename) for info in zin.infolist()}
        infos = zin.infolist()

    document = ET.fromstring(parts["word/document.xml"])
    rels = ET.fromstring(parts["word/_rels/document.xml.rels"])
    content_types = ET.fromstring(parts["[Content_Types].xml"])
    body = document.find(".//w:body", NS)
    if body is None:
        raise ValueError("DOCX document body not found.")

    caption_ppr = first_caption_ppr(body, args.main_placeholder)
    media_payloads: dict[str, bytes] = {}
    used_exts: set[str] = set()
    docpr_id = 0

    if main_blocks:
        main_index = find_paragraph_index(body, args.main_placeholder)
        if main_index is None:
            warnings.append(f"Main placeholder not found: {args.main_placeholder}; inserted before document section properties.")
            main_index = body_end_index(body)
            main_mode = "before"
        else:
            main_mode = "replace"
        docpr_id = insert_blocks(
            body,
            main_blocks,
            main_index,
            main_mode,
            caption_ppr,
            rels,
            media_payloads,
            used_exts,
            args.max_width_in,
            args.max_height_in,
            docpr_id,
        )

    if si_blocks:
        si_index = find_paragraph_index(body, args.si_anchor)
        if si_index is None:
            warnings.append(f"SI anchor not found: {args.si_anchor}; inserted before document section properties.")
            si_index = body_end_index(body)
            si_mode = "before"
        else:
            si_mode = args.si_position
        docpr_id = insert_blocks(
            body,
            si_blocks,
            si_index,
            si_mode,
            caption_ppr,
            rels,
            media_payloads,
            used_exts,
            args.max_width_in,
            args.max_height_in,
            docpr_id,
        )

    ensure_content_type_defaults(content_types, used_exts)
    document_xml = restore_document_namespace_declarations(
        ET.tostring(document, encoding="utf-8", xml_declaration=True),
        parts["word/document.xml"],
    )
    replacements = {
        "word/document.xml": document_xml,
        "word/_rels/document.xml.rels": ET.tostring(rels, encoding="utf-8", xml_declaration=True),
        "[Content_Types].xml": ET.tostring(content_types, encoding="utf-8", xml_declaration=True),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as zout:
        for info in infos:
            if info.filename in replacements or info.filename in media_payloads:
                continue
            zout.writestr(info, parts[info.filename])
        for name, data in replacements.items():
            zout.writestr(name, data)
        for name, data in media_payloads.items():
            zout.writestr(name, data)

    report = {
        "schema_version": 1,
        "template": str(template),
        "caption_info": str(caption_info_path),
        "realization": str(realization_path) if realization_path else "",
        "location_map": str(location_map_path) if location_map_path else "",
        "output_docx": str(output),
        "numbering": {
            "main": f"{args.figure_prefix} N",
            "si": f"{args.figure_prefix} S1",
        },
        "sizing": {
            "max_width_in": args.max_width_in,
            "max_height_in": args.max_height_in,
        },
        "main_figures": inserted_payload(main_blocks),
        "si_figures": inserted_payload(si_blocks),
        "skipped_figures": skipped,
        "warnings": warnings,
    }
    write_json(report_json_path, report)
    write_text(report_md_path, report_markdown(report))
    print(f"Wrote {output}")
    print(f"Wrote {report_json_path}")
    print(f"Wrote {report_md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
