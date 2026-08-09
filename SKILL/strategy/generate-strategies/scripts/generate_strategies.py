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


1. Task and Objective

* Generate multiple distinct, self-contained computational strategies that can support authoritative target claim by synthesizing these artifacts.
* Each strategy must use supported computational chemistry methods to produce an interpretable conclusion about a directly or partially testable component of the authoritative claim.
* Generate strategies at the strongest mechanistic depth supported by the authoritative claim, the extraction artifacts, and the available computational capabilities.
* Do NOT increase mechanistic ambition by rewriting, extending, or strengthening the target claim.


2. Input Artifacts and Source Roles

* Use the provided experimental extraction, paper decomposition, general paper insight, Generation context, and optional reaction-pathway prior only for their designated roles.
* Use experimental extraction for author-reported claims, observed material identity, measured facts, performance benchmarks, and constraints that the calculations should explain.
* Prefer paper decomposition for detailed mechanisms, structural models, computational methods, and calculation settings.
* Prefer general paper insight for broad design principles, descriptors, field bottlenecks, alternative explanations, and computational opportunities.
* Use Generation context to determine the authoritative target, and treat any reaction-pathway prior only as a candidate hypothesis library rather than an established mechanism.


3. Target Claim and Autority Rules

* When author_reported_claim is present, copy its statement exactly into target_task.statement and copy the complete object into target_task.author_reported_claim. Otherwise, copy Generation context target_task exactly and set author_reported_claim to None.
* Preserve the authoritative claim exactly, but decompose it internally into scientifically meaningful claim components for computational scope assessment.
* Classify each component as directly testable, partially testable, or not testable using the supported computational capabilities.
* Generate strategies only for directly or partially testable components. For partial tests, state exactly what is evaluated and do not present a descriptor, thermodynamic tendency, or necessary condition as proof of the complete claim.
* Explicitly skip components that require experiments or unsupported calculations. Do not invent a proxy strategy for them, and if no component is computationally testable, generate no strategy.


4. Supported Computational Capabilities

* Supported model-building operations include bulk, slab, gas-phase, and adsorption site selection, together with only the structural modifications explicitly available in the provided capability registry.
* Default atomic simulation engine is MLIP (UMA), unless there is an explicit information that VASP is supported for this project.
* MLIP supports geometry relaxation and vibrational calculations.
* VASP calculations may use only operations listed as validated in the provided VASP capability registry.


5. Prohibitied Strategies and Claims

Prohibited computational work:
  Water covered slab structure strategies,
  transition-state searches, 
  NEB calculations, 
  activation-barrier calculations, 
  reaction-rate calculations, 
  microkinetic modeling, 
  molecular dynamics, 
  or any other unsupported computational method.
Prohibited workflows:
  synthesis, 
  catalyst preparation, 
  microscopy, 
  spectroscopy, 
  electrochemical cell testing, 
  isotope labeling, 
  product quantification, 
  Faradaic-efficiency measurement, 
  H-cell experiments, 
  zero-gap experiments, 
  or any other wet-lab workflow.
* Do not generate experimental strategies.
* Do not rename, approximate, or replace an unsupported calculation with an assumed or qualitative substitute.
* Do not calculate or invent an activation barrier from adsorption energies or reaction free energies.

Unsupported requirements:

* If the authoritative claim cannot be fully tested without a prohibited or unsupported calculation, state that limitation explicitly.
* In that case, provide only the strongest supported computational test and clearly delimit the conclusion it can support.


6. Definition of a Complete Strategy

Each strategy must be a self-contained claim-supporting workflow.

A complete strategy must contain:

0. Mechanistic explanation supports the author-reported claim.
1. The exact authoritative claim or claim component being tested.
2. A clearly labeled computational hypothesis.
3. The explicitly and unambiguously described entry point that anyone can execute the strategy from scratch.
3. The material, surface, active-site, and adsorbate models to construct.
4. Matched control models that isolate the variable tested by the hypothesis.
5. The chemical states, adsorbates, or reaction pathways to evaluate.
6. An ordered sequence of supported calculations.
7. The computational observables and comparisons to be obtained.
8. And requested fields on following python dictionary structure.
9. Free-energy diagram about complete reaction pathway. Full reaction pathway free-energy diagram is always required.

Completeness rules:

* Model construction, adsorption-site enumeration, geometry relaxation, intermediate enumeration, or adsorption-energy calculation alone is not a complete strategy.
* Model construction, adsorption-energy analysis, and free-energy analysis are calculation stages, not automatically separate strategies.
* If two proposed strategies must be combined to reach one primary claim-level conclusion, merge them into one strategy.
* Every strategy must independently produce an interpretable result concerning the authoritative claim.

