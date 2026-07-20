#!/usr/bin/env python3
"""Write public Methods sections from a minimal Methods writer digest."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.numeric_precision import format_numeric_precision, overprecise_decimal_literals


API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.5"
SCHEMA_VERSION = 3
REQUIRED_SECTIONS = [
    "model_construction",
    "geometry_optimization",
    "vibrational_free_energy_corrections",
    "electrochemical_free_energy_formalism",
]
SECTION_TITLES = {
    "model_construction": "Model construction",
    "geometry_optimization": "Geometry optimization",
    "vibrational_free_energy_corrections": "Vibrational and free-energy corrections",
    "electrochemical_free_energy_formalism": "Electrochemical free-energy formalism",
}

METHODS_PROMPT = """You are writing the Methods section of a computational chemistry manuscript for heterogeneous catalysis.

You will receive a compact JSON digest. Write public, academic Methods prose from only that digest.

Strict rules:
1. Write exactly four sections, one for each input section_id:
   - model_construction
   - geometry_optimization
   - vibrational_free_energy_corrections
   - electrochemical_free_energy_formalism
2. Do not add descriptor analysis, electronic-structure analysis, results, discussion, or standalone limitations sections.
3. Do not mention internal workflow language, including: strategy, procedure, workflow, source, digest, JSON, artifact, manifest, skill, prompt, mapper, realizer, writer, P001-style ids, C001-style ids, file paths, project paths, or code filenames.
4. Translate internal tool names into public method language. Do not write names such as calculate-uma-vibrational-frequencies, alkaline-her-free-energy-bookkeeper, or methods-evidence-collector.
5. Do not invent missing details such as exact slab-builder arguments, slab dimensions, or convergence settings when not supplied.
6. Keep text factual and Methods-like. Avoid claims about catalytic performance, superiority, experimental validation, or mechanistic conclusions.
7. Mention descriptor/electronic-structure methods only if they are part of the four provided sections. If not provided, omit them.
8. Use plain text paragraphs. No bullet lists inside section text.
9. Do not write planning language such as "planned", "intended", "to be tested", or "if supported" in section text. Put such uncertainty in missing_details instead.
10. Use ordered content_blocks inside each section. Each block is either a paragraph block or an equation block.
11. Place each equation block exactly where it belongs in the Methods narrative. Do not collect equations at the end of a section.
12. Write manuscript-ready equations as LaTeX strings without Markdown math delimiters. Keep explanation fields academic and concise.
13. Treat chemical equations, electrochemical identities, and reaction-state sequences supplied in the digest as equation blocks, not as inline prose.
14. Do not repeat the same equation in both a paragraph and an equation block. Paragraphs should introduce or interpret equations, while equation blocks hold the mathematical or chemical expression.
15. In public text and equations, write non-integer numbers with at most two decimal places; keep integers as integers.

Return JSON only.

