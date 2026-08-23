#!/usr/bin/env python3
"""Update a computational strategy plan from a completed-strategy manuscript."""

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

UPDATE_PROMPT = """You are updating a computational chemistry strategy plan after one strategy has been completed and written up as a manuscript or manuscript-like result artifact.

You will receive:
1. The original generated strategy plan from generate-strategies.
2. A manuscript or result artifact for the completed strategy.
3. Optional supporting result artifacts.

Your job is to decide what the next strategy cycle should do.

Allowed update decisions:
* maintain_sequence: keep the original next strategy because the manuscript supports the original logic.
* revise_next_strategy: keep the same next strategy ID but change computational details, descriptors, models, or decision criteria.
* reprioritize_existing_strategy: move an existing lower-priority strategy earlier because the manuscript changes expected value.
* add_new_direction: introduce a new computational strategy because the manuscript reveals a mechanism, gap, surface state, descriptor, uncertainty, or failure mode missing from the original plan.
* repair_completed_strategy: repeat or repair the completed strategy computationally because the manuscript is inconclusive, contradictory, or missing essential computations.
* stop_or_finalize: state that remaining strategy work is not justified by the manuscript, if the completed strategy already resolves the target task sufficiently.

Scope:
* Generate only computational chemistry strategy updates.
* Allowed strategy types include DFT slab and adsorbate modeling, HEA site ensemble sampling, adsorption-energy and free-energy diagrams, transition-state or NEB calculations, constant-potential corrections, solvation/electrolyte corrections, AIMD checks, Pourbaix or stability calculations, segregation/reconstruction calculations, microkinetic modeling, descriptor screening, and ML/surrogate-assisted computational screening.
* Do not generate experimental strategies. Do not propose synthesis, catalyst preparation, microscopy, spectroscopy, electrochemical testing, isotope labeling, product quantification, Faradaic-efficiency measurement, H-cell/zero-gap experiments, or other wet-lab workflows.
* Manuscript experimental statements, if present, may only be used as already-reported benchmark facts or context to explain computationally.

Critical requirements:
* Output exactly one Python assignment named updated_strategy_plan.
* Do not use Markdown fences or prose outside the assignment.
* Use valid Python syntax with double-quoted string keys and string values.
* Use None for unavailable scalar values.
* Use empty lists when no supported entries exist.
* Do not invent manuscript claims, strategy outcomes, references, DFT settings, computed values, mechanisms, or missing results.
* Every decision must include explicit references showing where it came from.
* References must point to the original strategy artifact, manuscript artifact, or supporting artifacts.
* Preserve inherited references from the original strategy plan whenever using an original axiom, method, mechanism, descriptor, or benchmark.
* Treat the completed strategy as completed; do not rewrite its outcome unless the manuscript itself supports the assessment.
* Separate manuscript-supported findings from interpretation.
* If the manuscript contradicts the original plan, say what is contradicted and revise priorities accordingly.
* If the manuscript is too weak to justify a direction change, maintain or repair rather than inventing a new direction.
* The "experiment" object in every updated strategy must contain computational experiments only.
* Every updated strategy must include decision_target and author_claim_support_if_successful. Preserve them for the same lineage unless evidence narrows the boundary; define a bounded evidence-backed contract for a new direction.
* Keep the original strategy_id for repair_completed_strategy and other bounded revisions of the same central hypothesis. Execution attempts use separate run identifiers outside this strategy artifact.

Reference schema:
{
    "artifact": "...",
    "artifact_type": "original_strategies | manuscript | supporting_artifact",
    "strategy_id": "...",
    "manuscript_section": "...",
    "inherited_source": {
        "authors": "...",
        "year": ...,
        "journal": "...",
        "title": "...",
        "claim_used": "..."
    },
    "supporting_statement": "...",
    "decision_role": "completed_result | limitation | original_plan | sequence_decision | revision_reason | new_direction | computational_test | risk | prioritization"
}

Use this exact top-level schema:
updated_strategy_plan = {
    "target_task": {
        "statement": "...",
        "material_domain": "...",
        "benchmark_constraints": [
            {
                "constraint": "...",
                "references": []
            }
        ]
    },
    "revision_context": {
        "completed_strategy_id": "...",
        "original_strategies_artifact": "...",
        "manuscript_artifact": "...",
        "supporting_artifacts": ["..."],
        "manuscript_result_summary": [
            {
                "finding": "...",
                "status": "supports_original_plan | partially_supports_original_plan | contradicts_original_plan | inconclusive | reveals_new_direction",
                "references": []
            }
        ]
    },
    "completed_strategy_assessment": {
        "completed_strategy_id": "...",
        "assessment": "successful | partially_successful | failed | inconclusive | insufficiently_reported",
        "what_was_established": [
            {
                "statement": "...",
                "references": []
            }
        ],
        "what_remains_unresolved": [
            {
                "statement": "...",
                "references": []
            }
        ],
        "implications_for_original_plan": [
            {
                "statement": "...",
                "references": []
            }
        ]
    },
    "strategy_update_decision": {
        "decision": "maintain_sequence | revise_next_strategy | reprioritize_existing_strategy | add_new_direction | repair_completed_strategy | stop_or_finalize",
        "next_strategy_id": "...",
        "rationale": [
            {
                "statement": "...",
                "references": []
            }
        ],
        "changes_to_original_plan": [
            {
                "change": "...",
                "affected_strategy_ids": ["..."],
                "references": []
            }
        ]
    },
    "updated_strategies": [
        {
            "strategy_id": "S2",
            "title": "...",
            "decision_target": "...",
            "origin": "unchanged_from_original | revised_from_original | reprioritized_from_original | new_direction | repair_completed_strategy",
            "supersedes": "...",
            "revision_reason": "...",
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
            "author_claim_support_if_successful": {
                "expected_strength": "...",
                "maximum_supported_conclusion": "...",
                "out_of_scope": ["..."]
            },
            "decision_trace": [
                {
                    "decision": "...",
                    "why_it_matters_for_next_cycle": "...",
                    "references": []
                }
            ]
        }
    ],
    "updated_prioritization": {
        "recommended_order": ["..."],
        "rationale": [
            {
                "statement": "...",
                "references": []
            }
        ],
        "comparison_axes": ["manuscript support", "information gain", "computational feasibility", "risk", "impact on target task"]
    },
    "retired_or_deprioritized_strategies": [
        {
            "strategy_id": "...",
            "reason": "...",
            "references": []
        }
    ],
    "new_unsupported_gaps": [
        {
            "gap": "...",
            "why_it_matters": "...",
            "needed_computational_evidence": "..."
        }
    ]
}

If no strategy update is justified, use decision "maintain_sequence" or "stop_or_finalize" and explain why with references.
If a new direction is justified, include it only when the manuscript or supporting artifacts explicitly support the need for it."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Update a computational chemistry strategy plan using an original "
            "strategy artifact and a completed-strategy manuscript."
        )
    )
    parser.add_argument(
        "--original-strategies",
        required=True,
        type=Path,
        help="Original generated_strategies artifact from generate-strategies.",
    )
    parser.add_argument(
        "--manuscript",
        required=True,
        type=Path,
        help="Manuscript or manuscript-like result artifact for the completed strategy.",
    )
    parser.add_argument(
        "--completed-strategy-id",
        default="S1",
        help="Completed strategy ID represented by the manuscript. Defaults to S1.",
    )
    parser.add_argument(
        "--supporting-artifact",
        action="append",
        type=Path,
        default=[],
        help="Additional result artifact. May be repeated.",
    )
    parser.add_argument(
        "--target-task",
        default="",
        help="Optional target task if not clear from the original strategy plan.",
    )
    parser.add_argument(
        "--material-domain",
        default="",
        help="Optional material domain if not clear from the original strategy plan.",
    )
    parser.add_argument(
        "--num-next-strategies",
        type=int,
        default=5,
        help="Requested number of updated next strategies. Defaults to 5.",
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
        help="Write updated strategy text to this path.",
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
    blocks = [
        artifact_block("original_strategies", args.original_strategies),
        artifact_block("manuscript", args.manuscript),
    ]
    for path in args.supporting_artifact:
        blocks.append(artifact_block("supporting_artifact", path))

    context = {
        "target_task": args.target_task or None,
        "material_domain": args.material_domain or None,
        "completed_strategy_id": args.completed_strategy_id,
        "requested_num_next_strategies": args.num_next_strategies,
        "task_note": args.task_note or None,
    }

    return (
        f"{UPDATE_PROMPT}\n\n"
        f"Revision context:\n{json.dumps(context, indent=2)}\n\n"
        f"Artifacts:\n\n" + "\n\n".join(blocks)
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

    if args.num_next_strategies < 1:
        raise SystemExit("--num-next-strategies must be at least 1.")

    artifacts = [args.original_strategies, args.manuscript] + args.supporting_artifact
    sizes = {str(path): validate_artifact(path) for path in artifacts}

    if args.dry_run:
        print(
            json.dumps(
                {
                    "target_task": args.target_task,
                    "material_domain": args.material_domain,
                    "completed_strategy_id": args.completed_strategy_id,
                    "num_next_strategies": args.num_next_strategies,
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
