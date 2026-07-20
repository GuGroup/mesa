#!/usr/bin/env python3
"""Write a manuscript Introduction section from collected evidence."""

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
DEFAULT_MODEL = "gpt-5.5"
SCHEMA_VERSION = 1
SECTION_ID = "introduction"
SECTION_TITLE = ""
TARGET_PLACEHOLDERS = {"text": "{{INTRODUCTION_TEXT}}"}
MIN_PARAGRAPHS = 2
MAX_PARAGRAPHS = 3
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

INTRODUCTION_PROMPT = """You are writing the Introduction section of a computational chemistry manuscript for heterogeneous catalysis.

You will receive:
1. A compact Introduction evidence digest. This is the factual source for Introduction claims.
2. A compact manuscript context extracted from a DOCX. This is only for continuity and placeholder awareness.

Write manuscript-ready academic Introduction prose from only the provided evidence.

Strict rules:
1. Return JSON only.
2. Return exactly one section object in a top-level "sections" list.
3. The section must have section_id "introduction", title "", small_title "", render_title false, and content_blocks.
4. Write 2-3 cohesive paragraph content_blocks total. Each block must be {"type": "paragraph", "text": "..."}.
5. Build a literature-led narrative following the narrative_order and writing_profile fields in the digest. Do not impose a reaction, material, dopant, electrolyte, or mechanism that is not present in the digest.
6. Use selected-strategy or project-positioning content only in the final paragraph for the present-work framing. Do not write strategy/procedure language.
7. Do not write internal workflow language, including: strategy, procedure, workflow, source, digest, JSON, artifact, manifest, skill, prompt, writer, P001-style ids, C001-style ids, file paths, project paths, or code filenames.
8. Do not mention figures, tables, Results values, calculation counts, execution outcomes, or figure captions.
9. Do not add citations, citation placeholders, bracketed reference numbers, or author-year parentheticals.
10. Do not include equations, bullet lists, markdown, or headings inside paragraph text.
11. Do not overclaim. Avoid "prove", "fully explain", "complete mechanism", or equivalent language.
12. Do not introduce unsupported electronic-analysis objectives such as projected density of states, Bader analysis, charge transfer, or electronic descriptors.
13. Avoid the word "limitations"; use ordinary manuscript phrasing such as "challenges" or "constraints" if needed. Do not write a standalone limitations paragraph. The Introduction should end with the objective and rationale of the present computational study.
14. In public prose, write non-integer numbers with at most two decimal places; keep integers as integers.

Return schema:
{
  "sections": [
    {
      "section_id": "introduction",
      "title": "",
      "small_title": "",
      "render_title": false,
      "content_blocks": [
        {"type": "paragraph", "text": "Academic prose."}
      ]
    }
  ],
  "missing_details": [
    "Concise missing factual detail that would improve the Introduction."
  ]
}
"""

