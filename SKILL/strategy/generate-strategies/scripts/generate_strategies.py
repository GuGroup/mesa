#!/usr/bin/env python3
"""Generate referenced computational chemistry strategies from extraction artifacts."""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.6-sol"
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
CLAIM_HEADING = "author_reported_claim"
NOT_STATED = "not explicitly stated"

STRATEGY_PROMPT = """You are generating computational chemistry strategies for a target materials or chemistry task.

You will receive saved extraction artifacts from earlier workflow steps:
1. Experimental extraction from extract-data-from-experiment.
2. Paper decomposition from decompose-chemistry-paper-pdf.
3. General paper insight from extract-general-insight-pdf.

Your job is to generate multiple actionable computational proof strategies for the authoritative target task by synthesizing these artifacts.

Scope:
* Generate only computational chemistry strategies.
* Allowed strategy types include DFT slab and adsorbate modeling, adsorption-energy and free-energy diagram.
* Free-energy diagram is always recommended, but pursue the best if there are other strategies.
* But transition / NEB study is not supported in this session. Please evade it.
* All intermediate states, initial, and final gas state should be explicitly implemented for free-energy diagram strategy.
* Do not generate experimental strategies. Do not propose synthesis, catalyst preparation, microscopy, spectroscopy, electrochemical cell testing, isotope labeling, product quantification, Faradaic-efficiency measurement, H-cell/zero-gap experiments, or other wet-lab workflows.
* The extracted author-reported claim defines the target when present. Use all other experimental-extraction content only as benchmark constraints, observed material identity, observed performance targets, or measured facts that the computational strategy should explain. It must not become an experimental action plan.

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
* Copy Generation context target_task exactly into target_task.statement.
* When Generation context contains author_reported_claim, copy its statement exactly into target_task.statement and copy the complete author_reported_claim object exactly into target_task.author_reported_claim.
* When Generation context author_reported_claim is null, set target_task.author_reported_claim to None.
* Treat author_reported_claim as the definition of what must be supported. Do not add a material feature, causal variable, mechanism, structure, or performance claim to target_task.statement.
* Descriptive coexistence, correlation, characterization, or measured association must not be promoted into causation unless the author-reported claim explicitly makes that causal statement.
* Strategies may test alternative explanations, but label them as hypotheses and do not rewrite the authoritative target claim around them.

Mechanistic discipline requirements:

* Generate strategies at the strongest mechanistic depth supported by the authoritative claim and extraction artifacts; do not increase ambition by changing the claim.
* Use matched controls that isolate each variable named in the claim.
* Keep observations distinct from causal explanations. Connect an observation to a mechanism only when the evidence or a clearly labeled hypothesis supports that connection.
* Supported extrapolation is allowed inside strategy hypotheses, but unsupported invention is not. When combining multiple artifacts, use the allowed role that matches each source's contribution and explain the inference chain.

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
        "author_reported_claim": {
            "statement": "...",
            "source_locations": {
                "abstract": "...",
                "conclusion": "..."
            },
            "extraction_artifact": "..."
        },
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
        default="",
        help=(
            "Fallback target task when no experimental extraction contains an "
            "author_reported_claim. When a claim exists, this value may only "
            "select that exact claim."
        ),
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


def normalize_heading(line: str) -> str:
    heading = line.strip().lstrip("#").strip()
    if heading.startswith("- "):
        heading = heading[2:].strip()
    return heading.rstrip(":").strip()


def artifact_block(kind: str, path: Path) -> str:
    content = read_artifact(path)
    return (
        f"BEGIN_ARTIFACT\n"
        f"artifact_path: {path}\n"
        f"artifact_type: {kind}\n"
        f"content:\n{content}\n"
        f"END_ARTIFACT"
    )


def parse_author_reported_claim(path: Path) -> dict[str, Any] | None:
    lines = read_artifact(path).splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if normalize_heading(line) == CLAIM_HEADING
    ]
    if not starts:
        return None
    if len(starts) != 1:
        raise SystemExit(f"Expected exactly one author_reported_claim section: {path}")

    values: dict[str, str] = {}
    saw_source_locations = False
    for line in lines[starts[0] + 1:]:
        stripped = line.strip()
        if stripped == "- source_locations:":
            if saw_source_locations:
                raise SystemExit(
                    f"author_reported_claim contains duplicate source_locations: {path}"
                )
            saw_source_locations = True
            continue
        for label in ("statement", "abstract", "conclusion"):
            prefix = f"- {label}:"
            if not stripped.startswith(prefix):
                continue
            if label in values:
                raise SystemExit(
                    f"author_reported_claim contains duplicate {label}: {path}"
                )
            value = stripped[len(prefix):].strip()
            if not value:
                raise SystemExit(
                    f"author_reported_claim has an empty {label} value: {path}"
                )
            values[label] = value
            break
        if saw_source_locations and all(
            label in values for label in ("statement", "abstract", "conclusion")
        ):
            break

    if not saw_source_locations:
        raise SystemExit(f"author_reported_claim is missing source_locations: {path}")
    missing = [
        label
        for label in ("statement", "abstract", "conclusion")
        if label not in values
    ]
    if missing:
        raise SystemExit(
            f"author_reported_claim is missing: {', '.join(missing)}: {path}"
        )

    statement = values["statement"]
    abstract = values["abstract"]
    conclusion = values["conclusion"]
    if statement.strip("`").casefold() == NOT_STATED:
        return None
    return {
        "statement": statement,
        "source_locations": {"abstract": abstract, "conclusion": conclusion},
        "extraction_artifact": str(path),
    }


def resolve_target(args: argparse.Namespace) -> tuple[str, dict[str, Any] | None]:
    claims = [
        claim
        for path in args.experimental_extraction
        if (claim := parse_author_reported_claim(path)) is not None
    ]
    requested = " ".join(args.target_task.split())
    if claims:
        matches = [
            claim
            for claim in claims
            if " ".join(claim["statement"].split()) == requested
        ]
        if requested and not matches:
            raise SystemExit("--target-task conflicts with the extracted author-reported claim")
        if len(claims) > 1 and len(matches) != 1:
            raise SystemExit("Multiple author-reported claims found; use --target-task to select one exact statement")
        claim = matches[0] if matches else claims[0]
        return claim["statement"], claim
    if not requested:
        raise SystemExit("--target-task is required when no author-reported claim is available")
    return args.target_task, None


def build_prompt(
    args: argparse.Namespace,
    target_statement: str,
    author_claim: dict[str, Any] | None,
) -> str:
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
        "target_task": target_statement,
        "author_reported_claim": author_claim,
        "material_domain": args.material_domain or None,
        "requested_num_strategies": args.num_strategies,
        "task_note": args.task_note or None,
    }

    return (
        f"{STRATEGY_PROMPT}\n\n"
        f"Generation context:\n{json.dumps(context, indent=2)}\n\n"
        f"Extraction artifacts:\n\n" + "\n\n".join(blocks)
    )


def build_payload(
    args: argparse.Namespace,
    target_statement: str,
    author_claim: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "model": args.model,
        "input": [
            {
                "role": "user",
                "content": [{
                    "type": "input_text",
                    "text": build_prompt(args, target_statement, author_claim),
                }],
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


def validate_generated_output(
    text: str,
    target_statement: str,
    author_claim: dict[str, Any] | None,
) -> None:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise SystemExit(f"Generated strategy output is not valid Python: {exc}") from exc
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign):
        raise SystemExit("Generated output must contain exactly one assignment")
    assignment = tree.body[0]
    if len(assignment.targets) != 1 or not isinstance(assignment.targets[0], ast.Name):
        raise SystemExit("Generated output must assign one name")
    if assignment.targets[0].id != "generated_strategies":
        raise SystemExit("Generated output must assign generated_strategies")
    try:
        payload = ast.literal_eval(assignment.value)
    except (ValueError, TypeError) as exc:
        raise SystemExit("generated_strategies must be a literal Python object") from exc
    target = payload.get("target_task") if isinstance(payload, dict) else None
    if not isinstance(target, dict) or target.get("statement") != target_statement:
        raise SystemExit("Generated target_task.statement changed the authoritative target claim")
    if author_claim is not None and target.get("author_reported_claim") != author_claim:
        raise SystemExit("Generated target_task.author_reported_claim does not exactly preserve the extraction")
    if author_claim is None and target.get("author_reported_claim") is not None:
        raise SystemExit("Generated target_task.author_reported_claim must be None without an extracted claim")

    allowed_reference_roles = {
        "benchmark_constraint",
        "axiom",
        "mechanism",
        "method",
        "descriptor",
        "computational_test",
        "risk",
        "prioritization",
    }
    required_reference_fields = {
        "extraction_artifact",
        "extraction_type",
        "inherited_source",
        "supporting_statement",
        "decision_role",
    }

    def validate_references(value: Any, path: str = "generated_strategies") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                if key == "references":
                    if not isinstance(child, list) or not child:
                        raise SystemExit(f"{child_path} must be a non-empty list")
                    for index, reference in enumerate(child):
                        reference_path = f"{child_path}[{index}]"
                        if not isinstance(reference, dict):
                            raise SystemExit(f"{reference_path} must be an object")
                        missing = required_reference_fields.difference(reference)
                        if missing:
                            fields = ", ".join(sorted(missing))
                            raise SystemExit(f"{reference_path} is missing fields: {fields}")
                        role = reference.get("decision_role")
                        if role not in allowed_reference_roles:
                            allowed = ", ".join(sorted(allowed_reference_roles))
                            raise SystemExit(
                                f"{reference_path}.decision_role must be one of: {allowed}"
                            )
                validate_references(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                validate_references(child, f"{path}[{index}]")

    validate_references(payload)


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
    target_statement, author_claim = resolve_target(args)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "target_task": target_statement,
                    "author_reported_claim": author_claim,
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

    payload = build_payload(args, target_statement, author_claim)
    response = call_openai(payload, api_key)

    if args.save_response:
        args.save_response.write_text(json.dumps(response, indent=2), encoding="utf-8")

    text = output_text(response)
    if not text:
        raise SystemExit("No text output found in API response.")
    validate_generated_output(text, target_statement, author_claim)

    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
