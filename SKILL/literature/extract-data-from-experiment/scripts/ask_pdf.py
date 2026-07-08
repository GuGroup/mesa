#!/usr/bin/env python3
"""Extract DFT-relevant experimental information from a local PDF."""

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
EXTRACTION_PROMPT = """You are an information extraction system for computational materials research.

Your task is to extract ONLY experimentally reported information that can reduce uncertainty when setting up a DFT calculation.

Return only information explicitly stated, measured, observed, fitted, or reported in the document.

DO NOT:
- generate hypotheses
- propose mechanisms
- infer missing information
- recommend DFT settings
- suggest computational methods
- speculate about atomic structures
- predict properties
- provide interpretations beyond what is explicitly reported
- provide scientific discussion
- provide summaries not directly tied to DFT-relevant information

If a piece of information is not explicitly present in the document, do not mention it.

Extract the following categories when available:

1. Material identity
   - chemical formula
   - composition
   - stoichiometry
   - dopants
   - impurities

2. Crystal and structural information
   - crystal structure
   - space group
   - lattice parameters
   - atomic positions
   - site occupancies
   - phase information
   - polymorphs
   - defects explicitly identified

3. Experimental conditions
   - synthesis method
   - temperature
   - pressure
   - atmosphere
   - annealing conditions
   - growth conditions

4. Measured properties
   - electronic properties
   - magnetic properties
   - optical properties
   - electrochemical properties
   - mechanical properties
   - thermodynamic properties

5. Characterization results
   - XRD
   - XPS
   - Raman
   - TEM
   - SEM
   - EELS
   - EXAFS
   - XANES
   - neutron scattering
   - other reported characterization data

Inspect all document regions, including body text, tables, figure captions, figure panels, plots, axis labels, tick labels, legends, annotations, microscopy images, spectra, diffraction patterns, schematics, and graphical abstracts.

Explicitly check figures and extract data visible in figures when available:
- values printed in plots or annotations
- axis labels, units, scales, tick values, and plotted quantities
- legend labels and compared samples
- peak positions, binding energies, Raman shifts, diffraction angles, current density, voltage, efficiency, yield, selectivity, time, temperature, pressure, and composition values
- morphology, particle size, dispersion, phase, elemental mapping, or microscopy observations stated in figure labels, captions, or visible annotations

Do not ignore figure-only information. If a value appears only in a figure, report it and identify the figure/panel or nearby caption as evidence when possible.

For each extracted item:
- provide the exact value when available
- provide units when available
- provide the evidence sentence or nearby quotation from the document

Return a concise structured text report, not JSON.

Use these section headings exactly:
- Material identity
- Crystal and structural information
- Experimental conditions
- Measured properties
- Characterization results
- Figure-extracted data
- Missing information

In each section, use bullet points. Include evidence for every bullet point. The "Missing information" section may only contain categories that were searched for but not explicitly reported in the document.

Never include hypotheses, recommendations, assumptions, interpretations, or proposed DFT inputs.

When uncertain whether information is explicitly reported or inferred, exclude it."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract DFT-relevant experimental information from a PDF using a "
            "fixed materials-research prompt that explicitly checks figures."
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
            "prompt, such as a target material name."
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
    prompt = EXTRACTION_PROMPT
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
        with urllib.request.urlopen(request, timeout=120) as response:
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
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)


def main() -> int:
    args = parse_args()
    size = validate_pdf(args.pdf)

    if args.dry_run:
        summary = {
            "pdf": str(args.pdf),
            "bytes": size,
            "model": args.model,
            "task_note": args.task_note,
            "fixed_prompt": True,
            "api_url": API_URL,
            "will_call_api": False,
        }
        print(json.dumps(summary, indent=2))
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
        raise SystemExit("No text output found in OpenAI response.")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