FORBIDDEN_PATTERNS = [
    r"\bselected strategy\b",
    r"\bstrategy_id\b",
    r"\bprocedure\b",
    r"\bprocedures\b",
    r"\bworkflow\b",
    r"\bdigest\b",
    r"\bjson\b",
    r"\bartifact\b",
    r"\bartifacts\b",
    r"\bmanifest\b",
    r"\bmanifests\b",
    r"\bskill\b",
    r"\bskills\b",
    r"\bprompt\b",
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

PROHIBITED_CONTENT_PATTERNS = [
    r"\bFig\.?\s+S?\d+\b",
    r"\bfigure\s+\d+\b",
    r"\bTable\s+\d+\b",
    r"\bResults and Discussion\b",
    r"\bcalculation count\b",
    r"\ball \d+\b",
    r"\b\d+\s+relaxations\b",
    r"\bprove\b",
    r"\bproves\b",
    r"\bproved\b",
    r"\bfully explain\b",
    r"\bcomplete mechanism\b",
    r"\belectronic descriptor",
    r"\belectronic and structural descriptor",
    r"\bprojected density of states\b",
    r"\bPDOS\b",
    r"\bBader\b",
    r"\bcharge transfer\b",
]

CITATION_PATTERNS = [
    r"\{\{cite:",
    r"@[A-Za-z0-9_:-]+",
    r"\[(?:\d+|[,\s\d]+)\]",
    r"\([A-Z][A-Za-z-]+(?:\s+et\s+al\.)?,?\s+\d{4}\)",
]

LIMITATION_PATTERNS = [
    r"\bnot included\b",
    r"\bnot calculated\b",
    r"\bnot available\b",
    r"\bunavailable\b",
    r"\bfuture work\b",
    r"\blimitation(?:s)?\b",
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
            "near_introduction": [],
            "all_placeholders": [],
        }
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    paragraphs = []
    for index, p in enumerate(root.findall(".//w:body/w:p", NS), start=1):
        text = compact_text(paragraph_text(p))
        if text:
            paragraphs.append({"index": index, "style": paragraph_style(p), "text": text})
    all_text = "\n".join(item["text"] for item in paragraphs)
    placeholders = sorted(set(re.findall(r"\{\{[^{}]+\}\}", all_text)))
    placeholder_presence = {name: placeholder in all_text for name, placeholder in TARGET_PLACEHOLDERS.items()}
    outline = [
        {"index": item["index"], "style": item["style"], "text": item["text"]}
        for item in paragraphs
        if item["style"] in {"1", "2", "Heading1", "Heading2"}
        or item["text"] in {"Introduction", "Results and Discussion", "Methods", "References"}
    ]
    near = []
    for idx, item in enumerate(paragraphs):
        if "{{INTRODUCTION_TEXT}}" in item["text"] or item["text"] == "Introduction":
            near = [p["text"] for p in paragraphs[max(0, idx - 4) : idx + 6]]
            break
    return {
        "source_docx": str(path),
        "available": True,
        "target_placeholders": TARGET_PLACEHOLDERS,
        "target_placeholder_presence": placeholder_presence,
        "section_outline": outline,
        "near_introduction": near,
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
    lines.extend(["", "## Near Introduction", ""])
    for text in context.get("near_introduction", []):
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
    request = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"OpenAI API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"OpenAI API request failed: {exc.reason}") from exc


def default_outdir(digest: Path) -> Path:
    if digest.name == "introduction_writer_digest.json" and digest.parent.name == "evidence":
        return digest.parent.parent / "text"
    return digest.parent / "text"


def build_prompt(digest: dict[str, Any], context: dict[str, Any]) -> str:
    return (
        f"{INTRODUCTION_PROMPT}\n\n"
        f"Introduction writer digest:\n{json.dumps(digest, indent=2, ensure_ascii=False)}\n\n"
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


def normalize_one_section(section: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(section, dict):
        raise ValueError("Introduction section must be a JSON object.")
    blocks = []
    raw_blocks = section.get("content_blocks")
    if isinstance(raw_blocks, list):
        for block in raw_blocks:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "").strip().lower()
            if block_type != "paragraph":
                raise ValueError("Introduction writer only supports paragraph content blocks.")
            text = format_numeric_precision(str(block.get("text") or "").strip())
            if text:
                blocks.append({"type": "paragraph", "text": text})
    else:
        for paragraph in split_paragraphs(str(section.get("text") or "")):
            blocks.append({"type": "paragraph", "text": format_numeric_precision(paragraph)})
    if not blocks:
        raise ValueError("Introduction section must contain at least one paragraph block.")
    text = "\n\n".join(block["text"] for block in blocks)
    return {
        "section_id": SECTION_ID,
        "title": "",
        "small_title": "",
        "render_title": False,
        "text": text,
        "content_blocks": blocks,
    }


def normalize_sections(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sections = parsed.get("sections")
    if isinstance(raw_sections, list) and raw_sections:
        return [normalize_one_section(raw_sections[0])]
    if isinstance(parsed.get("section"), dict):
        return [normalize_one_section(parsed["section"])]
    raise ValueError("Output JSON must contain a non-empty sections list or section object.")


def pattern_hits(text: str, patterns: list[str]) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text, flags=re.IGNORECASE)]


def validate_sections(sections: list[dict[str, Any]], digest: dict[str, Any]) -> dict[str, Any]:
    full_text = "\n".join(
        part
        for section in sections
        for part in [section.get("title", ""), section.get("small_title", ""), section.get("text", "")]
    )
    forbidden = pattern_hits(full_text, FORBIDDEN_PATTERNS)
    prohibited = pattern_hits(full_text, PROHIBITED_CONTENT_PATTERNS)
    citations = pattern_hits(full_text, CITATION_PATTERNS)
    limitations = pattern_hits(full_text, LIMITATION_PATTERNS)
    overprecise = overprecise_decimal_literals(full_text)
    paragraph_count = sum(len(section.get("content_blocks", [])) for section in sections)
    role_mentions = {}
    for role in digest.get("narrative_order", []):
        if role == "present_work_framing":
            continue
        role_mentions[role] = any(
            role == point.get("role")
            and any(keyword.lower() in full_text.lower() for keyword in keyword_hints_for_role(role, digest))
            for point in digest.get("evidence_points", [])
        )
    ok = (
        len(sections) == 1
        and not forbidden
        and not prohibited
        and not citations
        and not limitations
        and not overprecise
        and MIN_PARAGRAPHS <= paragraph_count <= MAX_PARAGRAPHS
    )
    return {
        "ok": ok,
        "section_count": len(sections),
        "paragraph_count": paragraph_count,
        "forbidden_patterns": forbidden,
        "prohibited_content_patterns": prohibited,
        "citation_patterns": citations,
        "limitation_patterns": limitations,
        "overprecise_decimal_literals": overprecise,
        "role_mentions_heuristic": role_mentions,
    }


def keyword_hints_for_role(role: str, digest: dict[str, Any]) -> list[str]:
    profile = digest.get("writing_profile", {})
    if isinstance(profile, dict):
        for item in profile.get("introduction_roles", []):
            if isinstance(item, dict) and item.get("role") == role:
                return [str(word) for word in item.get("keywords", []) if str(word)]
    hints: list[str] = []
    for point in digest.get("evidence_points", []):
        if point.get("role") == role:
            hints.extend(re.findall(r"[A-Za-z][A-Za-z0-9_+-]{3,}", str(point.get("claim", "")))[:8])
    return hints[:12]


def clean_deterministic_text(text: str) -> str:
    text = re.sub(r"\[(?:\d+|[,\s\d]+)\]", "", str(text))
    text = re.sub(r"\bFig\.?\s+S?\d+\b", "the manuscript", text)
    text = re.sub(r"\blimitation(?:s)?\b", "constraint", text, flags=re.IGNORECASE)
    return compact_text(text)


def deterministic_sections(digest: dict[str, Any]) -> list[dict[str, Any]]:
    by_role: dict[str, list[str]] = {}
    for point in digest.get("evidence_points", []):
        by_role.setdefault(point.get("role", ""), []).append(point.get("claim", ""))
    positioning = digest.get("project_positioning", {})
    literature_paragraphs: list[str] = []
    for role in digest.get("narrative_order", []):
        if role == "present_work_framing":
            continue
        claims = [claim for claim in by_role.get(role, []) if claim]
        if not claims:
            continue
        text = claims[0] if len(claims) == 1 else f"{claims[0]} {claims[1]}"
        literature_paragraphs.append(clean_deterministic_text(text))
        if len(literature_paragraphs) >= MAX_PARAGRAPHS - 1:
            break
    if not literature_paragraphs:
        literature_paragraphs.append(
            "The collected literature establishes the broader catalytic motivation and the need to connect material design with reaction-relevant thermodynamic descriptors."
        )
    framing = positioning.get("present_work_question") or positioning.get("present_work_gap") or positioning.get("selected_strategy_title")
    if framing:
        final_paragraph = f"The present computational study addresses {clean_deterministic_text(framing)}."
    else:
        final_paragraph = (
            "The present computational analysis therefore focuses on the modeled catalyst structures, "
            "adsorbate states, and free-energy quantities available in the project evidence."
        )
    paragraphs = [*literature_paragraphs, final_paragraph][:MAX_PARAGRAPHS]
    return [normalize_one_section({"content_blocks": [{"type": "paragraph", "text": text} for text in paragraphs]})]


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
    lines = ["# Introduction", ""]
    for section in payload["sections"]:
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
            write_json(outdir / "introduction_section_text.json", payload)
            write_markdown(outdir / "introduction_section_text.md", payload)
            raise SystemExit("LLM output failed validation. See introduction_section_text.json and llm_response.json.")

    write_json(outdir / "introduction_section_text.json", payload)
    write_markdown(outdir / "introduction_section_text.md", payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--digest", required=True, help="Path to introduction_writer_digest.json.")
    parser.add_argument("--manuscript-docx", default="", help="Optional manuscript DOCX used only for compact context extraction.")
    parser.add_argument("--outdir", default="", help="Output directory. Defaults to sibling text/ directory.")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL), help=f"OpenAI model. Defaults to OPENAI_MODEL or {DEFAULT_MODEL}.")
    parser.add_argument("--no-llm", action="store_true", help="Write deterministic smoke-test output without calling OpenAI.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run(args)
    outdir = Path(args.outdir) if args.outdir else default_outdir(Path(payload["source_digest"]))
    print(f"Wrote {outdir / 'introduction_section_text.json'}")
    print(f"Wrote {outdir / 'introduction_section_text.md'}")
    print(f"Wrote {outdir / 'manuscript_context.json'}")
    if not payload.get("validation", {}).get("ok"):
        sys.exit(2)


if __name__ == "__main__":
    main()
