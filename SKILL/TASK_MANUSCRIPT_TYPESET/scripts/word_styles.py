from __future__ import annotations

import argparse
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Final
from zipfile import ZIP_DEFLATED, ZipFile


W_NS: Final = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CAPTION_TEXT_RE: Final = re.compile(r"^(?:Figure|Table)\s+\d+[A-Za-z]?\s*\|")
CAPTION_STYLE_IDS: Final = frozenset({"Caption", "FigureCaption", "TableCaption"})
ET.register_namespace("w", W_NS)


def apply_default_word_styles(docx: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        with ZipFile(docx) as source:
            source.extractall(workdir)
        styles = workdir / "word" / "styles.xml"
        if styles.is_file():
            patch_styles(styles)
        document = workdir / "word" / "document.xml"
        if document.is_file():
            patch_document(document)
        replacement = docx.with_suffix(".styled.docx")
        with ZipFile(replacement, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(workdir.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(workdir).as_posix())
        shutil.move(str(replacement), docx)


def patch_styles(path: Path) -> None:
    tree = ET.parse(path)
    root = tree.getroot()
    patch_doc_defaults(root)
    patch_style(root, "Normal", font_size_half_points="24", line_twips="360")
    patch_style(root, "BodyText", font_size_half_points="24", line_twips="360")
    patch_style(root, "Caption", font_size_half_points="22", line_twips="240")
    patch_style(root, "FigureCaption", font_size_half_points="22", line_twips="240")
    patch_style(root, "TableCaption", font_size_half_points="22", line_twips="240")
    for style_id in ("Title", "Subtitle", "Heading1", "Heading2", "Heading3", "Heading4", "Heading5", "Heading6"):
        patch_style_font(root, style_id)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def patch_document(path: Path) -> None:
    tree = ET.parse(path)
    root = tree.getroot()
    for paragraph in root.findall(".//w:p", namespaces()):
        text = paragraph_text(paragraph).strip()
        if CAPTION_TEXT_RE.match(text) is None:
            continue
        paragraph_props = find_or_add_first(paragraph, "pPr")
        paragraph_style = find_or_add(paragraph_props, "pStyle")
        paragraph_style.set(qname("val"), "Caption")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.findall(".//w:t", namespaces()))


def patch_doc_defaults(root: ET.Element) -> None:
    defaults = find_or_add(root, "docDefaults")
    run_defaults = find_or_add(defaults, "rPrDefault")
    run_props = find_or_add(run_defaults, "rPr")
    set_run_style(run_props, "24")
    paragraph_defaults = find_or_add(defaults, "pPrDefault")
    paragraph_props = find_or_add(paragraph_defaults, "pPr")
    set_paragraph_spacing(paragraph_props, "360")


def patch_style(root: ET.Element, style_id: str, font_size_half_points: str, line_twips: str) -> None:
    style = root.find(f".//w:style[@w:styleId='{style_id}']", namespaces())
    if style is None:
        return
    run_props = find_or_add(style, "rPr")
    set_run_style(run_props, font_size_half_points)
    if style_id in CAPTION_STYLE_IDS:
        disable_run_italic(run_props)
    paragraph_props = find_or_add(style, "pPr")
    set_paragraph_spacing(paragraph_props, line_twips)


def patch_style_font(root: ET.Element, style_id: str) -> None:
    style = root.find(f".//w:style[@w:styleId='{style_id}']", namespaces())
    if style is None:
        return
    run_props = find_or_add(style, "rPr")
    set_run_font(run_props)


def set_run_style(run_props: ET.Element, font_size_half_points: str) -> None:
    set_run_font(run_props)
    size = find_or_add(run_props, "sz")
    size.set(qname("val"), font_size_half_points)
    complex_size = find_or_add(run_props, "szCs")
    complex_size.set(qname("val"), font_size_half_points)


def set_run_font(run_props: ET.Element) -> None:
    fonts = find_or_add(run_props, "rFonts")
    for attr_name in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qname(attr_name), "Times New Roman")


def disable_run_italic(run_props: ET.Element) -> None:
    for local_name in ("i", "iCs"):
        italic = find_or_add(run_props, local_name)
        italic.set(qname("val"), "0")


def set_paragraph_spacing(paragraph_props: ET.Element, line_twips: str) -> None:
    spacing = find_or_add(paragraph_props, "spacing")
    spacing.set(qname("line"), line_twips)
    spacing.set(qname("lineRule"), "auto")


def find_or_add(parent: ET.Element, local_name: str) -> ET.Element:
    child = parent.find(f"w:{local_name}", namespaces())
    if child is not None:
        return child
    return ET.SubElement(parent, qname(local_name))


def find_or_add_first(parent: ET.Element, local_name: str) -> ET.Element:
    child = parent.find(f"w:{local_name}", namespaces())
    if child is not None:
        return child
    child = ET.Element(qname(local_name))
    parent.insert(0, child)
    return child


def namespaces() -> dict[str, str]:
    return {"w": W_NS}


def qname(local_name: str) -> str:
    return f"{{{W_NS}}}{local_name}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply MESA manuscript default Word styles to a DOCX file.")
    parser.add_argument("docx", type=Path)
    args = parser.parse_args()
    apply_default_word_styles(args.docx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
