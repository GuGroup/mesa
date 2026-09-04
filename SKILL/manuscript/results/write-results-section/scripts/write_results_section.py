#!/usr/bin/env python3
"""Write a Results and Discussion section from evidence and DOCX context."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.numeric_precision import format_numeric_precision, overprecise_decimal_literals


API_URL = "https://api.openai.com/v1/responses"
FALLBACK_API_URL = os.environ.get(
    "OPENAI_FALLBACK_API_URL", "http://127.0.0.1:10531/v1/responses"
)
FALLBACK_API_KEY = os.environ.get("OPENAI_FALLBACK_API_KEY", "openai-oauth-local")
RETRYABLE_STATUS_CODES = {408, 500, 502, 503, 504}
DEFAULT_MODEL = "gpt-5.5"
SCHEMA_VERSION = 2
SECTION_ID = "results_and_discussion"
SECTION_TITLE = "Results and Discussion"
TARGET_PLACEHOLDERS = {
    "small_title": "{{RESULTS_AND_DISCUSSIONS_SMALL_TITLE}}",
    "text": "{{RESULTS_AND_DISCUSSIONS_TEXT}}",
}
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

RESULTS_PROMPT = """You are writing the Results and Discussion section of a computational chemistry manuscript for heterogeneous catalysis.

You will receive:
1. A compact evidence digest. This is the factual source for Results claims.
2. A compact manuscript context extracted from a DOCX. This is only for continuity, tone, figure order, and target-placeholder awareness.

Write manuscript-ready academic Results and Discussion prose from only the provided evidence.

Strict rules:
1. Return JSON only.
2. Write 2-4 subsection objects in a top-level "sections" list. Each section must have a unique section_id, title "Results and Discussion", a concise small_title, and content_blocks.
3. Each small_title should cover only its local paragraphs, not the entire Results section. Derive focused titles from the figure types, computed quantities, and key findings in the digest.
4. Across all subsections, provide 5-8 paragraph content_blocks total. Each block must be {"type": "paragraph", "text": "..."}.
5. Organize the prose around the figure backbone and key findings, not around procedures or workflow steps.
6. Mention figures naturally using only figure numbers provided in the digest, for example "Fig. 1" or "Fig. S1".
6a. Mention every main-text figure provided in the digest at least once so the DOCX inserter can place each figure near the relevant paragraph. Supporting Information figures may be mentioned only when scientifically helpful.
7. Do not write internal workflow language, including: strategy, procedure, workflow, source, digest, JSON, artifact, manifest, skill, prompt, mapper, realizer, writer, P001-style ids, C001-style ids, file paths, project paths, or code filenames.
8. Do not write planning language such as "planned", "intended", "to be tested", "if supported", or "will be".
9. Do not claim PDOS, Bader charge analysis, charge transfer, kinetic barriers, active-site density, explicit charged OH- solvation, conductivity, or double-layer effects as completed evidence if unavailable or limited in the digest.
10. Do not claim quantitative overpotential or Tafel-slope prediction. Directional consistency with experiment is allowed only if the evidence digest provides it.
11. Do not add citations or citation placeholders.
12. Do not include equations, bullet lists, tables, markdown, or headings inside paragraph text.
13. Use unavailable or limited evidence only as a silent guardrail for claim strength. Do not write a standalone limitation, scope, missing-evidence, or future-work paragraph.
14. Do not enumerate analyses that were not performed. Avoid phrases such as "not included", "not calculated", "unavailable", "were not performed", "would be needed", or "future work".
15. State computed conclusions directly. Do not add meta-commentary telling readers how the agreement, result, finding, or trend "should be interpreted" or "should be understood".
16. In public prose, write non-integer numbers with at most two decimal places; keep integers as integers.