Strategy specific rules:
  1. If doping is included in a strategy, doping formation energy always needs to be presented.
  2. For oxygen evolution and reduction reaction, you may run O, OH, or OOH precovered structure, depending on the intermediate before the potential determining step, or using grand potential surface phase diagram. Nonetheless prefer to skip precovered simulations unless absolutely needed for describing the experiment.
  3. CHE (Computational Hydrogen Electrode) method is always recommended for electrochemical energy calculation. Method called grand canonical electrode potential or constant charge potential methods are the more specific method to implement actual potential in the DFT. These are currently not implemented here, thus use the computational hydrogen electrode method for now.


7. Reaction and Mechanistic Modeling Rules

* Keep observations distinct from causal mechanisms, and label any mechanism not directly supported by the extraction artifacts as a hypothesis.
* Use the supplied reaction-pathway lists. Only deviate if it is absolutely necessary to describe experiment.
* If no artifact or pathway prior supports a detailed mechanism, do not invent one. State the limitation and use only the strongest supported intermediate or thermodynamic comparison.
* For every free-energy strategy, define the balanced overall reaction and explicitly include the initial state, every evaluated intermediate, and the terminal state. Map each state to an explicit computational model or thermodynamic reference, including gas, liquid, solvated, proton, and electron references when applicable.
* State the free-energy reference convention and applicable corrections for zero-point energy, entropy, solvation, potential, and pH. Do not omit unfavorable states or interpret an uphill free-energy step as an activation barrier or kinetic rate-determining step.