Schema:
{
  "sections": [
    {
      "section_id": "model_construction",
      "title": "Model construction",
      "content_blocks": [
        {
          "type": "paragraph",
          "text": "Academic Methods prose."
        },
        {
          "type": "equation",
          "label": "Concise equation label",
          "latex": "G = E + E_{\\mathrm{ZPE}} - TS",
          "explanation": "Brief academic explanation of the equation terms."
        }
      ]
    }
  ],
  "missing_details": [
    "Concise missing factual detail that would improve reproducibility."
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
    r"\bP\d{3}\b",
    r"\bC\d{3}\b",
    r"\bTASK_[A-Za-z0-9_]+\b",
    r"\balkaline-her-free-energy-bookkeeper\b",
    r"\bmethods-evidence-collector\b",
    r"\bmethods_writer_digest\b",
    r"\bmethods_minimal_evidence\b",
    r"\bdescriptor analysis\b",
    r"\belectronic-structure analysis\b",
    r"\belectronic structure analysis\b",
    r"\bproject/",
    r"/home/",
    r"\b[A-Za-z0-9_.-]+\.json\b",
    r"\b[A-Za-z0-9_.-]+\.py\b",
]

INLINE_EQUATION_PATTERNS = [
    r"\b(?:Delta|Δ|\\Delta)\s*G\s*=",
    r"\\rightleftharpoons|⇌|<->",
    r"\bH2O\(l\)\s*\+\s*(?:e−|e-|\be\b)",
    r"\*\s*\+\s*H2O\(l\)\s*\+\s*(?:e−|e-|\be\b)",
    r"\bH2\*\s*\+\s*OH",
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
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
    if digest.name == "methods_writer_digest.json" and digest.parent.name == "evidence":
        return digest.parent.parent / "text"
    return digest.parent / "text"


def build_prompt(digest: dict[str, Any]) -> str:
    return f"{METHODS_PROMPT}\n\nMethods writer digest:\n{json.dumps(digest, indent=2)}\n"


def build_payload(model: str, prompt: str) -> dict[str, Any]:
    return {
        "model": model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
    }


def forbidden_hits(text: str) -> list[str]:
    hits = []
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            hits.append(pattern)
    return hits


def normalize_equation_block(item: dict[str, Any]) -> dict[str, str]:
    latex = format_numeric_precision(str(item.get("latex") or "").strip())
    if not latex:
        raise ValueError("Each equation block must contain a non-empty latex field.")
    label = format_numeric_precision(str(item.get("label") or "Equation").strip())
    explanation = format_numeric_precision(str(item.get("explanation") or "").strip())
    return {"type": "equation", "label": label, "latex": latex, "explanation": explanation}


def normalize_equations(raw: Any) -> list[dict[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("Section equations must be a list when provided.")
    equations: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each equation must be a JSON object.")
        block = normalize_equation_block(item)
        equations.append({"label": block["label"], "latex": block["latex"], "explanation": block["explanation"]})
    return equations


def split_paragraphs(text: str) -> list[str]:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = [str(part).strip() for part in re.split(r"\n\s*\n+", normalized)]
    return [part for part in parts if part]


def normalize_content_blocks(item: dict[str, Any], section_id: str) -> list[dict[str, str]]:
    raw = item.get("content_blocks")
    blocks: list[dict[str, str]] = []
    if raw is not None:
        if not isinstance(raw, list):
            raise ValueError(f"Section {section_id} content_blocks must be a list.")
        for block in raw:
            if not isinstance(block, dict):
                raise ValueError(f"Section {section_id} contains a non-object content block.")
            block_type = str(block.get("type") or "").strip().lower()
            if block_type == "paragraph":
                text = format_numeric_precision(str(block.get("text") or "").strip())
                if not text:
                    raise ValueError(f"Section {section_id} contains an empty paragraph block.")
                blocks.append({"type": "paragraph", "text": text})
            elif block_type == "equation":
                blocks.append(normalize_equation_block(block))
            else:
                raise ValueError(f"Section {section_id} contains unsupported block type: {block_type}")
    else:
        for paragraph in split_paragraphs(str(item.get("text") or "")):
            blocks.append({"type": "paragraph", "text": format_numeric_precision(paragraph)})
        for equation in normalize_equations(item.get("equations")):
            blocks.append({"type": "equation", **equation})
    if not any(block.get("type") == "paragraph" for block in blocks):
        raise ValueError(f"Section {section_id} must contain at least one paragraph block.")
    return blocks


def section_text_from_blocks(blocks: list[dict[str, str]]) -> str:
    paragraphs = [block["text"] for block in blocks if block.get("type") == "paragraph" and block.get("text")]
    return "\n\n".join(paragraphs)


def normalize_sections(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("sections")
    if not isinstance(raw, list):
        raise ValueError("Output JSON must contain a sections list.")
    by_id: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        section_id = str(item.get("section_id", ""))
        if section_id not in REQUIRED_SECTIONS:
            raise ValueError(f"Unexpected section_id: {section_id}")
        title = format_numeric_precision(str(item.get("title") or SECTION_TITLES[section_id]).strip())
        content_blocks = normalize_content_blocks(item, section_id)
        text = section_text_from_blocks(content_blocks)
        if not text:
            raise ValueError(f"Section {section_id} has empty text.")
        by_id[section_id] = {
            "section_id": section_id,
            "title": title,
            "text": text,
            "content_blocks": content_blocks,
        }
    missing = [section_id for section_id in REQUIRED_SECTIONS if section_id not in by_id]
    if missing:
        raise ValueError(f"Missing required sections: {', '.join(missing)}")
    return [by_id[section_id] for section_id in REQUIRED_SECTIONS]


def deterministic_sections(digest: dict[str, Any]) -> list[dict[str, Any]]:
    sections = []
    for item in digest.get("sections", []):
        section_id = item.get("section_id")
        if section_id not in REQUIRED_SECTIONS:
            continue
        title = SECTION_TITLES[section_id]
        strategy_inputs = item.get("strategy_inputs", {})
        project_details = item.get("project_details", {})
        if section_id == "model_construction":
            motifs = ", ".join(project_details.get("motif_labels", []))
            states = ", ".join(project_details.get("states", []))
            gas = project_details.get("gas_model_example", {})
            text = (
                f"Computational models were constructed for the catalyst motifs represented by {motifs}. "
                f"Adsorbate states included {states}. Gas-phase reference models used isolated molecules; "
                f"the representative gas model has formula {gas.get('formula')} in a cell with lengths "
                f"{gas.get('cell_lengths')} and periodic boundary settings {gas.get('pbc')}."
            )
            content_blocks: list[dict[str, str]] = [{"type": "paragraph", "text": text}]
        elif section_id == "geometry_optimization":
            code = strategy_inputs.get("code", "")
            conv = strategy_inputs.get("convergence_criteria", "")
            summary = project_details.get("relaxation_summary", {})
            text = (
                f"Geometry optimizations were carried out using {code}. {conv} "
                f"The relaxation set contained {summary.get('task_count')} tasks, with "
                f"{summary.get('converged_count')} converged records."
            )
            content_blocks = [{"type": "paragraph", "text": text}]
        elif section_id == "vibrational_free_energy_corrections":
            vib = project_details.get("vibration_summary", {})
            policy = project_details.get("surface_thermal_policy", {})
            policy_text = policy.get("model", "a local harmonic treatment was used") if isinstance(policy, dict) else str(policy)
            text = (
                "Free-energy corrections followed the thermochemical correction policy for zero-point and entropic terms where available. "
                f"Vibrational calculations produced {vib.get('frequency_result_count')} frequency results."
            )
            content_blocks = [
                {"type": "paragraph", "text": text},
                {
                    "type": "equation",
                    "label": "Thermochemical free energy",
                    "latex": "G = E + E_{\\mathrm{ZPE}} - TS",
                    "explanation": "The free energy was obtained from the electronic energy with zero-point and entropic corrections where available.",
                },
                {
                    "type": "paragraph",
                    "text": f"For surface structures, {policy_text}.",
                },
            ]
        else:
            policy = project_details.get("reference_policy", {})
            hydrogen = policy.get("hydrogen_reference", {})
            water = policy.get("water_reference", {})
            hydrogen_text = hydrogen.get("H_chemical_potential", "the hydrogen reference convention") if isinstance(hydrogen, dict) else "the hydrogen reference convention"
            water_text = (
                f"a liquid correction of {water.get('liquid_correction_ev')} eV"
                if isinstance(water, dict) and water.get("liquid_correction_ev") is not None
                else "the water reference convention"
            )
            text = (
                f"Electrochemical free energies were evaluated at pH {policy.get('pH')} and "
                f"U = {policy.get('potential_V_RHE')} V_RHE. The hydrogen reference was {hydrogen_text}, "
                f"and the water reference included {water_text}."
            )
            content_blocks = [
                {"type": "paragraph", "text": text},
            ]
            for equation in policy.get("equations", []) if isinstance(policy, dict) else []:
                if not isinstance(equation, dict):
                    continue
                latex = str(equation.get("latex") or equation.get("equation") or "").strip()
                if not latex:
                    continue
                content_blocks.append(
                    {
                        "type": "equation",
                        "label": str(equation.get("label") or "Reference equation"),
                        "latex": latex,
                        "explanation": str(equation.get("explanation") or ""),
                    }
                )
            if not any(block.get("type") == "equation" for block in content_blocks):
                content_blocks.append(
                    {
                        "type": "equation",
                        "label": "Thermodynamic free-energy relation",
                        "latex": "\\Delta G = \\Delta E + \\Delta E_{\\mathrm{ZPE}} - T\\Delta S",
                        "explanation": "Reaction free energies were assembled from electronic energy differences and available thermochemical corrections.",
                    }
                )
        sections.append({"section_id": section_id, "title": title, "content_blocks": content_blocks})
    return normalize_sections({"sections": sections})


def validate_output(sections: list[dict[str, Any]]) -> dict[str, Any]:
    section_reports = []
    ok = True
    for section in sections:
        parts = [section["title"], section["text"]]
        inline_hits: list[dict[str, Any]] = []
        for index, block in enumerate(section.get("content_blocks", [])):
            if block.get("type") == "paragraph":
                paragraph = block.get("text", "")
                parts.append(paragraph)
                paragraph_hits = []
                for pattern in INLINE_EQUATION_PATTERNS:
                    if re.search(pattern, paragraph, flags=re.IGNORECASE):
                        paragraph_hits.append(pattern)
                if paragraph_hits:
                    inline_hits.append({"block_index": index, "patterns": paragraph_hits})
            elif block.get("type") == "equation":
                parts.extend([block.get("label", ""), block.get("latex", ""), block.get("explanation", "")])
        public_text = "\n".join(parts)
        hits = forbidden_hits(public_text)
        overprecise = overprecise_decimal_literals(public_text)
        if hits or inline_hits or overprecise:
            ok = False
        section_reports.append(
            {
                "section_id": section["section_id"],
                "forbidden_patterns": hits,
                "inline_equation_patterns": inline_hits,
                "overprecise_decimal_literals": overprecise,
            }
        )
    return {"ok": ok, "section_reports": section_reports}


def assemble_output(source_digest: Path, digest: dict[str, Any], sections: list[dict[str, Any]], missing_details: list[str], source: str) -> dict[str, Any]:
    validation = validate_output(sections)
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": digest.get("strategy_id", ""),
        "source_digest": str(source_digest),
        "section_source": source,
        "sections": sections,
        "missing_details": missing_details,
        "validation": validation,
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = ["# Methods Sections", ""]
    for section in payload["sections"]:
        lines.extend([f"## {section['title']}", ""])
        for block in section.get("content_blocks", []):
            if block.get("type") == "paragraph":
                lines.extend([block.get("text", ""), ""])
            elif block.get("type") == "equation":
                label = block.get("label", "Equation")
                latex = block.get("latex", "")
                explanation = block.get("explanation", "")
                lines.extend([f"**{label}**", "", f"`${latex}$`", ""])
                if explanation:
                    lines.extend([explanation, ""])
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
    outdir = Path(args.outdir) if args.outdir else default_outdir(digest_path)
    prompt = build_prompt(digest)
    write_text(outdir / "llm_prompt.txt", prompt)

    if args.no_llm:
        sections = deterministic_sections(digest)
        payload = assemble_output(digest_path, digest, sections, ["LLM was not used; deterministic smoke-test prose was generated."], "deterministic")
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
        payload = assemble_output(digest_path, digest, sections, [str(item) for item in missing_details], "llm")
        if not payload["validation"]["ok"]:
            write_json(outdir / "methods_section_text.json", payload)
            write_markdown(outdir / "methods_section_text.md", payload)
            raise SystemExit("LLM output contains forbidden public text. See methods_section_text.json and llm_response.json.")

    write_json(outdir / "methods_section_text.json", payload)
    write_markdown(outdir / "methods_section_text.md", payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--digest", required=True, help="Path to methods_writer_digest.json.")
    parser.add_argument("--outdir", default="", help="Output directory. Defaults to sibling text/ directory.")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL), help=f"OpenAI model. Defaults to OPENAI_MODEL or {DEFAULT_MODEL}.")
    parser.add_argument("--no-llm", action="store_true", help="Write deterministic smoke-test output without calling OpenAI.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run(args)
    outdir = Path(args.outdir) if args.outdir else default_outdir(Path(payload["source_digest"]))
    print(f"Wrote {outdir / 'methods_section_text.json'}")
    print(f"Wrote {outdir / 'methods_section_text.md'}")
    if not payload.get("validation", {}).get("ok"):
        sys.exit(2)


if __name__ == "__main__":
    main()
