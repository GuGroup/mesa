#!/usr/bin/env python3
"""Generate referenced computational chemistry strategies from extraction artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.5"
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024

STRATEGY_PROMPT = """You are generating computational chemistry strategies for a target materials or chemistry task.

You will receive saved extraction artifacts from earlier workflow steps:
1. Experimental extraction from extract-data-from-experiment.
2. Paper decomposition from decompose-chemistry-paper-pdf.
3. General paper insight from extract-general-insight-pdf.

Your job is to generate multiple actionable computational proof strategies for the target task by synthesizing these artifacts.

Scope:
* Generate only computational chemistry strategies.
* Allowed strategy types include DFT slab and adsorbate modeling, adsorption-energy and free-energy diagram.
* Free-energy diagram is always recommended, but pursue the best if there are other strategies.
* But transition / NEB study is not supported in this session. Please evade it.
* All intermediate states, initial, and final gas state should be explicitly implemented for free-energy diagram strategy.
* Do not generate experimental strategies. Do not propose synthesis, catalyst preparation, microscopy, spectroscopy, electrochemical cell testing, isotope labeling, product quantification, Faradaic-efficiency measurement, H-cell/zero-gap experiments, or other wet-lab workflows.
* Experimental extraction may be used only as benchmark constraints, observed material identity, observed performance targets, or measured facts that the computational strategy should explain. It must not become an experimental action plan.

Critical requirements:
* Output exactly one Python assignment named generated_strategies.
* Do not use Markdown fences or prose outside the assignment.
* Use valid Python syntax with double-quoted string keys and string values.
* Use None for unavailable scalar values.
* Use empty lists when no supported entries exist.
* Do not invent references, paper metadata, mechanisms, settings, experimental values, or source claims.
* Every decision must include explicit references showing where it came from.
* References must be inherited from the extraction artifacts. If an extraction artifact contains source metadata from a cited paper, preserve that metadata under inherited_source.
* If source metadata is unavailable, set inherited_source to None and still identify the extraction artifact plus supporting statement.
* Paper decomposition artifacts are preferred for detailed mechanism, method, model, and computational-setting decisions.
* General insight artifacts are preferred for broad design principles, descriptors, field bottlenecks, risk framing, and computational opportunities.
* Results in this output are proposed expected computational results, computational checks, or benchmark comparisons, not established current-paper findings. Mark that status explicitly.
* Do not collapse all evidence into one generic bibliography. Attach references directly to the decision or claim they support.
* The "experiment" object in every strategy must contain computational experiments only.

echanistic ambition requirements:

* Do not generate safe generic DFT workflows. Generate paper-worthy mechanistic proof strategies.
* Every strategy must center on one explicit central mechanistic claim that could become the main claim of a computational chemistry paper.
* A strategy is invalid if its strongest conclusion is only that one site, surface, intermediate, pathway, composition, or structure is more stable or energetically favorable.

* Stability, adsorption energy, site preference, barrier height, selectivity, or descriptor trends are only observations. Each must be connected to a causal physical or chemical mechanism.

* Supported extrapolation is allowed, but unsupported invention is not. When combining multiple artifacts to form a new mechanistic hypothesis, explicitly label the reference role as "synthesis_basis" and explain the inference chain.

Reference schema:
{
    "extraction_artifact": "...",
    "extraction_type": "experimental_extraction | paper_decomposition | general_insight | paper_extraction",
    "inherited_source": {
        "authors": "...",
        "year": ...,
        "journal": "...",
        "title": "...",
        "claim_used": "..."
    },
    "supporting_statement": "...",
    "decision_role": "benchmark_constraint | axiom | mechanism | method | descriptor | computational_test | risk | prioritization"
}

Use this exact top-level schema:
generated_strategies = {
    "target_task": {
        "statement": "...",
        "material_domain": "...",
        "success_criteria": [
            {
                "criterion": "...",
                "references": [
                    {
                        "extraction_artifact": "...",
                        "extraction_type": "...",
                        "inherited_source": None,
                        "supporting_statement": "...",
                        "decision_role": "benchmark_constraint"
                    }
                ]
            }
        ],
        "benchmark_constraints": [
            {
                "constraint": "...",
                "references": [
                    {
                        "extraction_artifact": "...",
                        "extraction_type": "...",
                        "inherited_source": None,
                        "supporting_statement": "...",
                        "decision_role": "benchmark_constraint"
                    }
                ]
            }
        ]
    },
    "input_artifacts": {
        "experimental_extractions": ["..."],
        "paper_decompositions": ["..."],
        "general_insights": ["..."],
        "other_paper_extractions": ["..."]
    },
    "strategies": [
        {
            "strategy_id": "S1",
            "title": "...",
            "problem": {
                "question": "...",
                "unexplained_phenomenon": "...",
                "context": "...",
                "references": []
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
                        },
                        "references": []
                    }
                ]
            },
            "hypothesis": {
                "statement": "...",
                "derived_from_axioms": ["..."],
                "proposed_mechanism_or_prediction": "...",
                "references": []
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
                    "procedures": ["..."],
                    "references": []
                }
            },
            "results": {
                "expected_computational_results": [
                    {
                        "statement": "...",
                        "status": "proposed expectation, not established",
                        "references": []
                    }
                ],
                "computational_benchmark_comparisons": [
                    {
                        "statement": "...",
                        "status": "benchmark comparison to compute, not established",
                        "references": []
                    }
                ],
                "computational_tests_to_run": {
                    "mechanism_and_descriptor_tests": [
                        {
                            "statement": "...",
                            "status": "calculation to run",
                            "references": []
                        }
                    ],
                    "selectivity_and_competing_pathway_tests": [
                        {
                            "statement": "...",
                            "status": "calculation to run",
                            "references": []
                        }
                    ],
                    "stability_and_surface_state_tests": [
                        {
                            "statement": "...",
                            "status": "calculation to run",
                            "references": []
                        }
                    ]
                }
            },
            "conclusion": {
                "causal_mechanism": "...",
                "design_principle": "...",
                "scope_or_limitations": "...",
                "references": []
            },
            "decision_trace": [
                {
                    "decision": "...",
                    "why_it_matters_for_target_task": "...",
                    "references": []
                }
            ]
        }
    ],
    "prioritization": {
        "recommended_order": ["S1"],
        "rationale": [
            {
                "statement": "...",
                "references": []
            }
        ],
        "comparison_axes": ["feasibility", "expected impact", "evidence strength", "risk"]
    },
    "unsupported_gaps": [
        {
            "gap": "...",
            "why_it_matters": "...",
            "needed_computational_evidence": "..."
        }
    ]
}

