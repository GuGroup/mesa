from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from paper_search.models import DocumentBlock


def parse_xml_blocks(path: Path, paper_id: str, parse_id: str) -> list[DocumentBlock]:
    root = ET.parse(path).getroot()
    blocks: list[DocumentBlock] = []

    title = _first_text(root, {"article-title", "titleStmt", "title"})
    if title:
        blocks.append(
            DocumentBlock(
                paper_id=paper_id,
                parse_id=parse_id,
                block_type="title",
                text=title,
                confidence=0.95,
            )
        )

    for abstract in _iter_local(root, "abstract"):
        text = _clean_text(_inner_text(abstract))
        if text:
            blocks.append(
                DocumentBlock(
                    paper_id=paper_id,
                    parse_id=parse_id,
                    block_type="abstract",
                    text=text,
                    section="Abstract",
                    confidence=0.9,
                )
            )

    for section in _iter_local(root, "sec"):
        section_title = _section_title(section)
        for paragraph in _iter_local(section, "p"):
            text = _clean_text(_inner_text(paragraph))
            if text:
                blocks.append(
                    DocumentBlock(
                        paper_id=paper_id,
                        parse_id=parse_id,
                        block_type="paragraph",
                        text=text,
                        section=section_title,
                        confidence=0.85,
                    )
                )

    for div in _iter_local(root, "div"):
        section_title = _section_title(div)
        for paragraph in _iter_direct_or_nested(div, "p"):
            text = _clean_text(_inner_text(paragraph))
            if text:
                blocks.append(
                    DocumentBlock(
                        paper_id=paper_id,
                        parse_id=parse_id,
                        block_type="paragraph",
                        text=text,
                        section=section_title,
                        confidence=0.8,
                    )
                )

    # Elsevier full-text (xocs/ce schema): body paragraphs live in <ce:para> /
    # <ce:simple-para> inside <ce:section>, whose local names do not match the
    # JATS <sec>/<p> or TEI <div>/<p> passes above, so the article body would
    # otherwise be dropped. Extract each paragraph once with its nearest section
    # title, skipping any already covered by the <ce:abstract> block.
    elsevier_paras = [
        para for tag in ("para", "simple-para") for para in _iter_local(root, tag)
    ]
    if elsevier_paras:
        parent = {child: node for node in root.iter() for child in node}
        for para in elsevier_paras:
            if _has_ancestor(parent, para, {"abstract"}):
                continue
            text = _clean_text(_inner_text(para))
            if text:
                blocks.append(
                    DocumentBlock(
                        paper_id=paper_id,
                        parse_id=parse_id,
                        block_type="paragraph",
                        text=text,
                        section=_ancestor_section_title(parent, para),
                        confidence=0.8,
                    )
                )

    for node_name, block_type in (
        ("fig", "figure_caption"),
        ("figure", "figure_caption"),  # Elsevier ce:figure
        ("table-wrap", "table"),
        ("table", "table"),  # Elsevier ce:table
    ):
        for node in _iter_local(root, node_name):
            caption = _caption_text(node)
            if caption:
                blocks.append(
                    DocumentBlock(
                        paper_id=paper_id,
                        parse_id=parse_id,
                        block_type=block_type,
                        text=caption,
                        figure_or_table=_label_text(node),
                        confidence=0.8,
                    )
                )
    return _dedupe_blocks(blocks)


def blocks_to_dicts(blocks: list[DocumentBlock]) -> list[dict]:
    return [block.to_dict() for block in blocks if block.text.strip()]


def markdown_to_blocks(path: Path, paper_id: str, parse_id: str) -> list[DocumentBlock]:
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks: list[DocumentBlock] = []
    section = None
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if current:
                blocks.append(
                    DocumentBlock(
                        paper_id=paper_id,
                        parse_id=parse_id,
                        block_type="paragraph",
                        text=_clean_text(" ".join(current)),
                        section=section,
                        confidence=0.65,
                    )
                )
                current = []
            section = stripped.lstrip("#").strip()
            continue
        if not stripped:
            if current:
                blocks.append(
                    DocumentBlock(
                        paper_id=paper_id,
                        parse_id=parse_id,
                        block_type="paragraph",
                        text=_clean_text(" ".join(current)),
                        section=section,
                        confidence=0.65,
                    )
                )
                current = []
            continue
        current.append(stripped)
    if current:
        blocks.append(
            DocumentBlock(
                paper_id=paper_id,
                parse_id=parse_id,
                block_type="paragraph",
                text=_clean_text(" ".join(current)),
                section=section,
                confidence=0.65,
            )
        )
    return blocks


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _iter_local(root: ET.Element, name: str):
    for element in root.iter():
        if _local_name(element.tag) == name:
            yield element


def _iter_direct_or_nested(root: ET.Element, name: str):
    for element in root.iter():
        if element is not root and _local_name(element.tag) == name:
            yield element


def _inner_text(element: ET.Element) -> str:
    return " ".join(part for part in element.itertext())


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _first_text(root: ET.Element, names: set[str]) -> str | None:
    for element in root.iter():
        if _local_name(element.tag) in names:
            text = _clean_text(_inner_text(element))
            if text:
                return text
    return None


def _section_title(section: ET.Element) -> str | None:
    # "section-title" is the Elsevier ce: section heading element.
    for child in list(section):
        if _local_name(child.tag) in {"title", "head", "section-title"}:
            text = _clean_text(_inner_text(child))
            if text:
                return text
    return None


def _has_ancestor(parent: dict, element: ET.Element, names: set[str]) -> bool:
    current = parent.get(element)
    while current is not None:
        if _local_name(current.tag) in names:
            return True
        current = parent.get(current)
    return False


def _ancestor_section_title(parent: dict, element: ET.Element) -> str | None:
    current = parent.get(element)
    while current is not None:
        if _local_name(current.tag) in {"section", "sec"}:
            title = _section_title(current)
            if title:
                return title
        current = parent.get(current)
    return None


def _caption_text(node: ET.Element) -> str | None:
    for child in node.iter():
        if _local_name(child.tag) == "caption":
            text = _clean_text(_inner_text(child))
            if text:
                return text
    return None


def _label_text(node: ET.Element) -> str | None:
    for child in list(node):
        if _local_name(child.tag) == "label":
            text = _clean_text(_inner_text(child))
            if text:
                return text
    return None


def _dedupe_blocks(blocks: list[DocumentBlock]) -> list[DocumentBlock]:
    seen: set[tuple[str | None, str, str]] = set()
    unique: list[DocumentBlock] = []
    for block in blocks:
        key = (block.section, block.block_type, block.text)
        if key in seen:
            continue
        seen.add(key)
        unique.append(block)
    return unique
