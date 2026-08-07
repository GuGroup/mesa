#!/usr/bin/env python3
"""Extract a bounded citation source library from local project PDFs."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b", re.IGNORECASE)
REF_START_RE = re.compile(r"^\s*(?:\[\s*\d+\s*\]|\d{1,4}[\).])\s+")
BRACKET_REF_MARKER_RE = re.compile(r"\[\s*(\d{1,4})\s*\]\s+")
NUMBERED_REF_START_RE = re.compile(r"^\s*(?:\[\s*(\d{1,4})\s*\]|(\d{1,4})[\).])\s+")
REF_HEADING_RE = re.compile(r"^\s*(references|bibliography|literature cited)\b", re.IGNORECASE)
STOP_HEADING_RE = re.compile(
    r"^\s*(supporting information|supplementary materials?|appendix|acknowledg(?:e)?ments?)\s*$",
    re.IGNORECASE,
)
CITATION_KEY_RE = re.compile(r"[A-Za-z][A-Za-z0-9._:+-]{0,127}\Z", re.ASCII)


class PdfExtractionDependencyError(RuntimeError):
    """Raised when the required PDF text extraction executable is unavailable."""


class InvalidCitationKeyError(ValueError):
    def __init__(self, citation_key: str, context: str) -> None:
        self.citation_key = citation_key
        self.context = context
        super().__init__(f"Invalid citation key in {context}: {citation_key[:80]!r}")


def validate_citation_key(value: Any, context: str) -> str:
    if not isinstance(value, str):
        raise InvalidCitationKeyError(str(value), context)
    key = value
    if CITATION_KEY_RE.fullmatch(key) is None:
        raise InvalidCitationKeyError(key, context)
    return key


def norm_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def norm_match(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def clean_doi(raw: str | None) -> str | None:
    if not raw:
        return None
    m = DOI_RE.search(raw)
    if not m:
        return None
    doi = m.group(0).strip().rstrip(".,;)")
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.IGNORECASE)
    return doi or None


def first_valid_doi(*candidates: str | None) -> str | None:
    for candidate in candidates:
        doi = clean_doi(candidate)
        if doi:
            return doi
    return None


def first_match(regex: re.Pattern[str], text: str) -> str | None:
    m = regex.search(text or "")
    return m.group(0) if m else None


def extract_text_with_pdftotext(pdf: Path, mode: str = "layout") -> tuple[str, list[str]]:
    warnings: list[str] = []
    exe = shutil.which("pdftotext")
    if not exe:
        raise PdfExtractionDependencyError(
            "pdftotext was not found; install poppler-utils or provide extracted text another way."
        )
    mode_arg = "-layout" if mode == "layout" else "-raw"
    try:
        proc = subprocess.run(
            [exe, mode_arg, str(pdf), "-"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=90,
        )
    except subprocess.TimeoutExpired:
        return "", [f"pdftotext {mode} mode timed out for {pdf}"]
    if proc.returncode != 0:
        warnings.append(f"pdftotext {mode} mode failed for {pdf}: {proc.stderr.strip()[:300]}")
    return proc.stdout or "", warnings


def parse_search_report(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    text = path.read_text(errors="replace")
    records: list[dict[str, Any]] = []
    blocks = re.split(r"\n(?=###\s+)", text)
    for block in blocks:
        m = re.match(r"###\s+(.+?)\s*\n", block)
        if not m:
            continue
        rec: dict[str, Any] = {"title": norm_space(m.group(1))}
        for key in ("Authors", "Year", "DOI/URL", "Source/database", "Reason for inclusion"):
            km = re.search(rf"^- {re.escape(key)}:\s*(.+)$", block, flags=re.MULTILINE)
            if km:
                rec[key.lower().replace("/", "_").replace(" ", "_")] = norm_space(km.group(1))
        doi = first_match(DOI_RE, block)
        if doi:
            rec["doi"] = clean_doi(doi)
        if "year" not in rec:
            year = first_match(YEAR_RE, block)
            if year:
                rec["year"] = year[:4]
        records.append(rec)
    return records


def match_search_record(text: str, records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None
    sample = norm_match(text[:20000])
    best: tuple[int, dict[str, Any] | None] = (0, None)
    for rec in records:
        score = 0
        title = rec.get("title") or ""
        doi = rec.get("doi") or clean_doi(rec.get("doi_url"))
        if title and norm_match(title) in sample:
            score += 100 + min(len(norm_match(title)), 80)
        if doi and doi.lower() in text[:50000].lower():
            score += 100
        if score > best[0]:
            best = (score, rec)
    return best[1] if best[0] >= 100 else None


def guess_title(text: str, fallback: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    lines = [norm_space(x) for x in text.splitlines()[:120]]
    lines = [x for x in lines if x]
    skip = re.compile(
        r"(doi|journal|copyright|accepted|received|abstract|volume|issue|www\.|http|arxiv|downloaded)",
        re.IGNORECASE,
    )
    block_candidates: list[str] = []
    current: list[str] = []
    heading_skip = re.compile(r"^(article|review|research article|communication|electrocatalysis)$", re.I)
    author_like = re.compile(r"^[A-Z][A-Za-z.\- ]+,\s+[A-Z]")
    for line in lines[:50]:
        if heading_skip.match(line) or skip.search(line):
            if current:
                block_candidates.append(norm_space(" ".join(current)))
                current = []
            continue
        if author_like.search(line) or "@" in line:
            if current:
                block_candidates.append(norm_space(" ".join(current)))
                current = []
            break
        words = line.split()
        if 3 <= len(words) <= 16 and not re.match(r"^\d+$", line):
            current.append(line.rstrip("."))
        elif current:
            block_candidates.append(norm_space(" ".join(current)))
            current = []
    if current:
        block_candidates.append(norm_space(" ".join(current)))
    block_candidates = [x for x in block_candidates if 5 <= len(x.split()) <= 40]
    if block_candidates:
        return max(block_candidates[:8], key=len), warnings

    candidates: list[str] = []
    for line in lines:
        words = line.split()
        if 5 <= len(words) <= 24 and not skip.search(line) and not line.isupper():
            if not re.match(r"^\d+$", line):
                candidates.append(line.rstrip("."))
    if candidates:
        return max(candidates[:12], key=len), warnings
    warnings.append("title_guessed_from_filename")
    return fallback.replace("-", " ").replace("_", " ").strip(), warnings


def parse_authors(raw: str | None) -> list[str]:
    if not raw:
        return []
    raw = re.sub(r"\s*\([^)]*\)", "", raw)
    raw = re.sub(r"\bet al\.?", "", raw, flags=re.IGNORECASE).strip(" ,;")
    if ";" in raw:
        parts = [norm_space(x) for x in raw.split(";") if norm_space(x)]
    elif raw.count(",") >= 2:
        parts = [norm_space(x) for x in raw.split(",") if norm_space(x)]
    else:
        parts = [norm_space(x) for x in re.split(r",\s+(?=[A-Z]\.?\s*[A-Z][a-z])", raw) if norm_space(x)]
    if len(parts) == 1 and " and " in parts[0]:
        parts = [norm_space(x) for x in parts[0].split(" and ") if norm_space(x)]
    normalized: list[str] = []
    for part in parts:
        normalized.extend(norm_space(x).strip("*") for x in re.split(r"\s+and\s+", part) if norm_space(x))
    parts = normalized or parts
    return parts[:20]


def guess_authors_from_front_matter(text: str) -> list[str]:
    lines = [norm_space(x) for x in text.splitlines()[:90]]
    for line in lines:
        if line.count(",") >= 2 and not re.search(r"(citation:|doi|downloaded|copyright|abstract)", line, re.I):
            authors = parse_authors(line)
            if len(authors) >= 2:
                return authors
    return []


def first_author_surname(authors: list[str], fallback: str) -> str:
    if authors:
        first = authors[0]
        if "," in first:
            token = first.split(",", 1)[0]
        else:
            token = first.split()[-1]
        token = re.sub(r"[^A-Za-z0-9]", "", token)
        if token:
            return token
    stem = re.sub(r"[^A-Za-z0-9]+", " ", fallback).strip().split()
    return (stem[0] if stem else "Source").capitalize()


def make_key(base: str, year: str | None, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "", base) or "Source"
    key = f"{base}{year[:4]}" if year else base
    if not key:
        key = "Source"
    candidate = key
    i = 2
    while candidate in used:
        candidate = f"{key}{i}"
        i += 1
    used.add(candidate)
    return candidate


def collection_for_pdf(project: Path, pdf: Path) -> str:
    try:
        rel = pdf.relative_to(project)
    except ValueError:
        return pdf.parent.name
    parts = rel.parts
    if "papers" in parts:
        idx = parts.index("papers")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    if "experimental_data" in parts:
        return "experimental_data"
    return pdf.parent.name


def abstract_excerpt(text: str, limit: int = 900) -> str | None:
    m = re.search(r"\bAbstract\b\s*(.+?)(?:\n\s*(?:Keywords|Introduction|1\.?\s+Introduction)\b)", text, re.I | re.S)
    if not m:
        return None
    return norm_space(m.group(1))[:limit]


def reference_section_bounds(text: str) -> tuple[int, int] | None:
    lines = text.splitlines()
    heading_indices = [i for i, line in enumerate(lines) if REF_HEADING_RE.match(line)]
    if heading_indices:
        start = max(heading_indices)
        for idx in heading_indices:
            if idx > len(lines) * 0.35:
                start = idx
                break
    else:
        start = -1
        for i, line in enumerate(lines):
            if i > len(lines) * 0.35 and REF_START_RE.match(norm_space(line)):
                start = i - 1
                break
        if start < 0:
            return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if STOP_HEADING_RE.match(lines[j]):
            end = j
            break
    return start, end


def reference_section(text: str) -> str:
    bounds = reference_section_bounds(text)
    if not bounds:
        return ""
    lines = text.splitlines()
    start, end = bounds
    return "\n".join(lines[start + 1 : end])


def body_before_references(text: str) -> str:
    bounds = reference_section_bounds(text)
    if not bounds:
        return text
    lines = text.splitlines()
    start, _ = bounds
    return "\n".join(lines[:start])


def clean_reference_entry(entry: str) -> tuple[str | None, str]:
    match = NUMBERED_REF_START_RE.match(entry)
    number = None
    if match:
        number = match.group(1) or match.group(2)
    cleaned = re.sub(r"^\s*(?:\[\s*\d+\s*\]|\d{1,4}[\).])\s*", "", entry)
    return number, norm_space(cleaned)


def split_references(ref_text: str) -> list[dict[str, str | None]]:
    ref_text = deinterleave_reference_columns(ref_text)
    compact = norm_space(ref_text)
    bracket_markers = list(BRACKET_REF_MARKER_RE.finditer(compact))
    bracket_entries: list[tuple[str | None, str]] = []
    if len(bracket_markers) >= 3:
        for i, marker in enumerate(bracket_markers):
            end = bracket_markers[i + 1].start() if i + 1 < len(bracket_markers) else len(compact)
            entry = compact[marker.start() : end]
            bracket_entries.append(clean_reference_entry(entry))

    entries: list[str] = []
    current: list[str] = []
    for raw_line in ref_text.splitlines():
        line = norm_space(raw_line)
        if not line:
            continue
        if REF_START_RE.match(line):
            if current:
                entries.append(norm_space(" ".join(current)))
            current = [line]
        elif current:
            current.append(line)
    if current:
        entries.append(norm_space(" ".join(current)))
    line_entries = [clean_reference_entry(entry) for entry in entries]

    if len(line_entries) < 3:
        chunks = re.split(r"(?=(?:\[\s*\d+\s*\]|\b\d{1,4}[\).])\s+)", compact)
        line_entries = [clean_reference_entry(norm_space(x)) for x in chunks if len(norm_space(x)) > 30]

    candidates = bracket_entries if len(bracket_entries) > len(line_entries) else line_entries

    clean: list[dict[str, str | None]] = []
    for number, raw in candidates:
        if 30 <= len(raw) <= 2500:
            clean.append({"reference_number": number, "raw_reference": raw})
    return clean[:600]


def split_line_at_column_gap(line: str, split_col: int) -> tuple[str, str] | None:
    spans = [m for m in re.finditer(r" {6,}", line) if line[: m.start()].strip() and line[m.end() :].strip()]
    if not spans:
        return None
    best = min(spans, key=lambda m: abs(((m.start() + m.end()) // 2) - split_col))
    if abs(((best.start() + best.end()) // 2) - split_col) > 30:
        return None
    return line[: best.start()].rstrip(), line[best.end() :].rstrip()


def deinterleave_reference_columns(ref_text: str) -> str:
    pages = ref_text.split("\f")
    deinterleaved_pages: list[str] = []
    for page in pages:
        lines = page.splitlines()
        candidate_mids: list[int] = []
        for line in lines:
            for m in re.finditer(r" {6,}", line):
                if m.start() >= 35 and len(line) - m.end() >= 10 and line[: m.start()].strip() and line[m.end() :].strip():
                    candidate_mids.append((m.start() + m.end()) // 2)
        if len(candidate_mids) < 4:
            deinterleaved_pages.append(page)
            continue
        candidate_mids.sort()
        split_col = candidate_mids[len(candidate_mids) // 2]
        left_lines: list[str] = []
        right_lines: list[str] = []
        for line in lines:
            if not line.strip():
                continue
            split = split_line_at_column_gap(line, split_col)
            if split:
                left, right = split
                if left.strip():
                    left_lines.append(left)
                if right.strip():
                    right_lines.append(right)
            elif len(line) > split_col and not line[:split_col].strip():
                right_lines.append(line[split_col:].rstrip())
            else:
                left_lines.append(line.rstrip())
        deinterleaved_pages.append("\n".join(left_lines + right_lines))
    return "\n\f\n".join(deinterleaved_pages)


def is_author_fragment(part: str) -> bool:
    part = norm_space(part).strip(".;")
    if not part or YEAR_RE.search(part) or DOI_RE.search(part):
        return False
    if re.search(r"\b(phys|chem|catal|mater|energy|science|nature|journal|rev|adv|acs|angew|nano)\b", part, re.I):
        return False
    words = part.split()
    if len(words) > 6:
        return False
    return bool(re.search(r"(?:^|\s)[A-Z](?:\.-?[A-Z])?\.", part))


def looks_like_journal_fragment(part: str) -> bool:
    part = norm_space(part)
    if not part:
        return True
    words = part.split()
    journal_terms = re.compile(
        r"\b(phys|rev|chem|journal|j\.|catal|mater|energy|science|nature|nano|acs|adv|angew|appl|surf|soc|lett|commun|int\.|ed\.)\b",
        re.I,
    )
    return bool(journal_terms.search(part)) and len(words) <= 8


def parse_reference_metadata(raw: str) -> dict[str, Any]:
    stripped = norm_space(re.sub(r"^\s*(?:\[\s*\d+\s*\]|\d{1,4}[\).])\s*", "", raw))
    year = (first_match(YEAR_RE, stripped) or "")[:4] or None
    pieces = [norm_space(x) for x in stripped.split(",") if norm_space(x)]
    authors: list[str] = []
    consumed = 0
    for piece in pieces:
        if is_author_fragment(piece):
            authors.append(piece.strip("."))
            consumed += 1
            continue
        break

    title: str | None = None
    remainder = ", ".join(pieces[consumed:]).strip(" ,.")
    if remainder:
        title_candidate = norm_space(remainder.split(",", 1)[0]).rstrip(".")
        title_words = title_candidate.split()
        if 4 <= len(title_words) <= 30 and not looks_like_journal_fragment(title_candidate):
            title = title_candidate

    if not title and not authors:
        sentence_parts = re.split(r"(?<=\.)\s+(?=[A-Z0-9])", stripped)
        stop = re.compile(r"(doi|http|vol\.|issue|pages?|pp\.|copyright)", re.I)
        for part in sentence_parts:
            part = norm_space(part).rstrip(".")
            words = part.split()
            if 4 <= len(words) <= 30 and not stop.search(part) and not looks_like_journal_fragment(part):
                if not re.search(r"^\(?\d{4}\)?$", part):
                    title = part
                    break

    return {"authors": authors[:20], "title": title, "year": year}


def citation_numbers_from_marker(marker_text: str) -> list[str]:
    nums: list[str] = []
    for part in re.split(r"[,;]", marker_text):
        part = part.strip()
        range_match = re.match(r"^(\d{1,4})\s*[-–—]\s*(\d{1,4})$", part)
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            if 0 < start <= end and end - start <= 50:
                nums.extend(str(i) for i in range(start, end + 1))
            continue
        if re.match(r"^\d{1,4}$", part):
            nums.append(str(int(part)))
    return nums


def build_citation_context_index(body_text: str, max_contexts_per_number: int = 4) -> dict[str, list[dict[str, str]]]:
    normalized = norm_space(re.sub(r"-\s+", "", body_text))
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(])", normalized)
    context_index: dict[str, list[dict[str, str]]] = {}
    marker_re = re.compile(r"\[([0-9,\s\-–—]+)\]")
    noisy_context = re.compile(r"\b(E-mail|Department of|University|Copyright|Downloaded from|Correspondence)\b", re.I)
    for sentence in sentences:
        sentence = norm_space(sentence)
        sentence = norm_space(re.sub(r"\b\d+\s+arXiv:\S+(?:\s+\[[^\]]+\])?\s+\d{1,2}\s+\w+\s+\d{4}\b", " ", sentence))
        sentence = norm_space(re.sub(r"\barXiv:\S+(?:\s+\[[^\]]+\])?", " ", sentence))
        if len(sentence) < 30:
            continue
        if noisy_context.search(sentence):
            continue
        for marker in marker_re.finditer(sentence):
            marker_text = marker.group(1)
            for number in citation_numbers_from_marker(marker_text):
                bucket = context_index.setdefault(number, [])
                if len(bucket) < max_contexts_per_number:
                    bucket.append({
                        "citation_marker": f"[{marker_text}]",
                        "sentence": sentence[:1000],
                    })
    return context_index


def ref_dedupe_key(raw: str, doi: str | None) -> str:
    if doi:
        return f"doi:{doi.lower()}"
    return "raw:" + re.sub(r"[^a-z0-9]+", "", raw.lower())[:180]


def bib_escape(text: str | None) -> str:
    if not text:
        return ""
    return text.replace("\\", "\\textbackslash{}").replace("{", "\\{").replace("}", "\\}")


def write_bib(path: Path, primary: list[dict[str, Any]], refs: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    records = [
        (rec, validate_citation_key(rec.get("citation_key"), "BibTeX export"))
        for rec in primary + refs
    ]
    for rec, key in records:
        entry_type = "article" if rec.get("doi") or rec.get("year") else "misc"
        title = rec.get("title") or rec.get("raw_reference", "Untitled source")[:180]
        lines.append(f"@{entry_type}{{{key},")
        lines.append(f"  title = {{{bib_escape(title)}}},")
        if rec.get("authors"):
            lines.append(f"  author = {{{bib_escape(' and '.join(rec['authors']))}}},")
        if rec.get("year"):
            lines.append(f"  year = {{{bib_escape(str(rec['year'])[:4])}}},")
        if rec.get("doi"):
            lines.append(f"  doi = {{{bib_escape(rec['doi'])}}},")
        if rec.get("url"):
            lines.append(f"  url = {{{bib_escape(rec['url'])}}},")
        if rec.get("raw_reference"):
            lines.append(f"  note = {{{bib_escape(rec['raw_reference'][:500])}}},")
        lines.append("}\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def default_canonical_registry() -> Path:
    return Path(__file__).resolve().parents[1] / "references" / "canonical_method_references.json"


class CitationIdentityError(ValueError):
    """Raised when one citation key identifies different references."""

    def __init__(self, citation_key: str) -> None:
        self.citation_key = citation_key
        super().__init__(
            f"Citation key {citation_key} identifies different canonical and extracted references."
        )


def load_canonical_method_references(path: Path | None) -> tuple[list[dict[str, Any]], list[str]]:
    if path is None or not path.exists():
        return [], []
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_records = data.get("references", []) if isinstance(data, dict) else []
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not isinstance(raw_records, list):
        return [], [f"Canonical method reference registry has no references list: {path}"]
    for index, raw in enumerate(raw_records, start=1):
        if not isinstance(raw, dict) or not raw.get("citation_key"):
            warnings.append(f"Skipped canonical method reference {index}: missing citation_key.")
            continue
        key = validate_citation_key(raw["citation_key"], f"canonical registry record {index}")
        records.append({
            "reference_id": f"M{index:04d}",
            "source_id": f"M{index:04d}",
            "citation_key": key,
            "title": raw.get("title"),
            "authors": raw.get("authors", []),
            "year": raw.get("year"),
            "doi": raw.get("doi"),
            "url": raw.get("url"),
            "raw_reference": raw.get("raw_reference"),
            "collection": "canonical_method_references",
            "source_role": "canonical_method_reference",
            "method_tags": raw.get("method_tags", []),
            "backend_family": raw.get("backend_family", "general"),
            "citation_guidance": raw.get("citation_guidance", ""),
            "citation_contexts": [],
            "source_reference_numbers": [],
            "supports": raw.get("method_tags", []),
            "warnings": [],
        })
    return records, warnings


def merge_canonical_references(
    second_neighbors: list[dict[str, Any]],
    canonical: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Preserve canonical identity and reject ambiguous key collisions."""
    canonical_dois = {
        clean_doi(str(record.get("doi") or ""))
        for record in canonical
        if clean_doi(str(record.get("doi") or ""))
    }
    canonical_by_key = {
        str(record.get("citation_key")): record
        for record in canonical
        if record.get("citation_key")
    }
    retained: list[dict[str, Any]] = []
    for record in second_neighbors:
        doi = clean_doi(str(record.get("doi") or ""))
        if doi and doi in canonical_dois:
            continue
        key = str(record.get("citation_key") or "")
        canonical_record = canonical_by_key.get(key)
        if canonical_record is not None:
            canonical_doi = clean_doi(str(canonical_record.get("doi") or ""))
            if doi != canonical_doi:
                raise CitationIdentityError(key)
        retained.append(record)
    return retained, canonical


