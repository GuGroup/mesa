---
name: generate-strategies
description: Generate evidence-backed computational chemistry strategies that preserve a primary author-reported experimental claim from prior extraction artifacts. Use when Codex needs to synthesize outputs from extract-data-from-experiment, extract-strategy-paper, and extract-general-insights-paper into multiple DFT/computational proof strategies without broadening the authoritative claim, while retaining problem/axioms/hypothesis/experiment/results/conclusion structure and explicit references.
---

For MESA end-to-end use, read `SKILL/strategy/workflow.md` before applying this skill.

# Strategy Generation Prerequisites

Before generating any strategy, the agent must complete the following validation steps.

## Mandatory Checks

Do not generate a strategy until all of the following conditions are satisfied:

1. Verify that each directory exists and contains one or more PDF files and its extractions:
   - `literature/strategy*`
   - `literature/domain*`
   - `literature/legacy*`

2. If any required directory is missing, or if any directory does not contain at least one PDF file, stop the strategy generation process and request the missing materials from the user.

## Failure Handling

If the prerequisites are not met, respond with a message similar to:

> Strategy generation cannot proceed because the required literature sources are incomplete.
>
> Please ensure that:
> - `literature/strategy*` exists and contains relevant PDF papers.
> - `literature/domain*` exists and contains relevant PDF papers.
> - `literature/legacy*` exists and contains relevant PDF papers.
>
> Upload or provide the missing documents before requesting strategy generation again.

## Enforcement

These validation checks are mandatory and must be completed before any strategy generation, analysis, synthesis, recommendation, or planning activities are performed.


# Generate Strategies

## Overview

Use this skill after experimental data extraction and paper extraction have already been saved as text artifacts. The output is a computational chemistry strategy-generation artifact, not a loose summary and not an experimental plan.

The generator must:

- Use the single `author_reported_claim` from experimental extraction as the
  authoritative target when available.
- Copy that claim exactly into `target_task.statement`; do not add causal
  variables, structures, mechanisms, or performance claims to it.
- Use `--target-task` only as a fallback when no extracted claim exists, or to
  select one exact claim when several experimental extractions are supplied.
- Apart from its authoritative claim, use experimental extraction only as
  benchmark constraints, material identity, or measured targets to explain
  computationally.
- Use paper extraction as the source of mechanisms, design principles, computational methods, descriptors, and inherited references.
- Generate only computational chemistry strategies, such as free-energy analysis.
- Do not generate synthesis, characterization, electrochemical testing, isotope labeling, cell design, product quantification, or other wet-lab strategies.
- Produce multiple strategies, each shaped like a `paper_decomposition` branch:

```python
paper_decomposition = {
    "problem": {...},
    "axioms": {...},
    "hypothesis": {...},
    "experiment": {...},
    "results": {...},
    "conclusion": {...},
}
```

- Include explicit references for every decision and inherited claim.

## Inputs

Collect the saved outputs from previous workflow steps:

- Experimental data extraction from `extract-data-from-experiment`.
- Strategy-folder paper decompositions from `extract-strategy-paper`.
- Non-strategy paper insights from `extract-general-insights-paper`.

Prefer saved `.txt`, `.md`, `.py`, or `.json` extraction artifacts over PDFs. Do not rerun PDF extraction unless the expected extraction output is missing.

## Workflow

1. Identify the material domain and any user-supplied exact claim selection;
   do not compose a broader target task when an extracted claim exists.
2. Confirm at least one paper extraction artifact in each domain, strategy, legacy section is available.
3. Confirm that an experimental extraction contains exactly one
   `author_reported_claim` section with `abstract` and `conclusion` source
   locations. When no experimental claim exists, supply `--target-task`.
4. Run `scripts/generate_strategies.py` with the extraction artifacts.
5. Review the output for claim drift, unsupported decisions, and experimental-strategy leakage:
   - `target_task.statement` must exactly match the extracted claim.
   - `target_task.author_reported_claim` must preserve both source locations.
   - Descriptive observations must not be promoted to causal target variables.
   - Every strategy decision must include a `references` list.
   - References must point back to an extraction artifact and, when available, preserve the source metadata inherited from that extraction.
   - `experiment` must describe only computational experiments.
   - No strategy should propose lab synthesis, microscopy, spectroscopy, product quantification, isotope labeling, H-cell/zero-gap testing, or other experimental workflows.
   - If a decision has no support in the extraction artifacts, remove it or mark it as an explicit unsupported gap.
6. Preserve the output artifact because it is downstream evidence for strategy selection.

## Script

Run:

```bash
python3 SKILL/strategy/generate-strategies/scripts/generate_strategies.py \
  --material-domain "..." \
  --experimental-extraction /path/to/experimental_extraction.txt \
  --paper-decomposition /path/to/strategy_paper_decomposition.py \
  --general-insight /path/to/domain_or_review_insight.py
```

Useful options:

- `--target-task`: fallback only when no author-reported claim is present; with
  multiple extracted claims, use the exact statement to select one.
- `--num-strategies`: requested number of strategies. Defaults to `5`.
- `--paper-extraction`: generic paper extraction artifact when the subtype is unknown.
- `--task-note`: non-conflicting computational context, such as preferred DFT level, surface facet, adsorbate set, or known material family.
- `--output`: write generated text to a file.
- `--save-response`: write the full OpenAI API response JSON for debugging.
- `--dry-run`: validate inputs and print request metadata without calling the API.

The script reads `OPENAI_API_KEY` from the environment and uses only the Python standard library.

## Output Contract

The script asks for exactly one Python assignment named `generated_strategies`:

```python
generated_strategies = {
    "target_task": {
        "statement": "exact author-reported claim",
        "author_reported_claim": {
            "statement": "exact author-reported claim",
            "source_locations": {
                "abstract": "...",
                "conclusion": "...",
            },
            "extraction_artifact": "...",
        },
        ...
    },
    "input_artifacts": {...},
    "strategies": [
        {
            "strategy_id": "S1",
            "title": "...",
            "decision_target": "...",
            "problem": {...},
            "axioms": {...},
            "hypothesis": {...},
            "experiment": {...},
            "results": {...},
            "author_claim_support_if_successful": {...},
            "conclusion": {...},
            "decision_trace": [...]
        }
    ],
    "prioritization": {...},
    "unsupported_gaps": []
}
```

Each strategy must be clear enough to compare against `extract-strategy-paper`
output, while making two distinctions explicit:

- `experiment` means computational experiment only.
- `results` are expected computational results, computational checks, or benchmark comparisons for a proposed strategy, not established current-paper findings.

The script parses the author claim before the API call and validates the
returned Python assignment afterward. It fails if the model changes either the
authoritative statement or its source-location object.

Reference objects must use this shape:

```python
{
    "extraction_artifact": "...",
    "extraction_type": "experimental_extraction | paper_decomposition | general_insight | paper_extraction",
    "inherited_source": {...},
    "supporting_statement": "...",
    "decision_role": "benchmark_constraint | axiom | mechanism | method | descriptor | computational_test | risk | prioritization"
}
```

Use `None` for `inherited_source` only when the source extraction did not provide bibliographic metadata. Do not invent references, paper titles, authors, years, mechanisms, DFT settings, or experimental values. Do not turn experimental values into experimental action plans.