Return schema:
{
  "sections": [
    {
      "section_id": "results_model_space",
      "title": "Results and Discussion",
      "small_title": "Concise local subsection title",
      "content_blocks": [
        {"type": "paragraph", "text": "Academic prose."}
      ]
    }
  ],
  "missing_details": [
    "Concise missing factual detail that would improve the Results section."
  ]
}
"""

FORBIDDEN_PATTERNS = [
    r"\bstrategy\b",
    r"\bstrategies\b",
    r"\bprocedure\b",
    r"\bprocedures\b",
    r"\bworkflow\b",
    r"\bsource\b",
    r"\bsources\b",
    r"\bdigest\b",
    r"\bjson\b",
    r"\bartifact\b",
    r"\bartifacts\b",
    r"\bmanifest\b",
    r"\bmanifests\b",
    r"\bskill\b",
    r"\bskills\b",
    r"\bprompt\b",
    r"\bmapper\b",
    r"\brealizer\b",
    r"\bwriter\b",
    r"\bplanned\b",
    r"\bintended\b",
    r"\bto be tested\b",
    r"\bif supported\b",
    r"\bwill be\b",
    r"\bP\d{3}\b",
    r"\bC\d{3}\b",
    r"\bTASK_[A-Za-z0-9_]+\b",
    r"\bproject/",
    r"/home/",
    r"\b[A-Za-z0-9_.-]+\.json\b",
    r"\b[A-Za-z0-9_.-]+\.py\b",
]

UNSUPPORTED_CLAIM_PATTERNS = [
    r"\bPDOS\b",
    r"\bprojected density of states\b",
    r"\bBader\b",
    r"\bcharge transfer\b",
    r"\bkinetic barrier",
    r"\bNEB\b",
    r"\bactive-site density\b",
    r"\bdouble-layer\b",
    r"\bconductivity\b",
    r"\bquantitative overpotential\b",
    r"\bTafel(?:-|\s)?slope prediction\b",
]

EXPLICIT_LIMITATION_PATTERNS = [
    r"\bnot included\b",
    r"\bnot calculated\b",
    r"\bnot completed\b",
    r"\bnot available\b",
    r"\bunavailable\b",
    r"\bwere not performed\b",
    r"\bwas not performed\b",
    r"\bwere not included\b",
    r"\bwas not included\b",
    r"\bnot performed\b",
    r"\bmissing evidence\b",
    r"\bfuture work\b",
    r"\bwould be needed\b",
    r"\bwould be required\b",
    r"\bwould strengthen\b",
    r"\blimitation(?:s)?\b",
]

INTERPRETATION_DISCLAIMER_PATTERNS = [
    r"\bshould be interpreted\b",
    r"\bshould be understood\b",
    r"\bmust be interpreted\b",
    r"\bmust be understood\b",
    r"\bagreement should\b",
    r"\bresult should\b",
    r"\bresults should\b",
    r"\bfinding should\b",
    r"\bfindings should\b",
    r"\btrend should\b",
    r"\btrends should\b",
    r"\binterpreted at the\b",
    r"\bunderstood at the\b",
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def compact_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def paragraph_text(p: ET.Element) -> str:
    return "".join(t.text or "" for t in p.findall(".//w:t", NS))


def paragraph_style(p: ET.Element) -> str:
    style = p.find("./w:pPr/w:pStyle", NS)
    return style.get(f"{{{NS['w']}}}val") if style is not None else ""


def extract_docx_context(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "source_docx": None,
            "available": False,
            "target_placeholders": TARGET_PLACEHOLDERS,
            "target_placeholder_presence": {},
            "section_outline": [],
            "methods_paragraphs": [],
            "figure_caption_paragraphs": [],
            "all_placeholders": [],
        }
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    paragraphs = []
    for index, p in enumerate(root.findall(".//w:body/w:p", NS), start=1):
        text = compact_text(paragraph_text(p))
        if not text:
            continue
        paragraphs.append({"index": index, "style": paragraph_style(p), "text": text})
    outline = [
        {"index": item["index"], "style": item["style"], "text": item["text"]}
        for item in paragraphs
        if item["style"] in {"1", "2", "Heading1", "Heading2"} or item["text"] in {SECTION_TITLE, "Methods", "References"}
    ]
    all_text = "\n".join(item["text"] for item in paragraphs)
    placeholder_presence = {name: placeholder in all_text for name, placeholder in TARGET_PLACEHOLDERS.items()}
    placeholders = sorted(set(re.findall(r"\{\{[^{}]+\}\}", all_text)))
    methods_paragraphs = []
    in_methods = False
    for item in paragraphs:
        if item["text"] == "Methods":
            in_methods = True
            continue
        if in_methods and item["style"] == "1" and item["text"] != "Methods":
            break
        if in_methods:
            methods_paragraphs.append(item["text"])
    figure_captions = [item["text"] for item in paragraphs if re.match(r"Fig\.?\s+(?:S)?\d+\s*\|", item["text"])]
    return {
        "source_docx": str(path),
        "available": True,
        "target_placeholders": TARGET_PLACEHOLDERS,
        "target_placeholder_presence": placeholder_presence,
        "section_outline": outline,
        "methods_paragraphs": methods_paragraphs[:30],
        "figure_caption_paragraphs": figure_captions,
        "all_placeholders": placeholders,
    }


def write_context_markdown(path: Path, context: dict[str, Any]) -> None:
    lines = ["# Manuscript Context", "", f"- Source DOCX: `{context.get('source_docx')}`", ""]
    lines.extend(["## Target Placeholders", ""])
    for name, present in context.get("target_placeholder_presence", {}).items():
        lines.append(f"- `{name}`: `{present}`")
    lines.extend(["", "## Outline", ""])
    for item in context.get("section_outline", []):
        lines.append(f"- {item['index']}: {item['text']} (`{item['style']}`)")
    lines.extend(["", "## Figure Captions", ""])
    for text in context.get("figure_caption_paragraphs", []):
        lines.append(f"- {text}")
    lines.extend(["", "## Methods Snapshot", ""])
    for text in context.get("methods_paragraphs", [])[:12]:
        lines.append(f"- {text}")
    write_text(path, "\n".join(lines) + "\n")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_default_env() -> None:
    cwd = Path.cwd()
    for path in (cwd / ".env", cwd / "DEPENDENCY" / ".env"):
        load_env_file(path)


def output_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct:
        return direct
    chunks: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)


def parse_json_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(stripped[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM output must be a JSON object.")
    return data


def call_openai(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    for api_url, endpoint_key in (
        (API_URL, api_key),
        (
            os.environ.get("OPENAI_FALLBACK_API_URL", FALLBACK_API_URL),
            os.environ.get("OPENAI_FALLBACK_API_KEY", FALLBACK_API_KEY),
        ),
    ):
        request = urllib.request.Request(
            api_url,
            data=body,
            method="POST",
            headers={"Authorization": f"Bearer {endpoint_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if api_url == API_URL and exc.code in RETRYABLE_STATUS_CODES:
                continue
            detail = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"OpenAI API HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if api_url == API_URL:
                continue
            raise SystemExit(f"OpenAI API request failed: {exc}") from exc
    raise SystemExit("OpenAI API request failed: all endpoints unavailable")


def default_outdir(digest: Path) -> Path:
    if digest.name == "results_writer_digest.json" and digest.parent.name == "evidence":
        return digest.parent.parent / "text"
    return digest.parent / "text"


def build_prompt(digest: dict[str, Any], context: dict[str, Any]) -> str:
    return (
        f"{RESULTS_PROMPT}\n\n"
        f"Results writer digest:\n{json.dumps(digest, indent=2, ensure_ascii=False)}\n\n"
        f"Manuscript context:\n{json.dumps(context, indent=2, ensure_ascii=False)}\n"
    )


def build_payload(model: str, prompt: str) -> dict[str, Any]:
    return {
        "model": model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
    }


def split_paragraphs(text: str) -> list[str]:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = [str(part).strip() for part in re.split(r"\n\s*\n+", normalized)]
    return [part for part in parts if part]


def normalize_one_section(section: dict[str, Any], fallback_index: int) -> dict[str, Any]:
    if not isinstance(section, dict):
        raise ValueError("Each Results section must be a JSON object.")
    section_id = str(section.get("section_id") or f"{SECTION_ID}_{fallback_index}")
    title = format_numeric_precision(str(section.get("title") or SECTION_TITLE).strip())
    small_title = format_numeric_precision(str(section.get("small_title") or "").strip())
    if not small_title:
        raise ValueError("Each Results section must include a non-empty small_title.")
    blocks = []
    raw_blocks = section.get("content_blocks")
    if isinstance(raw_blocks, list):
        for block in raw_blocks:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "").strip().lower()
            if block_type != "paragraph":
                raise ValueError("Results writer v1 only supports paragraph content blocks.")
            text = format_numeric_precision(str(block.get("text") or "").strip())
            if text:
                blocks.append({"type": "paragraph", "text": text})
    else:
        for paragraph in split_paragraphs(str(section.get("text") or "")):
            blocks.append({"type": "paragraph", "text": format_numeric_precision(paragraph)})
    if not blocks:
        raise ValueError("Results section must contain at least one paragraph block.")
    text = "\n\n".join(block["text"] for block in blocks)
    return {
        "section_id": section_id,
        "title": title,
        "small_title": small_title,
        "text": text,
        "content_blocks": blocks,
    }


def normalize_sections(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sections = parsed.get("sections")
    if isinstance(raw_sections, list):
        sections = [normalize_one_section(section, idx) for idx, section in enumerate(raw_sections, start=1)]
    elif isinstance(parsed.get("section"), dict):
        sections = [normalize_one_section(parsed["section"], 1)]
    else:
        raise ValueError("Output JSON must contain a sections list or section object.")
    seen = set()
    for idx, section in enumerate(sections, start=1):
        section_id = str(section.get("section_id") or f"{SECTION_ID}_{idx}")
        if section_id in seen:
            section_id = f"{section_id}_{idx}"
        seen.add(section_id)
        section["section_id"] = section_id
    return sections


def forbidden_hits(text: str) -> list[str]:
    return [pattern for pattern in FORBIDDEN_PATTERNS if re.search(pattern, text, flags=re.IGNORECASE)]


def unsupported_hits(text: str) -> list[str]:
    hits = []
    safe_scope_words = re.compile(
        r"\b(not included|not calculated|not completed|not available|unavailable|excluded|without|no explicit|were not|was not|do not constitute|does not constitute|not constitute)\b",
        flags=re.IGNORECASE,
    )
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for pattern in UNSUPPORTED_CLAIM_PATTERNS:
        for sentence in sentences:
            if not re.search(pattern, sentence, flags=re.IGNORECASE):
                continue
            if safe_scope_words.search(sentence):
                continue
            hits.append(pattern)
            break
    return hits


def explicit_limitation_hits(text: str) -> list[str]:
    return [pattern for pattern in EXPLICIT_LIMITATION_PATTERNS if re.search(pattern, text, flags=re.IGNORECASE)]


def interpretation_disclaimer_hits(text: str) -> list[str]:
    return [
        pattern
        for pattern in INTERPRETATION_DISCLAIMER_PATTERNS
        if re.search(pattern, text, flags=re.IGNORECASE)
    ]


def validate_sections(sections: list[dict[str, Any]], digest: dict[str, Any]) -> dict[str, Any]:
    full_text = "\n".join(
        part
        for section in sections
        for part in [section.get("small_title", ""), section.get("text", "")]
    )
    forbidden = forbidden_hits(full_text)
    unsupported = unsupported_hits(full_text)
    explicit_limitations = explicit_limitation_hits(full_text)
    interpretation_disclaimers = interpretation_disclaimer_hits(full_text)
    overprecise = overprecise_decimal_literals(full_text)
    provided_figures = {
        str(fig.get("figure_number"))
        for fig in digest.get("figure_backbone", [])
        if fig.get("figure_number")
    }
    mentioned_figures = sorted(set(re.findall(r"Fig\.?\s+S?\d+", full_text)))
    unknown_figures = [fig for fig in mentioned_figures if fig not in provided_figures]
    main_figures = sorted(fig for fig in provided_figures if not fig.startswith("Fig. S"))
    missing_main_figures = [fig for fig in main_figures if fig not in mentioned_figures]
    paragraph_count = sum(len(section.get("content_blocks", [])) for section in sections)
    small_titles = [section.get("small_title", "") for section in sections]
    duplicate_small_titles = sorted({title for title in small_titles if small_titles.count(title) > 1})
    ok = (
        not forbidden
        and not unsupported
        and not explicit_limitations
        and not interpretation_disclaimers
        and not overprecise
        and not unknown_figures
        and not missing_main_figures
        and not duplicate_small_titles
        and 4 <= paragraph_count <= 9
        and 1 <= len(sections) <= 4
    )
    return {
        "ok": ok,
        "section_count": len(sections),
        "paragraph_count": paragraph_count,
        "small_titles": small_titles,
        "duplicate_small_titles": duplicate_small_titles,
        "forbidden_patterns": forbidden,
        "unsupported_claim_patterns": unsupported,
        "explicit_limitation_patterns": explicit_limitations,
        "interpretation_disclaimer_patterns": interpretation_disclaimers,
        "overprecise_decimal_literals": overprecise,
        "provided_figures": sorted(provided_figures),
        "mentioned_figures": mentioned_figures,
        "unknown_figures": unknown_figures,
        "missing_main_figures": missing_main_figures,
    }


def deterministic_sections(digest: dict[str, Any]) -> list[dict[str, Any]]:
    figures = [fig for fig in digest.get("figure_backbone", []) if fig.get("figure_number") and not str(fig.get("figure_number")).startswith("Fig. S")]
    findings = digest.get("key_findings", [])
    sections: list[dict[str, Any]] = []
    first_blocks: list[dict[str, str]] = []
    for fig in figures[:3]:
        title = fig.get("title") or fig.get("figure_type") or "Computed result"
        number = fig.get("figure_number")
        caption = fig.get("caption") or ""
        first_blocks.append(
            {
                "type": "paragraph",
                "text": f"{title} in {number} summarizes the corresponding computed evidence. {caption}".strip(),
            }
        )
    if first_blocks:
        sections.append(
            {
                "section_id": "results_figure_backbone",
                "title": SECTION_TITLE,
                "small_title": "Computed Evidence Overview",
                "content_blocks": first_blocks,
            }
        )
    finding_blocks = []
    for finding in findings[:4]:
        text = str(finding.get("finding") or "").strip()
        related = ", ".join(str(x) for x in finding.get("related_figures", []) if x)
        if related:
            text = f"{text} This finding is supported by {related}."
        if text:
            finding_blocks.append({"type": "paragraph", "text": text})
    if finding_blocks:
        sections.append(
            {
                "section_id": "results_key_findings",
                "title": SECTION_TITLE,
                "small_title": "Key Computed Trends",
                "content_blocks": finding_blocks,
            }
        )
    remaining_figures = figures[3:]
    if remaining_figures:
        sections.append(
            {
                "section_id": "results_additional_figures",
                "title": SECTION_TITLE,
                "small_title": "Additional Computed Comparisons",
                "content_blocks": [
                    {
                        "type": "paragraph",
                        "text": f"{fig.get('title') or fig.get('figure_type') or 'The additional comparison'} in {fig.get('figure_number')} provides the corresponding supporting comparison. {fig.get('caption') or ''}".strip(),
                    }
                    for fig in remaining_figures
                ],
            }
        )
    if not sections:
        sections = [
            {
                "section_id": "results_computed_evidence",
                "title": SECTION_TITLE,
                "small_title": "Computed Evidence",
                "content_blocks": [
                    {
                        "type": "paragraph",
                        "text": "The collected Results evidence summarizes the computed model set, calculated quantities, and ranking information available for the manuscript.",
                    }
                ],
            }
        ]
    for section in sections:
        section["text"] = "\n\n".join(block["text"] for block in section["content_blocks"])
    return normalize_sections({"sections": sections})


def assemble_output(
    digest_path: Path,
    manuscript_docx: Path | None,
    digest: dict[str, Any],
    context: dict[str, Any],
    sections: list[dict[str, Any]],
    missing_details: list[str],
    source: str,
) -> dict[str, Any]:
    validation = validate_sections(sections, digest)
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": digest.get("strategy_id", ""),
        "source_digest": str(digest_path),
        "source_manuscript_docx": str(manuscript_docx) if manuscript_docx else None,
        "section_source": source,
        "target_placeholders": TARGET_PLACEHOLDERS,
        "sections": sections,
        "missing_details": missing_details,
        "validation": validation,
        "manuscript_context_path": "manuscript_context.json",
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = ["# Results and Discussion", ""]
    for section in payload["sections"]:
        lines.extend([f"## {section['small_title']}", ""])
        for block in section.get("content_blocks", []):
            lines.extend([block.get("text", ""), ""])
    if payload.get("missing_details"):
        lines.extend(["## Missing Details", ""])
        for item in payload["missing_details"]:
            lines.append(f"- {item}")
        lines.append("")
    lines.extend(["## Validation", "", f"- ok: {payload.get('validation', {}).get('ok')}", ""])
    write_text(path, "\n".join(lines))


def run(args: argparse.Namespace) -> dict[str, Any]:
    digest_path = Path(args.digest)
    digest = read_json(digest_path)
    manuscript_docx = Path(args.manuscript_docx) if args.manuscript_docx else None
    outdir = Path(args.outdir) if args.outdir else default_outdir(digest_path)
    context = extract_docx_context(manuscript_docx)
    write_json(outdir / "manuscript_context.json", context)
    write_context_markdown(outdir / "manuscript_context.md", context)
    prompt = build_prompt(digest, context)
    write_text(outdir / "llm_prompt.txt", prompt)

    if args.no_llm:
        sections = deterministic_sections(digest)
        payload = assemble_output(
            digest_path,
            manuscript_docx,
            digest,
            context,
            sections,
            ["LLM was not used; deterministic smoke-test prose was generated."],
            "deterministic",
        )
    else:
        load_default_env()
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise SystemExit("OPENAI_API_KEY is not set. Export it or add it to DEPENDENCY/.env, or use --no-llm.")
        response = call_openai(build_payload(args.model, prompt), api_key)
        write_json(outdir / "llm_response.json", response)
        parsed = parse_json_text(output_text(response))
        sections = normalize_sections(parsed)
        missing_details = parsed.get("missing_details", [])
        if not isinstance(missing_details, list):
            missing_details = []
        payload = assemble_output(
            digest_path,
            manuscript_docx,
            digest,
            context,
            sections,
            [str(item) for item in missing_details],
            "llm",
        )
        if not payload["validation"]["ok"]:
            write_json(outdir / "results_section_text.json", payload)
            write_markdown(outdir / "results_section_text.md", payload)
            raise SystemExit("LLM output failed validation. See results_section_text.json and llm_response.json.")

    write_json(outdir / "results_section_text.json", payload)
    write_markdown(outdir / "results_section_text.md", payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--digest", required=True, help="Path to results_writer_digest.json.")
    parser.add_argument("--manuscript-docx", default="", help="Optional manuscript DOCX used only for compact context extraction.")
    parser.add_argument("--outdir", default="", help="Output directory. Defaults to sibling text/ directory.")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL), help=f"OpenAI model. Defaults to OPENAI_MODEL or {DEFAULT_MODEL}.")
    parser.add_argument("--no-llm", action="store_true", help="Write deterministic smoke-test output without calling OpenAI.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run(args)
    outdir = Path(args.outdir) if args.outdir else default_outdir(Path(payload["source_digest"]))
    print(f"Wrote {outdir / 'results_section_text.json'}")
    print(f"Wrote {outdir / 'results_section_text.md'}")
    print(f"Wrote {outdir / 'manuscript_context.json'}")
    if not payload.get("validation", {}).get("ok"):
        sys.exit(2)


if __name__ == "__main__":
    main()