If a strategy cannot be supported by the extraction artifacts, do not include it as a strategy. Put the missing idea in unsupported_gaps instead.
If an idea would require experimental work, do not include it as a strategy. Only mention it as a benchmark constraint if it is already present in the extraction artifacts."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate referenced computational chemistry strategies from saved "
            "extraction outputs."
        )
    )
    parser.add_argument(
        "--target-task",
        required=True,
        help="Target task the strategies should solve.",
    )
    parser.add_argument(
        "--material-domain",
        default="",
        help="Optional material or chemistry domain.",
    )
    parser.add_argument(
        "--experimental-extraction",
        action="append",
        type=Path,
        default=[],
        help=(
            "Saved output from extract-data-from-experiment. May be repeated. "
            "Used only as benchmark constraints, not as experimental strategy input."
        ),
    )
    parser.add_argument(
        "--paper-decomposition",
        action="append",
        type=Path,
        default=[],
        help="Saved output from decompose-chemistry-paper-pdf. May be repeated.",
    )
    parser.add_argument(
        "--general-insight",
        action="append",
        type=Path,
        default=[],
        help="Saved output from extract-general-insight-pdf. May be repeated.",
    )
    parser.add_argument(
        "--paper-extraction",
        action="append",
        type=Path,
        default=[],
        help="Generic paper extraction artifact when subtype is unknown. May be repeated.",
    )
    parser.add_argument(
        "--num-strategies",
        type=int,
        default=5,
        help="Requested number of strategies. Defaults to 5.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        help=f"Model to use. Defaults to OPENAI_MODEL or {DEFAULT_MODEL}.",
    )
    parser.add_argument(
        "--task-note",
        default="",
        help="Optional non-conflicting computational downstream context.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write generated strategy text to this path.",
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


def validate_artifact(path: Path) -> int:
    if not path.exists():
        raise SystemExit(f"Artifact does not exist: {path}")
    if not path.is_file():
        raise SystemExit(f"Artifact path is not a file: {path}")

    size = path.stat().st_size
    if size > MAX_ARTIFACT_BYTES:
        raise SystemExit(
            f"Artifact is {size} bytes, which exceeds the 2 MB text-artifact limit: {path}"
        )
    return size


def read_artifact(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def artifact_block(kind: str, path: Path) -> str:
    content = read_artifact(path)
    return (
        f"BEGIN_ARTIFACT\n"
        f"artifact_path: {path}\n"
        f"artifact_type: {kind}\n"
        f"content:\n{content}\n"
        f"END_ARTIFACT"
    )


def build_prompt(args: argparse.Namespace) -> str:
    blocks: list[str] = []
    for path in args.experimental_extraction:
        blocks.append(artifact_block("experimental_extraction", path))
    for path in args.paper_decomposition:
        blocks.append(artifact_block("paper_decomposition", path))
    for path in args.general_insight:
        blocks.append(artifact_block("general_insight", path))
    for path in args.paper_extraction:
        blocks.append(artifact_block("paper_extraction", path))

    context = {
        "target_task": args.target_task,
        "material_domain": args.material_domain or None,
        "requested_num_strategies": args.num_strategies,
        "task_note": args.task_note or None,
    }

    return (
        f"{STRATEGY_PROMPT}\n\n"
        f"Generation context:\n{json.dumps(context, indent=2)}\n\n"
        f"Extraction artifacts:\n\n" + "\n\n".join(blocks)
    )


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "model": args.model,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": build_prompt(args)}],
            }
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
        with urllib.request.urlopen(request, timeout=600) as response:
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

    if args.num_strategies < 1:
        raise SystemExit("--num-strategies must be at least 1.")

    all_paper_artifacts = (
        args.paper_decomposition + args.general_insight + args.paper_extraction
    )
    if not all_paper_artifacts:
        raise SystemExit(
            "At least one paper extraction artifact is required "
            "(--paper-decomposition, --general-insight, or --paper-extraction)."
        )

    artifacts = (
        args.experimental_extraction
        + args.paper_decomposition
        + args.general_insight
        + args.paper_extraction
    )
    sizes = {str(path): validate_artifact(path) for path in artifacts}

    if args.dry_run:
        print(
            json.dumps(
                {
                    "target_task": args.target_task,
                    "material_domain": args.material_domain,
                    "num_strategies": args.num_strategies,
                    "model": args.model,
                    "artifacts": sizes,
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

    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
