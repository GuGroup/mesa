#!/usr/bin/env python3
"""Create a BibTeX/Pandoc-cited DOCX from citation-selector JSON."""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2
CITE_RE = re.compile(r"\{\{cite:([^{}]+)\}\}")
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16se": "http://schemas.microsoft.com/office/word/2015/wordml/symex",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16": "http://schemas.microsoft.com/office/word/2018/wordml",
    "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
    "w16sdtdh": "http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "v": "urn:schemas-microsoft-com:vml",
    "o": "urn:schemas-microsoft-com:office:office",
    "w10": "urn:schemas-microsoft-com:office:word",
}
for _prefix, _uri in NS.items():
    ET.register_namespace(_prefix, _uri)

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

NUMERIC_CSL = """<?xml version="1.0" encoding="utf-8"?>
<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text" default-locale="en-US">
  <info>
    <title>Minimal Numeric</title>
    <id>https://mesa.local/csl/minimal-numeric</id>
    <link href="https://mesa.local/csl/minimal-numeric" rel="self"/>
    <author>
      <name>MESA manuscript pipeline</name>
    </author>
    <category citation-format="numeric"/>
    <category field="science"/>
    <updated>2026-07-06T00:00:00+00:00</updated>
    <rights license="http://creativecommons.org/licenses/by-sa/3.0/">This work is licensed under a Creative Commons Attribution-ShareAlike 3.0 License</rights>
  </info>
  <macro name="author">
    <names variable="author" delimiter=", ">
      <name initialize-with=". " name-as-sort-order="all"/>
      <substitute>
        <text variable="title"/>
      </substitute>
    </names>
  </macro>
  <macro name="issued-year">
    <date variable="issued">
      <date-part name="year"/>
    </date>
  </macro>
  <citation collapse="citation-number">
    <sort>
      <key variable="citation-number"/>
    </sort>
    <layout prefix="[" suffix="]" delimiter=",">
      <text variable="citation-number"/>
    </layout>
  </citation>
  <bibliography second-field-align="flush" et-al-min="7" et-al-use-first="6">
    <layout suffix=".">
      <text variable="citation-number" prefix="[" suffix="] "/>
      <text macro="author"/>
      <text variable="title" prefix=". "/>
      <text variable="container-title" prefix=". " font-style="italic"/>
      <text macro="issued-year" prefix=". "/>
      <text variable="volume" prefix=";"/>
      <text variable="page" prefix=":"/>
      <text variable="DOI" prefix=". doi:"/>
    </layout>
  </bibliography>
</style>
"""


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def qn(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def compact_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def paragraph_text(p: ET.Element) -> str:
    return "".join(t.text or "" for t in p.findall(".//w:t", NS))


def add_text_run(p: ET.Element, text: str, *, bold: bool = False, italic: bool = False) -> None:
    if text == "":
        return
    run = ET.SubElement(p, qn("w", "r"))
    if bold or italic:
        rpr = ET.SubElement(run, qn("w", "rPr"))
        if bold:
            ET.SubElement(rpr, qn("w", "b"))
        if italic:
            ET.SubElement(rpr, qn("w", "i"))
    t = ET.SubElement(run, qn("w", "t"))
    if text.startswith(" ") or text.endswith(" "):
        t.set(XML_SPACE, "preserve")
    t.text = text


def replace_paragraph_text(p: ET.Element, text: str) -> None:
    ppr = p.find("./w:pPr", NS)
    for child in list(p):
        if child is not ppr:
            p.remove(child)
    add_text_run(p, text)


def replace_intro_paragraph_text(p: ET.Element, title: str, text: str) -> None:
    ppr = p.find("./w:pPr", NS)
    for child in list(p):
        if child is not ppr:
            p.remove(child)
    add_text_run(p, title, bold=True)
    add_text_run(p, " ")
    add_text_run(p, text)


def make_paragraph_like(template: ET.Element | None, text: str) -> ET.Element:
    p = ET.Element(qn("w", "p"))
    if template is not None:
        ppr = template.find("./w:pPr", NS)
        if ppr is not None:
            p.append(deepcopy_xml(ppr))
    add_text_run(p, text)
    return p


def deepcopy_xml(node: ET.Element) -> ET.Element:
    return ET.fromstring(ET.tostring(node, encoding="utf-8"))


def sanitize_word_xml(xml: str) -> str:
    """Repair namespace prefixes commonly leaked by ElementTree DOCX edits."""
    relationship_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    if "ns6:id=" in xml:
        xml = xml.replace("ns6:id=", "r:id=")
    if "r:id=" in xml and "xmlns:r=" not in xml:
        xml = xml.replace(
            "<w:document ",
            f'<w:document xmlns:r="{relationship_ns}" ',
            1,
        )
    return xml


def sanitize_rels_xml(xml: str) -> str:
    package_rels_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    xml = xml.replace(
        f'<ns0:Relationships xmlns:ns0="{package_rels_ns}">',
        f'<Relationships xmlns="{package_rels_ns}">',
    )
    xml = xml.replace("</ns0:Relationships>", "</Relationships>")
    xml = xml.replace("<ns0:Relationship", "<Relationship")
    xml = xml.replace("</ns0:Relationship>", "</Relationship>")
    return xml


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


def sanitize_docx_package(input_docx: Path, output_docx: Path) -> int:
    """Copy a DOCX while repairing known unbound namespace prefixes."""
    replacements = 0
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    write_path = output_docx
    if input_docx.resolve() == output_docx.resolve():
        write_path = output_docx.with_name(output_docx.name + ".tmp")
    with zipfile.ZipFile(input_docx) as src, zipfile.ZipFile(write_path, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename.endswith(".xml") or info.filename.endswith(".rels"):
                text = data.decode("utf-8", errors="replace")
                fixed = sanitize_rels_xml(sanitize_word_xml(text))
                if info.filename == "word/document.xml":
                    try:
                        root = ET.fromstring(fixed.encode("utf-8"))
                        normalize_mc_ignorable(root)
                        fixed = ET.tostring(root, encoding="unicode", xml_declaration=True)
                    except ET.ParseError:
                        pass
                if fixed != text:
                    replacements += 1
                data = fixed.encode("utf-8")
            dst.writestr(info, data)
    if write_path != output_docx:
        write_path.replace(output_docx)
    return replacements


def find_pandoc() -> Path:
    found = shutil.which("pandoc")
    if found:
        return Path(found)
    local = Path("DEPENDENCY/tools/pandoc/bin/pandoc")
    if local.exists():
        return local
    raise SystemExit("Pandoc was not found on PATH or at DEPENDENCY/tools/pandoc/bin/pandoc.")


def citation_keys_from_placeholder(raw: str) -> list[str]:
    keys = []
    for key in re.split(r"[;,]", raw):
        key = key.strip()
        if key:
            keys.append(key)
    return keys


def pandoc_citation(keys: list[str]) -> str:
    return "[" + "; ".join(f"@{key}" for key in keys) + "]"


def numeric_citation(keys: list[str], numbers: dict[str, int]) -> str:
    resolved = sorted(numbers[key] for key in keys if key in numbers)
    if not resolved:
        return ""
    return "[" + ",".join(str(number) for number in resolved) + "]"


def placeholder_to_pandoc(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return pandoc_citation(citation_keys_from_placeholder(match.group(1)))

    return CITE_RE.sub(repl, text or "")


def placeholder_to_numeric(text: str, numbers: dict[str, int]) -> str:
    def repl(match: re.Match[str]) -> str:
        return numeric_citation(citation_keys_from_placeholder(match.group(1)), numbers)

    return CITE_RE.sub(repl, text or "")


def source_map(cited_json: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("citation_key")): item
        for item in cited_json.get("citation_sources_used", [])
        if item.get("citation_key")
    }


def combine_cited_jsons(cited_jsons: list[dict[str, Any]]) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    source_by_key: dict[str, dict[str, Any]] = {}
    for cited_json in cited_jsons:
        for source in cited_json.get("citation_sources_used", []):
            key = str(source.get("citation_key") or "")
            if key and key not in source_by_key:
                source_by_key[key] = copy.deepcopy(source)
        sections.extend(copy.deepcopy(cited_json.get("sections", [])))
    combined = {
        "schema_version": SCHEMA_VERSION,
        "citation_schema_version": SCHEMA_VERSION,
        "section_source": "combined_cited_sections",
        "sections": sections,
        "citation_sources_used": [],
    }
    combined["citation_sources_used"] = [
        source_by_key[key]
        for key in first_appearance_order(combined)
        if key in source_by_key
    ]
    return combined


def first_appearance_order(cited_json: dict[str, Any]) -> list[str]:
    order: list[str] = []
    seen: set[str] = set()
    for section in cited_json.get("sections", []):
        for block in section.get("content_blocks", []):
            if block.get("type") != "paragraph":
                continue
            text = block.get("text_with_citation_placeholders") or ""
            for match in CITE_RE.finditer(text):
                for key in citation_keys_from_placeholder(match.group(1)):
                    if key not in seen:
                        seen.add(key)
                        order.append(key)
    return order


def citation_number_map(cited_json: dict[str, Any]) -> dict[str, int]:
    return {key: idx + 1 for idx, key in enumerate(first_appearance_order(cited_json))}


def manuscript_replacement_pairs(cited_json: dict[str, Any], numbers: dict[str, int]) -> list[dict[str, str]]:
    pairs: list[dict[str, str]] = []
    for section in cited_json.get("sections", []):
        title = compact_text(section.get("small_title") or section.get("title") or section.get("section_id") or "")
        render_title = bool(section.get("render_title", True))
        first_paragraph = True
        for block in section.get("content_blocks", []):
            if block.get("type") != "paragraph":
                continue
            raw_text = compact_text(block.get("text") or "")
            cited_text = compact_text(
                placeholder_to_numeric(
                    block.get("text_with_citation_placeholders") or block.get("text") or "",
                    numbers,
                )
            )
            if not raw_text:
                continue
            pairs.append(
                {
                    "section_title": title if first_paragraph and render_title else "",
                    "raw_text": raw_text,
                    "replacement_text": cited_text,
                    "target_text": compact_text(f"{title} {raw_text}") if first_paragraph and render_title and title else raw_text,
                }
            )
            first_paragraph = False
    return pairs


def bib_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\\", "\\textbackslash{}")
    text = text.replace("{", "\\{").replace("}", "\\}")
    return text.strip()


def bib_author(authors: Any) -> str:
    if not isinstance(authors, list):
        return ""
    cleaned = [str(a).strip().rstrip(".") for a in authors if str(a).strip()]
    return " and ".join(cleaned)


def bibtex_entry(key: str, source: dict[str, Any] | None) -> str:
    source = source or {}
    title = source.get("title") or source.get("raw_reference") or key
    entry_type = "article" if source.get("doi") or source.get("year") else "misc"
    lines = [f"@{entry_type}{{{key},"]
    lines.append(f"  title = {{{bib_escape(title)}}},")
    author = bib_author(source.get("authors"))
    if author:
        lines.append(f"  author = {{{bib_escape(author)}}},")
    if source.get("year"):
        lines.append(f"  year = {{{bib_escape(str(source.get('year'))[:4])}}},")
    if source.get("doi"):
        lines.append(f"  doi = {{{bib_escape(source.get('doi'))}}},")
    if source.get("raw_reference"):
        lines.append(f"  note = {{{bib_escape(source.get('raw_reference'))}}},")
    lines.append("}")
    return "\n".join(lines)


def write_used_bib(cited_json: dict[str, Any], path: Path) -> tuple[list[str], list[str]]:
    sources = source_map(cited_json)
    warnings: list[str] = []
    keys = first_appearance_order(cited_json)
    entries = []
    for key in keys:
        if key not in sources:
            warnings.append(f"Selected citation key is missing from citation_sources_used: {key}")
        entries.append(bibtex_entry(key, sources.get(key)))
    write_text(path, "\n\n".join(entries) + "\n")
    return keys, warnings


def markdown_escape_plain(text: str) -> str:
    # Keep prose readable while avoiding accidental fenced block starts.
    return (text or "").replace("\n", " ").strip()


def markdown_from_cited_json(cited_json: dict[str, Any], title: str) -> str:
    lines = ["---", f"title: {json.dumps(title)}", "link-citations: true", "reference-section-title: References", "---", ""]
    for section in cited_json.get("sections", []):
        section_title = section.get("title") or section.get("section_id") or "Section"
        lines.extend([f"## {section_title}", ""])
        for block in section.get("content_blocks", []):
            block_type = block.get("type")
            if block_type == "paragraph":
                text = block.get("text_with_citation_placeholders") or block.get("text") or ""
                lines.extend([placeholder_to_pandoc(markdown_escape_plain(text)), ""])
            elif block_type == "equation":
                latex = str(block.get("latex") or "").strip()
                if latex:
                    lines.extend(["$$", latex, "$$", ""])
                explanation = str(block.get("explanation") or "").strip()
                if explanation:
                    lines.extend([explanation, ""])
    return "\n".join(lines).rstrip() + "\n"


def default_outdir(cited_section_json: Path) -> Path:
    if cited_section_json.name == "cited_section_text.json":
        return cited_section_json.parent / "pandoc"
    return cited_section_json.parent / "pandoc"


def run_pandoc(
    pandoc: Path,
    markdown_path: Path,
    bib_path: Path,
    csl_path: Path,
    output_docx: Path,
    reference_docx: Path | None,
) -> list[str]:
    cmd = [
        str(pandoc),
        str(markdown_path),
        "--from=markdown+tex_math_dollars",
        "--to=docx",
        "--citeproc",
        f"--bibliography={bib_path}",
        f"--csl={csl_path}",
        f"--output={output_docx}",
    ]
    if reference_docx:
        cmd.append(f"--reference-doc={reference_docx}")
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"Pandoc failed with code {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return cmd


def validate_docx(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        if "word/document.xml" not in names:
            raise ValueError("DOCX is missing word/document.xml")
        document_xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
        declared_prefixes = set(re.findall(r"\sxmlns:([A-Za-z0-9_]+)=", document_xml))
        ignorable_match = re.search(r"\s(?:mc|ns\d+):Ignorable=\"([^\"]*)\"", document_xml)
        ignorable_prefixes = ignorable_match.group(1).split() if ignorable_match else []
        undeclared_ignorable_prefixes = [
            prefix for prefix in ignorable_prefixes if prefix not in declared_prefixes
        ]
        synthetic_namespace_prefixes = sorted(prefix for prefix in declared_prefixes if re.fullmatch(r"ns\d+", prefix))
        bad_xml = []
        for name in sorted(names):
            if not (name.endswith(".xml") or name.endswith(".rels")):
                continue
            try:
                ET.fromstring(zf.read(name))
            except Exception as exc:  # noqa: BLE001 - report exact parse problem.
                bad_xml.append({"part": name, "error": str(exc)})
    return {
        "docx_path": str(path),
        "has_document_xml": True,
        "xml_parts_parseable": not bad_xml,
        "bad_xml_parts": bad_xml,
        "contains_raw_pandoc_citation_keys": bool(re.search(r"@[A-Za-z0-9_:-]+", document_xml)),
        "contains_raw_citation_placeholders": "{{cite:" in document_xml,
        "contains_bibliography_heading": "References" in document_xml,
        "ignorable_prefixes": ignorable_prefixes,
        "undeclared_ignorable_prefixes": undeclared_ignorable_prefixes,
        "synthetic_namespace_prefixes": synthetic_namespace_prefixes,
        "document_xml_bytes": len(document_xml.encode("utf-8")),
    }


def docx_structure_stats(path: Path) -> dict[str, int]:
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    body = root.find(".//w:body", NS)
    if body is None:
        return {"body_paragraphs": 0, "body_tables": 0, "drawings": 0}
    return {
        "body_paragraphs": sum(1 for child in list(body) if child.tag == qn("w", "p")),
        "body_tables": sum(1 for child in list(body) if child.tag == qn("w", "tbl")),
        "drawings": len(root.findall(".//w:drawing", NS)),
    }


def bibliography_texts_from_docx(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    body = root.find(".//w:body", NS)
    if body is None:
        return []
    paragraphs = [child for child in list(body) if child.tag == qn("w", "p")]
    ref_idx = None
    for idx, p in enumerate(paragraphs):
        if compact_text(paragraph_text(p)) == "References":
            ref_idx = idx
            break
    if ref_idx is None:
        return []
    references = []
    for p in paragraphs[ref_idx + 1 :]:
        text = compact_text(paragraph_text(p))
        if text:
            references.append(text)
    return references


def write_docx_with_document_xml(source_docx: Path, output_docx: Path, document_xml: bytes) -> None:
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_docx.with_name(output_docx.name + ".tmp")
    with zipfile.ZipFile(source_docx) as src, zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            if info.filename == "word/document.xml":
                dst.writestr(info, document_xml)
            else:
                dst.writestr(info, src.read(info.filename))
    tmp_path.replace(output_docx)


def apply_citations_to_manuscript_docx(
    cited_json: dict[str, Any],
    input_docx: Path,
    output_docx: Path,
    standalone_docx: Path,
) -> dict[str, Any]:
    numbers = citation_number_map(cited_json)
    replacements = manuscript_replacement_pairs(cited_json, numbers)
    bibliography_texts = bibliography_texts_from_docx(standalone_docx)
    if not bibliography_texts:
        raise ValueError("Could not extract bibliography paragraphs from standalone Pandoc DOCX.")

    sanitized_input = output_docx.with_name(output_docx.stem + ".input_sanitized.docx")
    input_sanitized_parts = sanitize_docx_package(input_docx, sanitized_input)
    before_stats = docx_structure_stats(sanitized_input)

    with zipfile.ZipFile(sanitized_input) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    body = root.find(".//w:body", NS)
    if body is None:
        raise ValueError("Input DOCX is missing w:body.")

    children = list(body)
    matched: list[str] = []
    unmatched: list[str] = []
    for item in replacements:
        target = item["target_text"]
        match = None
        for child in children:
            if child.tag != qn("w", "p"):
                continue
            current = compact_text(paragraph_text(child))
            if current == target:
                match = child
                break
        if match is None:
            unmatched.append(target[:180])
            continue
        if item["section_title"]:
            replace_intro_paragraph_text(match, item["section_title"], item["replacement_text"])
        else:
            replace_paragraph_text(match, item["replacement_text"])
        matched.append(target[:180])

    children = list(body)
    placeholder_index = None
    placeholder = None
    for idx, child in enumerate(children):
        if child.tag == qn("w", "p") and compact_text(paragraph_text(child)) == "{{REFERENCES_TEXT}}":
            placeholder_index = idx
            placeholder = child
            break
    if placeholder_index is None:
        for idx, child in enumerate(children):
            if child.tag == qn("w", "p") and compact_text(paragraph_text(child)) == "References":
                placeholder_index = idx + 1
                while placeholder_index < len(children):
                    candidate = children[placeholder_index]
                    if candidate.tag != qn("w", "p"):
                        break
                    candidate_text = compact_text(paragraph_text(candidate))
                    if not re.match(r"^\[\d+\]", candidate_text):
                        break
                    body.remove(candidate)
                    children.pop(placeholder_index)
                break
    if placeholder_index is None:
        raise ValueError("Could not find References placeholder or heading in input DOCX.")

    if placeholder is not None:
        body.remove(placeholder)
    insert_at = placeholder_index
    for ref_text in bibliography_texts:
        body.insert(insert_at, make_paragraph_like(placeholder, ref_text))
        insert_at += 1

    normalize_mc_ignorable(root)
    document_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    write_docx_with_document_xml(sanitized_input, output_docx, document_xml)
    output_sanitized_parts = sanitize_docx_package(output_docx, output_docx)
    after_stats = docx_structure_stats(output_docx)
    validation = validate_docx(output_docx)
    return {
        "input_docx": str(input_docx),
        "output_docx": str(output_docx),
        "sanitized_input_docx": str(sanitized_input),
        "input_sanitized_parts": input_sanitized_parts,
        "output_sanitized_parts": output_sanitized_parts,
        "matched_paragraphs": len(matched),
        "unmatched_paragraphs": unmatched,
        "bibliography_paragraphs_inserted": len(bibliography_texts),
        "before_structure": before_stats,
        "after_structure": after_stats,
        "docx_validation": validation,
    }


def write_summary(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Citation DOCX Insertion Summary",
        "",
        f"- Output DOCX: `{report['output_docx']}`",
        f"- Markdown source: `{report['markdown_path']}`",
        f"- BibTeX file: `{report['bib_path']}`",
        f"- CSL file: `{report['csl_path']}`",
        f"- Citation count: {len(report['citation_keys'])}",
        f"- Human-check flags ignored: `{report['human_check_flags_ignored']}`",
        f"- XML parts parseable: `{report['docx_validation']['xml_parts_parseable']}`",
        f"- Contains bibliography heading: `{report['docx_validation']['contains_bibliography_heading']}`",
        f"- Raw citation placeholders found in DOCX XML: `{report['docx_validation']['contains_raw_citation_placeholders']}`",
        f"- Raw Pandoc citation keys found in DOCX XML: `{report['docx_validation']['contains_raw_pandoc_citation_keys']}`",
        f"- Undeclared mc:Ignorable prefixes: `{report['docx_validation']['undeclared_ignorable_prefixes']}`",
        f"- Synthetic namespace prefixes: `{report['docx_validation']['synthetic_namespace_prefixes']}`",
        "",
        "## Citation Keys",
        "",
    ]
    lines.extend(f"- `{key}`" for key in report["citation_keys"])
    lines.extend(["", "## Warnings", ""])
    if report["warnings"]:
        lines.extend(f"- {warning}" for warning in report["warnings"])
    else:
        lines.append("- None")
    write_text(path, "\n".join(lines) + "\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cited-section-json", required=True, type=Path, nargs="+", help="One or more cited_section_text.json files from citation-selector.")
    parser.add_argument("--outdir", type=Path, help="Output directory. Defaults to a pandoc/ folder next to the input.")
    parser.add_argument("--input-docx", type=Path, help="Existing manuscript DOCX to update in place at the package/body level.")
    parser.add_argument("--output-docx", type=Path, help="Output DOCX path. With --input-docx, this is the skeleton-preserving manuscript output; otherwise it is the standalone cited section.")
    parser.add_argument("--reference-docx", type=Path, help="Optional reference DOCX for Pandoc styles.")
    parser.add_argument("--title", default="Methods", help="Markdown document title.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    cited_section_paths = args.cited_section_json
    cited_jsons = [read_json(path) for path in cited_section_paths]
    cited_json = cited_jsons[0] if len(cited_jsons) == 1 else combine_cited_jsons(cited_jsons)
    outdir = args.outdir or default_outdir(cited_section_paths[0])
    outdir.mkdir(parents=True, exist_ok=True)

    markdown_path = outdir / "cited_section.md"
    bib_path = outdir / "used_references.bib"
    csl_path = outdir / "minimal_numeric.csl"
    standalone_docx = outdir / "cited_section.docx"
    if args.input_docx:
        output_docx = args.output_docx or args.input_docx.with_name(f"{args.input_docx.stem}_with_citations.docx")
    else:
        output_docx = args.output_docx or standalone_docx
        standalone_docx = output_docx
    report_path = outdir / "citation_docx_report.json"
    summary_path = outdir / "citation_docx_summary.md"
    reference_docx = args.reference_docx or args.input_docx
    sanitized_reference_docx = outdir / "reference_docx.sanitized.docx" if reference_docx else None

    citation_keys, warnings = write_used_bib(cited_json, bib_path)
    write_text(csl_path, NUMERIC_CSL)
    write_text(markdown_path, markdown_from_cited_json(cited_json, args.title))
    reference_docx_for_pandoc = reference_docx
    reference_sanitized_parts = 0
    if reference_docx and sanitized_reference_docx:
        reference_sanitized_parts = sanitize_docx_package(reference_docx, sanitized_reference_docx)
        reference_docx_for_pandoc = sanitized_reference_docx

    pandoc = find_pandoc()
    cmd = run_pandoc(pandoc, markdown_path, bib_path, csl_path, standalone_docx, reference_docx_for_pandoc)
    standalone_sanitized_parts = sanitize_docx_package(standalone_docx, standalone_docx)
    validation = validate_docx(standalone_docx)
    if not validation["xml_parts_parseable"]:
        warnings.append("Standalone DOCX contains XML parts that Word may not open cleanly.")
    if validation["contains_raw_citation_placeholders"]:
        warnings.append("Standalone DOCX XML still contains raw {{cite:...}} placeholders.")
    if validation["contains_raw_pandoc_citation_keys"]:
        warnings.append("Standalone DOCX XML still contains raw Pandoc citation keys; citeproc may not have resolved all citations.")
    if validation["undeclared_ignorable_prefixes"]:
        warnings.append(
            "Standalone DOCX has undeclared prefixes in mc:Ignorable: "
            + ", ".join(validation["undeclared_ignorable_prefixes"])
        )

    manuscript_update = None
    if args.input_docx:
        manuscript_update = apply_citations_to_manuscript_docx(
            cited_json,
            args.input_docx,
            output_docx,
            standalone_docx,
        )
        if manuscript_update["unmatched_paragraphs"]:
            warnings.append(
                f"Could not match {len(manuscript_update['unmatched_paragraphs'])} manuscript paragraph(s) for citation insertion."
            )
        if not manuscript_update["docx_validation"]["xml_parts_parseable"]:
            warnings.append("Skeleton-preserving manuscript DOCX contains XML parts that Word may not open cleanly.")
        if manuscript_update["docx_validation"]["contains_raw_citation_placeholders"]:
            warnings.append("Skeleton-preserving manuscript DOCX still contains raw {{cite:...}} placeholders.")
        if manuscript_update["docx_validation"]["contains_raw_pandoc_citation_keys"]:
            warnings.append("Skeleton-preserving manuscript DOCX still contains raw Pandoc citation keys.")
        if manuscript_update["docx_validation"]["undeclared_ignorable_prefixes"]:
            warnings.append(
                "Skeleton-preserving manuscript DOCX has undeclared prefixes in mc:Ignorable: "
                + ", ".join(manuscript_update["docx_validation"]["undeclared_ignorable_prefixes"])
            )

    report = {
        "schema_version": SCHEMA_VERSION,
        "input_cited_section_json": str(cited_section_paths[0]),
        "input_cited_section_jsons": [str(path) for path in cited_section_paths],
        "global_citation_mode": len(cited_section_paths) > 1,
        "input_docx": str(args.input_docx) if args.input_docx else None,
        "output_docx": str(output_docx),
        "standalone_docx": str(standalone_docx),
        "markdown_path": str(markdown_path),
        "bib_path": str(bib_path),
        "csl_path": str(csl_path),
        "reference_docx": str(reference_docx) if reference_docx else None,
        "sanitized_reference_docx": str(sanitized_reference_docx) if sanitized_reference_docx else None,
        "reference_sanitized_parts": reference_sanitized_parts,
        "standalone_sanitized_parts": standalone_sanitized_parts,
        "pandoc_path": str(pandoc),
        "pandoc_command": cmd,
        "citation_keys": citation_keys,
        "citation_count": len(citation_keys),
        "human_check_flags_ignored": True,
        "standalone_docx_validation": validation,
        "docx_validation": manuscript_update["docx_validation"] if manuscript_update else validation,
        "manuscript_update": manuscript_update,
        "warnings": warnings,
    }
    write_json(report_path, report)
    write_summary(summary_path, report)

    print(json.dumps({
        "ok": True,
        "output_docx": str(output_docx),
        "standalone_docx": str(standalone_docx),
        "citation_count": len(citation_keys),
        "warnings": len(warnings),
        "outdir": str(outdir),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
