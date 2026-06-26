#!/usr/bin/env python3
"""Decompose a computational chemistry paper PDF into a Python dictionary."""

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

DECOMPOSITION_PROMPT = """You are analyzing a scientific paper.
Your task is to decompose the paper into a structured knowledge representation.
Target domain is computational chemistry.

Read the full PDF, including abstract, introduction, methods, computational details, results, discussion, conclusions, figures, tables, captions, supporting-information pointers, and references/bibliography.

Important distinctions:

1. Problem
* What question is the paper trying to answer?
* What phenomenon is unexplained?

2. Axioms
* Statements that the authors assume, inherit, or build upon.
* These usually originate from cited literature.
* Do NOT include claims first established in the current paper.
* For every axiom, identify the source paper if available.

3. Hypothesis
* What new prediction or mechanism do the authors propose before presenting results?
* This should be derived from the axioms.

4. Experiment
* What calculations, simulations, measurements, datasets, models, or procedures are performed to test the hypothesis?
* Details in DFT method must be included when reported, including slab modeling method, slab composition and surface facet, supercell size, vacuum, number of layers, fixed layers, adsorption site and coverage, transition-state method, specific code, exchange-correlation functional, pseudopotentials or PAW potentials, plane-wave cutoff, k-point mesh, convergence criteria, dispersion correction, solvation model, spin treatment, charge treatment, finite-temperature corrections, thermodynamic corrections, and any VASP settings.
* Include experimental measurements only when they are directly related to computational proof, computational validation, or computational explanation.

5. Results
* What findings are produced by the current paper?
* Results should contain only claims supported by the current work.
* Do NOT classify prior literature claims as results.
* When experimental measurements are present and computational work explains the experimental hypothesis, separate computational results and experimental results.

6. Conclusion
* What causal mechanism or design principle is established?

Additionally extract integrated_results:
* findings where computation explains experiment
* findings where experiment validates computation
* findings where theory and experiment disagree

Output rules:
* Output exactly one Python assignment named paper_decomposition.
* Do not use Markdown fences or prose outside the assignment.
* Use valid Python syntax with double-quoted string keys and string values.
* Use None only when a value is not available; do not use JSON null.
* Prefer author names over citation numbers.
* Resolve Ref. X into full bibliographic information whenever possible.
* Distinguish clearly between inherited knowledge and newly established knowledge.
* If a source paper cannot be identified, leave source as None.
* Do not invent references.
* Do not summarize loosely; preserve mechanistic details.
* Put entire information; do not abbreviate authors or journal names.

For every cited source use this schema:
{
    "authors": "...",
    "year": ...,
    "journal": "...",
    "title": "...",
    "claim_used": "..."
}

For every result add:
{
    "statement": "...",
    "novelty": "current paper"
}

Use this exact top-level schema:
paper_decomposition = {
    "problem": {
        "question": "...",
        "unexplained_phenomenon": "...",
        "context": "..."
    },
    "axioms": {
        "items": [
            {
                "statement": "...",
                "source": {
                    "authors": "...",
                    "year": ...,
                    "journal": "...",
                    "title": "...",
                    "claim_used": "..."
                }
            }
        ]
    },
    "hypothesis": {
        "statement": "...",
        "derived_from_axioms": ["..."],
        "proposed_mechanism_or_prediction": "..."
    },
    "experiment": {
        "computational": {
            "models": ["..."],
            "methods": ["..."],
            "dft_details": {
                "code": "...",
                "functional": "...",
                "pseudopotentials_or_paw": "...",
                "plane_wave_cutoff": "...",
                "k_point_mesh": "...",
                "convergence_criteria": "...",
                "dispersion_correction": "...",
                "slab_model": "...",
                "adsorption_sites": ["..."],
                "transition_state_method": "...",
                "thermodynamic_corrections": "...",
                "other_settings": ["..."]
            },
            "procedures": ["..."]
        },
        "experimental": {
            "measurements_directly_related_to_computation": ["..."],
            "conditions": ["..."],
            "datasets_or_samples": ["..."]
        }
    },
    "results": {
        "computational_results": [
            {
                "statement": "...",
                "novelty": "current paper"
            }
        ],
        "experimental_results": [
            {
                "statement": "...",
                "novelty": "current paper"
            }
        ],
        "integrated_results": {
            "computation_explains_experiment": [
                {
                    "statement": "...",
                    "novelty": "current paper"
                }
            ],
            "experiment_validates_computation": [
                {
                    "statement": "...",
                    "novelty": "current paper"
                }
            ],
            "theory_experiment_disagree": [
                {
                    "statement": "...",
                    "novelty": "current paper"
                }
            ]
        }
    },
    "conclusion": {
        "causal_mechanism": "...",
        "design_principle": "...",
        "scope_or_limitations": "..."
    }
}

If a list has no supported entries, use an empty list. If a scalar field is not reported, use None."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract a computational chemistry paper PDF into a fixed "
            "problem/axioms/hypothesis/experiment/results/conclusion dictionary."
        )
    )
    parser.add_argument("pdf", type=Path, help="Path to a local PDF file.")
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        help=f"Model to use. Defaults to OPENAI_MODEL or {DEFAULT_MODEL}.",
    )
    parser.add_argument(
        "--task-note",
        default="",
        help=(
            "Optional non-conflicting context to append to the fixed extraction "
            "prompt, such as target catalyst, reaction, material, or section range."
        ),
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


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    pdf_bytes = args.pdf.read_bytes()
    encoded = base64.b64encode(pdf_bytes).decode("ascii")
    prompt = DECOMPOSITION_PROMPT
    if args.task_note:
        prompt = f"{prompt}\n\nAdditional user context: {args.task_note}"

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
                    {"type": "input_text", "text": prompt},
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