def write_summary(path: Path, payload: dict[str, Any]) -> None:
    primary = payload["primary_papers"]
    refs = payload["second_neighbor_references"]
    canonical = payload.get("canonical_method_references", [])
    warnings = payload["warnings"]
    context_count = sum(len(r.get("citation_contexts", [])) for r in refs)
    lines = [
        "# Citation Source Summary",
        "",
        f"Project: `{payload['project']}`",
        "",
        f"- Primary project PDFs: {len(primary)}",
        f"- Second-neighbor references: {len(refs)}",
        f"- Canonical method references: {len(canonical)}",
        f"- Second-neighbor citation contexts: {context_count}",
        f"- Additive search: `{payload['extraction_policy']['additive_search']}`",
        "",
        "## Primary Papers",
        "",
    ]
    for rec in primary:
        bits = [rec["paper_id"], rec["citation_key"]]
        if rec.get("year"):
            bits.append(str(rec["year"])[:4])
        if rec.get("doi"):
            bits.append(rec["doi"])
        lines.append(f"- {' | '.join(bits)}: {rec.get('title') or rec['pdf_path']}")
        if rec.get("warnings"):
            lines.append(f"  - Warnings: {', '.join(rec['warnings'])}")
    lines.extend(["", "## Warnings", ""])
    if warnings:
        lines.extend(f"- {w}" for w in warnings)
    else:
        lines.append("- None")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def discover_pdfs(roots: list[Path]) -> list[Path]:
    pdfs: list[Path] = []
    for root in roots:
        if root.exists():
            pdfs.extend(sorted(root.rglob("*.pdf")))
    seen: set[Path] = set()
    out: list[Path] = []
    for pdf in pdfs:
        rp = pdf.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(pdf)
    return out