Supplied reaction-pathway:
    REACTION_PATHWAY_PRIORS = {
    "HER": {
        "products": ["H2"],
        "overall_reactions": {
            "acidic": "2H+ + 2e- -> H2",
            "alkaline": "2H2O + 2e- -> H2 + 2OH-"
        },
        "candidate_pathways": {
            "acidic_volmer_heyrovsky": [
                "*",
                "H*",
                "H2(g) + *"
            ],
            "acidic_volmer_tafel": [
                "2*",
                "2H*",
                "H2(g) + 2*"
            ],
            "alkaline_volmer_heyrovsky": [
                "* + H2O",
                "H* + OH-",
                "H2(g) + OH- + *"
            ],
            "alkaline_volmer_tafel": [
                "2* + 2H2O",
                "2H* + 2OH-",
                "H2(g) + 2OH- + 2*"
            ]
        },
        "reverse_reaction": "HOR"
    },

    "OER": {
        "products": ["O2"],
        "overall_reactions": {
            "acidic": "2H2O -> O2 + 4H+ + 4e-",
            "alkaline": "4OH- -> O2 + 2H2O + 4e-"
        },
        "candidate_pathways": {
            "adsorbate_evolution_mechanism": [
                "*",
                "OH*",
                "O*",
                "OOH*",
                "O2(g) + *"
            ],
            "lattice_oxygen_mechanism": [
                "Use only for oxygen-containing catalysts when lattice-oxygen participation is supported by the target claim or inherited evidence.",
                "Explicitly model lattice-oxygen activation, O-O coupling, oxygen-vacancy formation, O2 release, and lattice replenishment.",
                "Do not assume one universal lattice-oxygen sequence."
            ]
        }
    },

    "ORR": {
        "products": ["H2O", "OH-", "H2O2", "HO2-"],
        "overall_reactions": {
            "acidic_4e": "O2 + 4H+ + 4e- -> 2H2O",
            "alkaline_4e": "O2 + 2H2O + 4e- -> 4OH-",
            "acidic_2e": "O2 + 2H+ + 2e- -> H2O2",
            "alkaline_2e": "O2 + H2O + 2e- -> HO2- + OH-"
        },
        "candidate_pathways": {
            "associative_4e": [
                "O2(g) + *",
                "OOH*",
                "O* + H2O",
                "OH* + H2O",
                "2H2O + *"
            ],
            "associative_2e": [
                "O2(g) + *",
                "OOH*",
                "H2O2 or HO2- + *"
            ],
            "dissociative_4e": [
                "O2(g) + 2*",
                "O2* + *",
                "2O*",
                "O* + OH*",
                "2OH*",
                "OH* + H2O + *",
                "2H2O + 2*"
            ]
        }
    },

    "CO2RR": {
        "products": [
            "CO",
            "HCOOH or HCOO-",
            "CH4",
            "CH3OH",
            "C2H4",
            "C2H5OH"
        ],
        "overall_reactions": {
            "CO": "CO2 + 2H+ + 2e- -> CO + H2O",
            "formic_acid": "CO2 + 2H+ + 2e- -> HCOOH",
            "methane": "CO2 + 8H+ + 8e- -> CH4 + 2H2O",
            "methanol": "CO2 + 6H+ + 6e- -> CH3OH + H2O",
            "ethylene": "2CO2 + 12H+ + 12e- -> C2H4 + 4H2O",
            "ethanol": "2CO2 + 12H+ + 12e- -> C2H5OH + 3H2O"
        },
        "candidate_pathways": {
            "CO": [
                "CO2 + *",
                "COOH*",
                "CO* + H2O",
                "CO(g) + H2O + *"
            ],
            "formate": [
                "CO2 + *",
                "OCHO* or HCOO*",
                "HCOOH or HCOO- + *"
            ],
            "methane_via_CHO": [
                "CO2 + *",
                "COOH*",
                "CO*",
                "CHO*",
                "CHOH*",
                "CH* + H2O",
                "CH2*",
                "CH3*",
                "CH4(g) + *"
            ],
            "methane_via_COH": [
                "CO2 + *",
                "COOH*",
                "CO*",
                "COH*",
                "C* + H2O",
                "CH*",
                "CH2*",
                "CH3*",
                "CH4(g) + *"
            ],
            "methanol": [
                "CO2 + *",
                "COOH*",
                "CO*",
                "CHO*",
                "CH2O*",
                "CH3O*",
                "CH3OH + *"
            ],
            "C2_coupling_entry": [
                "2CO* -> OCCO*",
                "CO* + CHO* -> OCCHO*",
                "Select and fully specify downstream intermediates using product-specific inherited evidence.",
                "Do not generate a C2 free-energy diagram from this entry pathway alone."
            ]
        },
        "required_competing_pathways": [
            "HER",
            "CO desorption versus further CO* reduction",
            "COOH* versus OCHO* formation",
            "C1 hydrogenation versus C-C coupling when C2 products are relevant"
        ]
    },

    "NRR": {
        "products": ["NH3"],
        "overall_reaction": "N2 + 6H+ + 6e- -> 2NH3",
        "candidate_pathways": {
            "associative_distal": [
                "N2(g) + *",
                "N2*",
                "NNH*",
                "NNH2*",
                "N* + NH3",
                "NH* + NH3",
                "NH2* + NH3",
                "NH3* + NH3",
                "2NH3 + *"
            ],
            "associative_alternating": [
                "N2(g) + *",
                "N2*",
                "NNH*",
                "NHNH*",
                "NHNH2*",
                "NH2NH2*",
                "NH2* + NH3",
                "NH3* + NH3",
                "2NH3 + *"
            ]
        },
        "required_competing_pathways": [
            "HER"
        ],
        "conditional_pathways": {
            "dissociative": [
                "Evaluate only when N-N dissociation is supported by inherited evidence and the required calculation is supported.",
                "Do not infer N-N dissociation kinetics from the thermodynamic stability of 2N*."
            ]
        }
    },

    "NO3RR": {
        "products": ["NH3", "NO2-", "NO", "N2O", "N2"],
        "overall_reaction_to_NH3": "NO3- + 9H+ + 8e- -> NH3 + 3H2O",
        "candidate_pathways": {
            "hydroxylamine_pathway": [
                "NO3- + *",
                "NO3*",
                "NO3H*",
                "NO2* + H2O",
                "NO2H*",
                "NO* + H2O",
                "NOH*",
                "NHOH*",
                "NH2OH*",
                "NH2* + H2O",
                "NH3*",
                "NH3 + *"
            ],
            "atomic_nitrogen_branch": [
                "NO*",
                "NOH*",
                "N* + H2O",
                "NH*",
                "NH2*",
                "NH3*",
                "NH3 + *"
            ],
            "alternative_NO_hydrogenation": [
                "NO*",
                "NHO* or HNO*",
                "Continue only when the downstream pathway is supported by inherited evidence."
            ]
        },
        "selectivity_branches": [
            "NO3* or NO2* desorption toward NO2-",
            "NO* desorption toward NO",
            "N-N coupling toward N2O or N2 when adjacent active sites are available",
            "HER"
        ]
    },


8. Strategy Prioritization
* Always start with strategy that cost less computation time, and build up as needed to describe experiment.


9. General requirements:
* Output exactly one Python assignment named generated_strategies.
* Use valid Python syntax with double-quoted string keys and string values.
* Use None for unavailable scalar values.
* Use empty lists when no supported entries exist.
* Do not invent references, paper metadata, mechanisms, settings, experimental values, or source claims.
* Every decision must include explicit references showing where it came from.
* Every field named "references" must contain at least one complete reference object.
* References must be inherited from the extraction artifacts. If an extraction artifact contains source metadata from a cited paper, preserve that metadata under inherited_source.
* If source metadata is unavailable, set inherited_source to None and still identify the extraction artifact plus supporting statement.
* Results in this output are proposed expected computational results, computational checks, or benchmark comparisons, not established current-paper findings. Mark that status explicitly.
* Do not collapse all evidence into one generic bibliography. Attach references directly to the decision or claim they support.
* The "experiment" object in every strategy must contain computational experiments only.
* Schema notation: Replace every REFERENCE_DICT with a non-empty list of complete reference objects; never output the literal placeholder.

Reference schema (REFERENCE_DICT):
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
        "benchmark_constraints": [
            {
                "constraint": "...",
                "references": [REFERENCE_DICT]
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
            "decision_target": "...",
            "problem": {
                "question": "...",
                "unexplained_phenomenon": "...",
                "context": "...",
                "references": [REFERENCE_DICT]
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
                        "references": [REFERENCE_DICT]
                    }
                ]
            },
            "hypothesis": {
                "statement": "...",
                "derived_from_axioms": ["..."],
                "proposed_mechanism_or_prediction": "...",
                "references": [REFERENCE_DICT]
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
                    "references": [REFERENCE_DICT]
                }
            },
            "results": {
                "expected_computational_results": [
                    {
                        "statement": "...",
                        "status": "proposed expectation, not established",
                        "references": [REFERENCE_DICT]
                    }
                ],
                "computational_benchmark_comparisons": [
                    {
                        "statement": "...",
                        "status": "benchmark comparison to compute, not established",
                        "references": [REFERENCE_DICT]
                    }
                ],
                "computational_tests_to_run": {
                    "mechanism_and_descriptor_tests": [
                        {
                            "statement": "...",
                            "status": "calculation to run",
                            "references": [REFERENCE_DICT]
                        }
                    ],
                    "selectivity_and_competing_pathway_tests": [
                        {
                            "statement": "...",
                            "status": "calculation to run",
                            "references": [REFERENCE_DICT]
                        }
                    ],
                    "stability_and_surface_state_tests": [
                        {
                            "statement": "...",
                            "status": "calculation to run",
                            "references": [REFERENCE_DICT]
                        }
                    ]
                }
            },
            "author_claim_support_if_successful": {
                "expected_strength": "strong | moderate | weak",
                "maximum_supported_conclusion": "...",
                "out_of_scope": ["..."]
            },
            "conclusion": {
                "causal_mechanism": "...",
                "design_principle": "...",
                "scope_or_limitations": "...",
                "references": [REFERENCE_LIST]
            },
            "decision_trace": [
                {
                    "decision": "...",
                    "why_it_matters_for_target_task": "...",
                    "references": [REFERENCE_LIST]
                }
            ]
        }
    ],
    "prioritization": {
        "recommended_order": ["S1"],
        "rationale": [
            {
                "statement": "...",
                "references": [REFERENCE_LIST]
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

10. Definitions of Selected generated_strategies Fields:
"decision_target": The specific component or causal link within the author-reported claim that the strategy is designed to evaluate computationally.
"author_claim_support_if_successful": The strongest bounded mechanistic support that the strategy may provide for the author-reported claim if its expected computational outcome is obtained.
"unsupported_gaps": If a strategy cannot be supported by the extraction artifacts, do not include it as a strategy. Put the missing idea in unsupported_gaps instead.
"""


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

    strategies = payload.get("strategies")
    if not isinstance(strategies, list):
        raise SystemExit("Generated strategies must be a list")
    for index, strategy in enumerate(strategies):
        strategy_path = f"generated_strategies.strategies[{index}]"
        if not isinstance(strategy, dict):
            raise SystemExit(f"{strategy_path} must be an object")
        if not isinstance(strategy.get("decision_target"), str) or not strategy[
            "decision_target"
        ].strip():
            raise SystemExit(f"{strategy_path}.decision_target must be a non-empty string")

        support = strategy.get("author_claim_support_if_successful")
        if not isinstance(support, dict):
            raise SystemExit(f"{strategy_path}.author_claim_support_if_successful must be an object")
        if support.get("expected_strength") not in {"strong", "moderate", "weak"}:
            raise SystemExit(
                f"{strategy_path}.author_claim_support_if_successful.expected_strength "
                "must be one of: strong, moderate, weak"
            )
        maximum_conclusion = support.get("maximum_supported_conclusion")
        if not isinstance(maximum_conclusion, str) or not maximum_conclusion.strip():
            raise SystemExit(
                f"{strategy_path}.author_claim_support_if_successful."
                "maximum_supported_conclusion must be a non-empty string"
            )
        out_of_scope = support.get("out_of_scope")
        if not isinstance(out_of_scope, list) or not all(
            isinstance(item, str) and item.strip() for item in out_of_scope
        ):
            raise SystemExit(
                f"{strategy_path}.author_claim_support_if_successful.out_of_scope "
                "must be a list of non-empty strings"
            )

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
