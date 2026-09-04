#!/usr/bin/env python3
"""Write title, abstract, keywords, and conclusion from an assembled manuscript DOCX."""

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
SCHEMA_VERSION = 1
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

TARGET_PLACEHOLDERS = {
    "title": "{{TITLE}}",
    "abstract": "{{ABSTRACT_TEXT}}",
    "keywords": "{{KEYWORDS_TEXT}}",
    "conclusion": "{{CONCLUSION_TEXT}}",
}

AKC_PROMPT = """You are writing the title, abstract, keywords, and conclusion of a computational chemistry manuscript for heterogeneous catalysis.

You will receive compact context extracted from an already assembled DOCX manuscript. The context contains manuscript body text, figure captions, section outline, and remaining placeholders.

Write only the title, abstract, keywords, and conclusion from the provided manuscript context.

Strict rules:
1. Return JSON only.
2. Use only information supported by the manuscript context.
3. Do not add citations, citation placeholders, bracketed reference numbers, or author-year parentheticals.
4. Do not mention figures, tables, figure numbers, or supplementary figures in the abstract or conclusion.
5. Do not write internal workflow language, including: strategy, procedure, workflow, source, digest, JSON, artifact, manifest, skill, prompt, writer, inserter, P001-style ids, C001-style ids, file paths, project paths, or code filenames.
6. Do not introduce unsupported analyses such as projected density of states, Bader charge analysis, charge transfer, kinetic barriers, active-site density, conductivity, explicit charged hydroxide solvation, or double-layer effects unless the manuscript context states they were performed.
7. Do not write standalone limitation, missing-evidence, or future-work paragraphs.
8. Do not overclaim. Avoid "prove", "fully explain", "complete mechanism", or equivalent language.
9. The title must be one line of 8-18 words, without a trailing period.
10. The title must identify the central reaction or property, material/catalyst family, and computational focus when those details are present in the manuscript context, without using "study of".
11. The abstract must be one paragraph of 150-230 words.
12. The keywords must be 5-8 short phrases.
13. The conclusion must contain 2-3 paragraphs totaling 140-300 words.
14. The abstract should cover background, computational approach, main thermodynamic finding, and implication.
15. The conclusion should synthesize the main mechanistic outcome and manuscript-level implication without repeating Methods details.
16. Do not use markdown, bullets, headings, or numbered lists in text fields.
17. In public text, write non-integer numbers with at most two decimal places; keep integers as integers.

Return schema:
{
  "title": {
    "text": "One manuscript title."
  },
  "abstract": {
    "text": "One manuscript abstract paragraph."
  },
  "keywords": [
    "keyword phrase"
  ],
  "conclusion": {
    "paragraphs": [
      "Conclusion paragraph 1.",
      "Conclusion paragraph 2."
    ]
  },
  "missing_details": [
    "Concise detail that would improve title/AKC writing."
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
    r"\bwriter\b",
    r"\binserter\b",
    r"\bP\d{3}\b",
    r"\bC\d{3}\b",
    r"\bTASK_[A-Za-z0-9_]+\b",
    r"\bproject/",
    r"/home/",
    r"\b[A-Za-z0-9_.-]+\.json\b",
    r"\b[A-Za-z0-9_.-]+\.py\b",
    r"\b[A-Za-z0-9_.-]+\.docx\b",
]

CITATION_PATTERNS = [
    r"\{\{cite:",
    r"@[A-Za-z0-9_:-]+",
    r"\[(?:\d+|[,\s\d]+)\]",
    r"\([A-Z][A-Za-z-]+(?:\s+et\s+al\.)?,?\s+\d{4}\)",
]

FIGURE_PATTERNS = [
    r"\bFig\.?\s+S?\d+\b",
    r"\bFigure\s+S?\d+\b",
    r"\bTable\s+S?\d+\b",
]

UNSUPPORTED_PATTERNS = [
    r"\bPDOS\b",
    r"\bprojected density of states\b",
    r"\bBader\b",
    r"\bcharge transfer\b",
    r"\bkinetic barrier",
    r"\bNEB\b",
    r"\bactive-site density\b",
    r"\bdouble-layer\b",
    r"\bconductivity\b",
    r"\bexplicit charged hydroxide solvation\b",
]

LIMITATION_PATTERNS = [
    r"\bnot included\b",
    r"\bnot calculated\b",
    r"\bnot completed\b",
    r"\bnot available\b",
    r"\bunavailable\b",
    r"\bwere not performed\b",
    r"\bwas not performed\b",
    r"\bmissing evidence\b",
    r"\bfuture work\b",
    r"\blimitation(?:s)?\b",
]

OVERCLAIM_PATTERNS = [
    r"\bprove\b",
    r"\bproves\b",
    r"\bproved\b",
    r"\bfully explain\b",
    r"\bcomplete mechanism\b",
]


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


def extract_paragraphs(path: Path) -> list[dict[str, Any]]:
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    paragraphs = []
    for index, p in enumerate(root.findall(".//w:body/w:p", NS), start=1):
        text = compact_text(paragraph_text(p))
        if text:
            paragraphs.append({"index": index, "style": paragraph_style(p), "text": text})
    return paragraphs


def is_major_heading(item: dict[str, Any]) -> bool:
    text = item["text"].strip()
    style = item.get("style", "")
    return style in {"1", "Heading1"} or text in {
        "Abstract",
        "Keywords",
        "Introduction",
        "Results and Discussion",
        "Methods",
        "Conclusion",
        "References",
        "Data availability",
        "Acknowledgements",
        "Author contributions",
        "Competing interests",
    }


def collect_section(paragraphs: list[dict[str, Any]], heading: str, stop_headings: set[str], max_items: int) -> list[str]:
    in_section = False
    collected: list[str] = []
    for item in paragraphs:
        text = item["text"].strip()
        if text == heading:
            in_section = True
            continue
        if not in_section:
            continue
        if text in stop_headings or (is_major_heading(item) and text != heading):
            break
        if "{{" in text and "}}" in text:
            continue
        if text.startswith("References") or re.match(r"^\[\d+\]", text):
            continue
        collected.append(text)
        if len(collected) >= max_items:
            break
    return collected


def extract_docx_context(path: Path) -> dict[str, Any]:
    paragraphs = extract_paragraphs(path)
    all_text = "\n".join(item["text"] for item in paragraphs)
    placeholders = sorted(set(re.findall(r"\{\{[^{}]+\}\}", all_text)))
    placeholder_presence = {name: placeholder in all_text for name, placeholder in TARGET_PLACEHOLDERS.items()}
    outline = [
        {"index": item["index"], "style": item["style"], "text": item["text"]}
        for item in paragraphs
        if is_major_heading(item)
    ]
    stop = {
        "Abstract",
        "Keywords",
        "Introduction",
        "Results and Discussion",
        "Methods",
        "Conclusion",
        "References",
        "Data availability",
        "Acknowledgements",
        "Author contributions",
        "Competing interests",
    }
    intro = collect_section(paragraphs, "Introduction", stop - {"Introduction"}, 8)
    results = collect_section(paragraphs, "Results and Discussion", stop - {"Results and Discussion"}, 12)
    methods = collect_section(paragraphs, "Methods", stop - {"Methods"}, 8)
    captions = [
        item["text"]
        for item in paragraphs
        if re.match(r"^Fig\.?\s+S?\d+\s*\|", item["text"])
    ][:12]
    body_text = intro + results + methods + captions
    return {
        "source_docx": str(path),
        "target_placeholders": TARGET_PLACEHOLDERS,
        "target_placeholder_presence": placeholder_presence,
        "all_placeholders": placeholders,
        "section_outline": outline,
        "introduction_paragraphs": intro,
        "results_paragraphs": results,
        "methods_paragraphs": methods,
        "figure_caption_paragraphs": captions,
        "context_word_count": word_count("\n".join(body_text)),
    }


def write_context_markdown(path: Path, context: dict[str, Any]) -> None:
    lines = ["# AKC-Title Manuscript Context", "", f"- Source DOCX: `{context['source_docx']}`", ""]
    lines.extend(["## Target Placeholders", ""])
    for name, present in context.get("target_placeholder_presence", {}).items():
        lines.append(f"- `{name}`: `{present}`")
    lines.extend(["", "## Outline", ""])
    for item in context.get("section_outline", []):
        lines.append(f"- {item['index']}: {item['text']} (`{item['style']}`)")
    for key, title in [
        ("introduction_paragraphs", "Introduction"),
        ("results_paragraphs", "Results and Discussion"),
        ("methods_paragraphs", "Methods"),
        ("figure_caption_paragraphs", "Figure Captions"),
    ]:
        lines.extend(["", f"## {title}", ""])
        for text in context.get(key, []):
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


def build_prompt(context: dict[str, Any]) -> str:
    return (
        f"{AKC_PROMPT}\n\n"
        f"Manuscript context:\n{json.dumps(context, indent=2, ensure_ascii=False)}\n"
    )


def build_payload(model: str, prompt: str) -> dict[str, Any]:
    return {
        "model": model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
    }


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def split_paragraphs(text: str) -> list[str]:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = [part.strip() for part in re.split(r"\n\s*\n+", normalized)]
    return [part for part in parts if part]


def normalize_output(parsed: dict[str, Any]) -> dict[str, Any]:
    title_raw = parsed.get("title", {})
    if isinstance(title_raw, dict):
        title_text = format_numeric_precision(compact_text(title_raw.get("text", "")))
    else:
        title_text = format_numeric_precision(compact_text(title_raw))
    abstract_raw = parsed.get("abstract", {})
    if isinstance(abstract_raw, dict):
        abstract_text = format_numeric_precision(compact_text(abstract_raw.get("text", "")))
    else:
        abstract_text = format_numeric_precision(compact_text(abstract_raw))
    keywords_raw = parsed.get("keywords", [])
    if isinstance(keywords_raw, str):
        keywords = [format_numeric_precision(compact_text(item)) for item in re.split(r";|,", keywords_raw) if compact_text(item)]
    elif isinstance(keywords_raw, list):
        keywords = [format_numeric_precision(compact_text(item)) for item in keywords_raw if compact_text(item)]
    else:
        keywords = []
    conclusion_raw = parsed.get("conclusion", {})
    if isinstance(conclusion_raw, dict):
        paragraphs_raw = conclusion_raw.get("paragraphs", [])
    else:
        paragraphs_raw = conclusion_raw
    if isinstance(paragraphs_raw, str):
        conclusion_paragraphs = [format_numeric_precision(item) for item in split_paragraphs(paragraphs_raw)]
    elif isinstance(paragraphs_raw, list):
        conclusion_paragraphs = [format_numeric_precision(compact_text(item)) for item in paragraphs_raw if compact_text(item)]
    else:
        conclusion_paragraphs = []
    missing = parsed.get("missing_details", [])
    if not isinstance(missing, list):
        missing = []
    return {
        "title": {"text": title_text},
        "abstract": {"text": abstract_text},
        "keywords": keywords,
        "conclusion": {"paragraphs": conclusion_paragraphs},
        "missing_details": [compact_text(item) for item in missing if compact_text(item)],
    }


def pattern_hits(text: str, patterns: list[str]) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text, flags=re.IGNORECASE)]


def validate_akc(akc: dict[str, Any]) -> dict[str, Any]:
    title_text = akc["title"]["text"]
    abstract_text = akc["abstract"]["text"]
    keywords = akc["keywords"]
    conclusion_paragraphs = akc["conclusion"]["paragraphs"]
    conclusion_text = "\n".join(conclusion_paragraphs)
    full_text = "\n".join([title_text, abstract_text, "; ".join(keywords), conclusion_text])
    title_words = word_count(title_text)
    abstract_words = word_count(abstract_text)
    conclusion_words = word_count(conclusion_text)
    validation = {
        "title_word_count": title_words,
        "abstract_word_count": abstract_words,
        "keyword_count": len(keywords),
        "conclusion_paragraph_count": len(conclusion_paragraphs),
        "conclusion_word_count": conclusion_words,
        "forbidden_patterns": pattern_hits(full_text, FORBIDDEN_PATTERNS),
        "citation_patterns": pattern_hits(full_text, CITATION_PATTERNS),
        "figure_patterns": pattern_hits(full_text, FIGURE_PATTERNS),
        "unsupported_patterns": pattern_hits(full_text, UNSUPPORTED_PATTERNS),
        "limitation_patterns": pattern_hits(full_text, LIMITATION_PATTERNS),
        "overclaim_patterns": pattern_hits(full_text, OVERCLAIM_PATTERNS),
        "title_has_trailing_period": title_text.endswith("."),
        "title_has_study_of": bool(re.search(r"\bstudy of\b", title_text, re.IGNORECASE)),
        "overprecise_decimal_literals": overprecise_decimal_literals(full_text),
    }
    validation["ok"] = (
        6 <= title_words <= 22
        and not validation["title_has_trailing_period"]
        and not validation["title_has_study_of"]
        and 120 <= abstract_words <= 250
        and 4 <= len(keywords) <= 10
        and 1 <= len(conclusion_paragraphs) <= 4
        and 120 <= conclusion_words <= 320
        and not validation["forbidden_patterns"]
        and not validation["citation_patterns"]
        and not validation["figure_patterns"]
        and not validation["unsupported_patterns"]
        and not validation["limitation_patterns"]
        and not validation["overclaim_patterns"]
        and not validation["overprecise_decimal_literals"]
    )
    return validation


def deterministic_akc(context: dict[str, Any]) -> dict[str, Any]:
    title_seed = compact_text((context.get("section_outline", [{}])[0].get("text") if context.get("section_outline") else "") or "")
    title_text = title_seed if 6 <= word_count(title_seed) <= 22 and "{{" not in title_seed else "Computational Thermodynamic Analysis of Catalyst Models"
    abstract = (
        "Computational catalyst manuscripts require concise front matter that reflects only the model systems, calculations, and conclusions already present in the assembled text. "
        "This deterministic abstract summarizes a generic computational study in which catalyst structures are constructed, optimized, corrected for available thermochemical contributions, and compared through computed energetic quantities. "
        "The calculated trends are used to distinguish the tested models and to connect local structure with the reported catalytic descriptors. "
        "The analysis therefore links model definition, adsorbate or intermediate states, and free-energy comparison within a consistent computational framework. "
        "The resulting manuscript framing emphasizes evidence already contained in the body text, avoids unsupported mechanistic claims, and presents the computational comparison as a bounded interpretation of the available model space. "
        "This generic output is intended for validation of the title, abstract, keyword, and conclusion schema when project-specific language is not supplied."
    )
    return {
        "title": {
            "text": title_text
        },
        "abstract": {
            "text": abstract
        },
        "keywords": [
            "computational catalysis",
            "density functional theory",
            "thermodynamic analysis",
            "catalyst models",
            "free-energy descriptors",
        ],
        "conclusion": {
            "paragraphs": [
                "The manuscript uses a consistent computational framework to compare modeled catalyst structures and associated energetic quantities. The calculated trends distinguish the tested models through their relative thermodynamic behavior and provide a direct basis for connecting local structure with catalytic descriptors. This structure-to-energy connection is the central manuscript-level outcome captured by the assembled text.",
                "The resulting analysis supports a focused interpretation of the computed catalyst model space. By separating model construction, adsorbate or intermediate states, and thermochemical contributions, the manuscript identifies the structural and energetic features that control the reported computational ranking. The conclusion therefore remains grounded in the calculations already described in the manuscript body and avoids adding claims beyond the assembled evidence reported here or outside the documented computational scope.",
            ]
        },
        "missing_details": ["LLM was not used; deterministic smoke-test prose was generated."],
    }


def section_payload(
    strategy_id: str,
    manuscript_docx: Path,
    placeholder_key: str,
    section_id: str,
    text_blocks: list[str],
) -> dict[str, Any]:
    blocks = [{"type": "paragraph", "text": text} for text in text_blocks if text]
    section = {
        "section_id": section_id,
        "title": "",
        "small_title": "",
        "render_title": False,
        "text": "\n\n".join(block["text"] for block in blocks),
        "content_blocks": blocks,
    }
    if placeholder_key == "title":
        section["paragraph_style"] = {"bold": True, "font_size_pt": 14}
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": strategy_id,
        "source_manuscript_docx": str(manuscript_docx),
        "target_placeholders": {"text": TARGET_PLACEHOLDERS[placeholder_key]},
        "sections": [section],
        "missing_details": [],
    }


def write_section_jsons(outdir: Path, strategy_id: str, manuscript_docx: Path, akc: dict[str, Any]) -> dict[str, str]:
    title_payload = section_payload(
        strategy_id,
        manuscript_docx,
        "title",
        "title",
        [akc["title"]["text"]],
    )
    abstract_payload = section_payload(
        strategy_id,
        manuscript_docx,
        "abstract",
        "abstract",
        [akc["abstract"]["text"]],
    )
    keywords_text = "; ".join(akc["keywords"])
    keywords_payload = section_payload(
        strategy_id,
        manuscript_docx,
        "keywords",
        "keywords",
        [keywords_text],
    )
    conclusion_payload = section_payload(
        strategy_id,
        manuscript_docx,
        "conclusion",
        "conclusion",
        akc["conclusion"]["paragraphs"],
    )
    paths = {
        "title": "title_section_text.json",
        "abstract": "abstract_section_text.json",
        "keywords": "keywords_section_text.json",
        "conclusion": "conclusion_section_text.json",
    }
    write_json(outdir / paths["title"], title_payload)
    write_json(outdir / paths["abstract"], abstract_payload)
    write_json(outdir / paths["keywords"], keywords_payload)
    write_json(outdir / paths["conclusion"], conclusion_payload)
    return paths


def default_outdir(manuscript_docx: Path, strategy_id: str) -> Path:
    project_root = None
    parts = list(manuscript_docx.parts)
    for idx, part in enumerate(parts):
        if part == "project" and idx + 1 < len(parts):
            project_root = Path(*parts[: idx + 2])
            break
    if project_root is not None:
        return project_root / "strategy_execution" / f"{strategy_id}_akctitle" / "text"
    return manuscript_docx.parent / f"{strategy_id}_akctitle" / "text"


def assemble_output(
    strategy_id: str,
    manuscript_docx: Path,
    source: str,
    akc: dict[str, Any],
    section_paths: dict[str, str],
    validation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": strategy_id,
        "source_manuscript_docx": str(manuscript_docx),
        "section_source": source,
        "target_placeholders": TARGET_PLACEHOLDERS,
        "title": akc["title"],
        "abstract": akc["abstract"],
        "keywords": akc["keywords"],
        "conclusion": akc["conclusion"],
        "section_json_paths": section_paths,
        "missing_details": akc.get("missing_details", []),
        "validation": validation,
        "manuscript_context_path": "manuscript_context.json",
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = ["# Title, Abstract, Keywords, and Conclusion", ""]
    lines.extend(["## Title", "", payload["title"]["text"], ""])
    lines.extend(["## Abstract", "", payload["abstract"]["text"], ""])
    lines.extend(["## Keywords", "", "; ".join(payload["keywords"]), ""])
    lines.extend(["## Conclusion", ""])
    for paragraph in payload["conclusion"]["paragraphs"]:
        lines.extend([paragraph, ""])
    if payload.get("missing_details"):
        lines.extend(["## Missing Details", ""])
        for item in payload["missing_details"]:
            lines.append(f"- {item}")
        lines.append("")
    lines.extend(["## Validation", "", f"- ok: {payload.get('validation', {}).get('ok')}", ""])
    write_text(path, "\n".join(lines))


def run(args: argparse.Namespace) -> dict[str, Any]:
    manuscript_docx = Path(args.manuscript_docx)
    strategy_id = args.strategy_id
    outdir = Path(args.outdir) if args.outdir else default_outdir(manuscript_docx, strategy_id)
    context = extract_docx_context(manuscript_docx)
    write_json(outdir / "manuscript_context.json", context)
    write_context_markdown(outdir / "manuscript_context.md", context)
    prompt = build_prompt(context)
    write_text(outdir / "llm_prompt.txt", prompt)

    if args.no_llm:
        akc = normalize_output(deterministic_akc(context))
        source = "deterministic"
    else:
        load_default_env()
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise SystemExit("OPENAI_API_KEY is not set. Export it or add it to DEPENDENCY/.env, or use --no-llm.")
        response = call_openai(build_payload(args.model, prompt), api_key)
        write_json(outdir / "llm_response.json", response)
        akc = normalize_output(parse_json_text(output_text(response)))
        source = "llm"

    validation = validate_akc(akc)
    section_paths = write_section_jsons(outdir, strategy_id, manuscript_docx, akc)
    payload = assemble_output(strategy_id, manuscript_docx, source, akc, section_paths, validation)
    write_json(outdir / "title_abstract_keywords_conclusion_text.json", payload)
    write_markdown(outdir / "title_abstract_keywords_conclusion_text.md", payload)
    if not validation["ok"]:
        raise SystemExit("AKC-title output failed validation. See title_abstract_keywords_conclusion_text.json and llm_response.json.")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manuscript-docx", required=True, help="Assembled manuscript DOCX.")
    parser.add_argument("--strategy-id", default="S1", help="Strategy id used for output naming.")
    parser.add_argument("--outdir", default="", help="Output directory. Defaults to project/<project>/strategy_execution/<strategy>_akctitle/text.")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL), help=f"OpenAI model. Defaults to OPENAI_MODEL or {DEFAULT_MODEL}.")
    parser.add_argument("--no-llm", action="store_true", help="Write deterministic smoke-test output without calling OpenAI.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run(args)
    outdir = Path(args.outdir) if args.outdir else default_outdir(Path(args.manuscript_docx), args.strategy_id)
    print(f"Wrote {outdir / 'title_abstract_keywords_conclusion_text.json'}")
    print(f"Wrote {outdir / 'title_section_text.json'}")
    print(f"Wrote {outdir / 'abstract_section_text.json'}")
    print(f"Wrote {outdir / 'keywords_section_text.json'}")
    print(f"Wrote {outdir / 'conclusion_section_text.json'}")
    if not payload.get("validation", {}).get("ok"):
        sys.exit(2)


if __name__ == "__main__":
    main()