def build_sources(
    project: Path,
    pdf_roots: list[Path],
    search_report: Path | None,
    canonical_path: Path | None = None,
) -> dict[str, Any]:
    search_records = parse_search_report(search_report)
    pdfs = discover_pdfs(pdf_roots)
    canonical, canonical_warnings = load_canonical_method_references(
        canonical_path or default_canonical_registry()
    )
    reserved_keys = {
        str(record["citation_key"])
        for record in canonical
        if record.get("citation_key")
    }
    primary_used_keys = set(reserved_keys)
    warnings: list[str] = list(canonical_warnings)
    primary: list[dict[str, Any]] = []
    ref_map: dict[str, dict[str, Any]] = {}
    work_items: list[dict[str, Any]] = []

    for idx, pdf in enumerate(pdfs, start=1):
        text, pdf_warnings = extract_text_with_pdftotext(pdf, mode="layout")
        context_text, context_warnings = extract_text_with_pdftotext(pdf, mode="raw")
        rec_warnings = list(pdf_warnings)
        rec_warnings.extend(context_warnings)
        if not text.strip():
            rec_warnings.append("no_extractable_text")

        matched = match_search_record(text, search_records)
        title_warnings: list[str] = []
        if matched:
            title = matched.get("title")
            authors = parse_authors(matched.get("authors"))
            year = (matched.get("year") or first_match(YEAR_RE, text[:20000]) or "")[:4] or None
            doi = first_valid_doi(matched.get("doi"), matched.get("doi_url"), first_match(DOI_RE, text[:50000]))
        else:
            title, title_warnings = guess_title(text, pdf.stem)
            authors = guess_authors_from_front_matter(text)
            year = (first_match(YEAR_RE, text[:20000]) or first_match(YEAR_RE, pdf.stem) or "")[:4] or None
            doi = first_valid_doi(first_match(DOI_RE, text[:50000]))
        rec_warnings.extend(title_warnings)
        if not matched:
            rec_warnings.append("not_matched_to_search_report")

        paper_id = f"P{idx:03d}"
        key_base = first_author_surname(authors, pdf.stem)
        citation_key = make_key(key_base, year, primary_used_keys)
        refs = split_references(reference_section(text))
        context_index = build_citation_context_index(body_before_references(context_text or text))
        if not refs:
            rec_warnings.append("no_reference_list_parsed")

        paper = {
            "paper_id": paper_id,
            "citation_key": citation_key,
            "title": title,
            "authors": authors,
            "year": year,
            "doi": doi,
            "pdf_path": str(pdf),
            "collection": collection_for_pdf(project, pdf),
            "source_role": "primary_project_pdf",
            "abstract_excerpt": abstract_excerpt(text),
            "reference_count": len(refs),
            "supports": [],
            "warnings": rec_warnings,
        }
        primary.append(paper)
        work_items.append({
            "paper_id": paper_id,
            "citation_key": citation_key,
            "pdf_path": str(pdf),
            "refs": refs,
            "context_index": context_index,
        })

    used_keys = reserved_keys | {p["citation_key"] for p in primary}
    for item in work_items:
        paper_id = item["paper_id"]
        citation_key = item["citation_key"]
        pdf_path = item["pdf_path"]
        refs = item["refs"]
        context_index = item["context_index"]
        for ref_entry in refs:
            raw = str(ref_entry["raw_reference"])
            ref_number = ref_entry.get("reference_number")
            doi_ref = first_valid_doi(first_match(DOI_RE, raw))
            dedupe = ref_dedupe_key(raw, doi_ref)
            parsed_ref = parse_reference_metadata(raw)
            year_ref = parsed_ref.get("year")
            if dedupe not in ref_map:
                base = "Reference"
                if parsed_ref["authors"]:
                    base = first_author_surname(parsed_ref["authors"], "Reference")
                elif parsed_ref["title"]:
                    words = re.sub(r"[^A-Za-z0-9]+", " ", parsed_ref["title"]).split()
                    if words:
                        base = words[0]
                ref_map[dedupe] = {
                    "reference_id": "",
                    "citation_key": make_key(base, year_ref, used_keys),
                    "title": parsed_ref["title"],
                    "authors": parsed_ref["authors"],
                    "year": year_ref,
                    "doi": doi_ref,
                    "raw_reference": raw,
                    "cited_by": [],
                    "source_pdf_paths": [],
                    "source_reference_numbers": [],
                    "citation_contexts": [],
                    "source_role": "second_neighbor_reference",
                    "supports": [],
                    "warnings": [] if parsed_ref["title"] or parsed_ref["authors"] or doi_ref else ["metadata_limited_to_raw_reference"],
                }
            ref = ref_map[dedupe]
            if paper_id not in ref["cited_by"]:
                ref["cited_by"].append(paper_id)
            if pdf_path not in ref["source_pdf_paths"]:
                ref["source_pdf_paths"].append(pdf_path)
            if ref_number:
                number_record = {"cited_by": paper_id, "reference_number": ref_number}
                if number_record not in ref["source_reference_numbers"]:
                    ref["source_reference_numbers"].append(number_record)
                for context in context_index.get(str(ref_number), []):
                    context_record = {
                        "cited_by": paper_id,
                        "source_citation_key": citation_key,
                        "reference_number": str(ref_number),
                        "citation_marker": context["citation_marker"],
                        "sentence": context["sentence"],
                    }
                    if context_record not in ref["citation_contexts"]:
                        ref["citation_contexts"].append(context_record)

    second_refs = list(ref_map.values())
    second_refs.sort(key=lambda r: (r.get("year") or "9999", r.get("citation_key") or ""))

    if not pdfs:
        warnings.append("No local PDFs found in configured roots.")
    for p in primary:
        for w in p["warnings"]:
            warnings.append(f"{p['paper_id']} {w}: {p['pdf_path']}")

    second_refs, canonical = merge_canonical_references(second_refs, canonical)
    for i, rec in enumerate(second_refs, start=1):
        rec["reference_id"] = f"R{i:04d}"

    return {
        "schema_version": 3,
        "project": project.name,
        "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "extraction_policy": {
            "additive_search": False,
            "source_scope": "local primary PDFs and explicit reference lists only",
            "pdf_roots": [str(p) for p in pdf_roots],
            "search_report_used_for_primary_metadata_only": str(search_report) if search_report and search_report.exists() else None,
        },
        "primary_papers": primary,
        "second_neighbor_references": second_refs,
        "canonical_method_references": canonical,
        "warnings": warnings,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path, help="Project directory, e.g. project/<project_name>")
    parser.add_argument("--pdf-root", action="append", type=Path, help="PDF root to scan. Can be repeated.")
    parser.add_argument("--search-report", type=Path, help="Optional paper_search/search_report.md for primary metadata matching.")
    parser.add_argument(
        "--canonical-method-references",
        type=Path,
        help="Optional canonical method reference registry. Defaults to the bundled registry.",
    )
    parser.add_argument("--outdir", type=Path, help="Output directory. Defaults to <project>/references.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    project = args.project
    if not project.exists():
        raise SystemExit(f"Project directory does not exist: {project}")
    pdf_roots = args.pdf_root or [
        project / "strategy_generation" / "papers",
        project / "strategy_generation" / "experimental_data",
    ]
    search_report = args.search_report or project / "strategy_generation" / "paper_search" / "search_report.md"
    outdir = args.outdir or project / "references"
    outdir.mkdir(parents=True, exist_ok=True)

    try:
        payload = build_sources(project, pdf_roots, search_report, args.canonical_method_references)
    except InvalidCitationKeyError as exc:
        raise SystemExit(str(exc)) from exc
    (outdir / "citation_sources.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_bib(
        outdir / "library.bib",
        payload["primary_papers"],
        payload["second_neighbor_references"] + payload.get("canonical_method_references", []),
    )
    write_summary(outdir / "citation_source_summary.md", payload)

    print(json.dumps({
        "ok": True,
        "primary_papers": len(payload["primary_papers"]),
        "second_neighbor_references": len(payload["second_neighbor_references"]),
        "canonical_method_references": len(payload.get("canonical_method_references", [])),
        "outdir": str(outdir),
        "warnings": len(payload["warnings"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
