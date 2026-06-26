#!/usr/bin/env python3
"""Extract broad scientific insights from a local paper PDF."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.5"
MAX_FILE_BYTES = 50 * 1024 * 1024

GENERAL_INSIGHT_PROMPT = """You are analyzing a scientific paper.
Your task is to extract broad, reusable, topic-level insight from the paper.

This is a loose extraction task intended especially for review papers, perspective papers, roadmap papers, and domain-overview papers.
Do not force the paper into a detailed experiment/result schema if the paper is a review.

Target output:
* Output exactly one Python assignment named paper_general_insight.
* Do not use Markdown fences or prose outside the assignment.
* Use valid Python syntax with double-quoted string keys and string values.
* Use None for unavailable scalar values.
* Use empty lists when no supported entries exist.

Extraction priorities:
1. Identify the topic and the paper's central thesis.
2. Extract the field-level problem or motivation.
3. Extract the main conceptual framework used by the paper.
4. Extract general mechanisms and causal explanations.
5. Extract design principles, heuristics, and transferable rules.
6. Extract progress, representative examples, and enabling methods.
7. Extract bottlenecks, challenges, unresolved questions, and risks.
8. Extract future opportunities and research directions.
9. Distinguish reviewed consensus from the review authors' synthesis or perspective.
10. Preserve the paper's domain language without copying long passages.

Rules:
* Prefer general insight over exhaustive detail.
* Do not invent citations, mechanisms, or examples.
* Include representative cited examples only when they support a general insight.
* If a claim is attributed to prior literature and a source is identifiable in the PDF, include the source.
* If the source cannot be identified, use None for source.
* Keep uncertainty explicit when the paper frames a topic as unresolved, speculative, debated, or prospective.
* For review papers, do not classify all reviewed literature as current-paper results. Use "reviewed_consensus" or "review_authors_synthesis".
* If the user provides a focus topic, prioritize insight related to that topic while keeping enough context to understand it.

For any source that is included, use this schema:
{
    "authors": "...",
    "year": ...,
    "journal": "...",
    "title": "...",
    "claim_used": "..."
}

Use this exact top-level schema:
paper_general_insight = {
    "paper": {
        "title": "...",
        "authors": "...",
        "year": ...,
        "journal": "...",
        "paper_type": "review | perspective | roadmap | research_article | other",
        "topic_focus": "..."
    },
    "central_thesis": {
        "statement": "...",
        "why_it_matters": "..."
    },
    "field_problem": {
        "motivation": "...",
        "knowledge_gap_or_bottleneck": "...",
        "target_outcome": "..."
    },
    "conceptual_framework": {
        "organizing_concepts": ["..."],
        "key_variables_or_descriptors": ["..."],
        "classification_scheme": ["..."]
    },
    "general_mechanisms": [
        {
            "statement": "...",
            "mechanistic_logic": "...",
            "status": "reviewed_consensus | review_authors_synthesis | unresolved | speculative",
            "source": {
                "authors": "...",
                "year": ...,
                "journal": "...",
                "title": "...",
                "claim_used": "..."
            }
        }
    ],
    "design_principles": [
        {
            "principle": "...",
            "rationale": "...",
            "applicability": "...",
            "status": "reviewed_consensus | review_authors_synthesis | unresolved | speculative"
        }
    ],
    "representative_examples": [
        {
            "example": "...",
            "insight_supported": "...",
            "source": {
                "authors": "...",
                "year": ...,
                "journal": "...",
                "title": "...",
                "claim_used": "..."
            }
        }
    ],
    "methods_and_tools": {
        "experimental_methods": ["..."],
        "computational_methods": ["..."],
        "data_or_ai_methods": ["..."],
        "why_they_matter": ["..."]
    },
    "challenges": [
        {
            "challenge": "...",
            "why_it_is_hard": "...",
            "impact_on_field": "..."
        }
    ],
    "opportunities": [
        {
            "direction": "...",
            "expected_payoff": "...",
            "needed_capabilities": ["..."]
        }
    ],
    "actionable_takeaways": [
        {
            "takeaway": "...",
            "use_case": "...",
            "caveat": "..."
        }
    ],
    "open_questions": ["..."],
    "short_summary": "..."
}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract broad topic-level insight from a scientific paper PDF."
    )
    parser.add_argument("pdf", type=Path, help="Path to a local PDF file.")
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        help=f"Model to use. Defaults to OPENAI_MODEL or {DEFAULT_MODEL}.",
    )
    parser.add_argument(
        "--topic",
        default="",
        help="Optional focus topic within the paper.",
    )
    parser.add_argument(
        "--task-note",
        default="",
        help="Optional non-conflicting context for downstream use.",
    )
    parser.add_argument(
        "--save-response",
        type=Path,
        help="Write the full API response JSON to this path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and print request metadata without calling the API.",
    )
    return parser.parse_args()


def validate_pdf(path: Path) -> int:
    if not path.exists():
        raise SystemExit(f"PDF does not exist: {path}")
    if not path.is_file():
        raise SystemExit(f"PDF path is not a file: {path}")
    if path.suffix.lower() != ".pdf":
        raise SystemExit(f"Expected a .pdf file: {path}")

    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise SystemExit(
            f"PDF is {size} bytes, which exceeds the 50 MB file-input limit."
        )
    return size


def build_prompt(args: argparse.Namespace) -> str:
    prompt = GENERAL_INSIGHT_PROMPT
    if args.topic:
        prompt = f"{prompt}\n\nFocus topic: {args.topic}"
    if args.task_note:
        prompt = f"{prompt}\n\nAdditional user context: {args.task_note}"
    return prompt


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    pdf_bytes = args.pdf.read_bytes()
    encoded = base64.b64encode(pdf_bytes).decode("ascii")

    return {
        "model": args.model,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "filename": args.pdf.name,
                        "file_data": f"data:application/pdf;base64,{encoded}",
                    },
                    {"type": "input_text", "text": build_prompt(args)},
                ],
            },
        ],
    }


def call_openai(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"OpenAI API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"OpenAI API request failed: {exc.reason}") from exc


def output_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct:
        return direct

    chunks: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)


def main() -> int:
    args = parse_args()
    size = validate_pdf(args.pdf)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "pdf": str(args.pdf),
                    "bytes": size,
                    "model": args.model,
                    "topic": args.topic,
                    "task_note": bool(args.task_note),
                    "api_url": API_URL,
                    "will_call_api": False,
                },
                indent=2,
            )
        )
        return 0

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set.")

    payload = build_payload(args)
    response = call_openai(payload, api_key)

    if args.save_response:
        args.save_response.write_text(json.dumps(response, indent=2), encoding="utf-8")

    text = output_text(response)
    if not text:
        raise SystemExit("No text output found in API response.")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
