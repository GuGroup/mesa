---
name: generate-strategies
description: Generate evidence-backed computational chemistry strategies for a target materials/chemistry task from prior extraction artifacts. Use when Codex needs to synthesize outputs from extract-data-from-experiment, extract-strategy-paper, and extract-general-insights-paper into multiple DFT/computational proof strategy dictionaries that preserve the problem/axioms/hypothesis/experiment/results/conclusion structure, exclude experimental strategy generation, and include explicit inherited references for every decision.
---

For MESA end-to-end use, read `SKILL/strategy/workflow.md` before applying this skill.

# Generate Strategies

## Overview

Use this skill after experimental data extraction and paper extraction have already been saved as text artifacts. The output is a computational chemistry strategy-generation artifact, not a loose summary and not an experimental plan.

The generator must:

- Use the target task as the organizing objective.
- Use experimental extraction only as benchmark constraints, material identity, or measured targets to explain computationally.
- Use paper extraction as the source of mechanisms, design principles, computational methods, descriptors, and inherited references.
- Generate only computational chemistry strategies, such as DFT slab/adsorbate modeling, adsorption/free-energy analysis, transition-state searches, HEA site sampling, AIMD/solvation/potential corrections, microkinetics, descriptor screening, stability/reconstruction calculations, and computational uncertainty checks.
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

1. Identify the target task and material domain from the user or workflow context.
2. Confirm at least one paper extraction artifact is available.
3. Run `scripts/generate_strategies.py` with the target task and extraction artifacts.
4. Review the output for unsupported decisions and experimental-strategy leakage:
   - Every strategy decision must include a `references` list.
   - References must point back to an extraction artifact and, when available, preserve the source metadata inherited from that extraction.
   - `experiment` must describe only computational experiments.
   - No strategy should propose lab synthesis, microscopy, spectroscopy, product quantification, isotope labeling, H-cell/zero-gap testing, or other experimental workflows.
   - If a decision has no support in the extraction artifacts, remove it or mark it as an explicit unsupported gap.
5. Preserve the output artifact because it is downstream evidence for strategy selection.

## Script

Run:

```bash
python3 SKILL/strategy/generate-strategies/scripts/generate_strategies.py \
  --target-task "..." \
  --material-domain "..." \
  --experimental-extraction /path/to/experimental_extraction.txt \
  --paper-decomposition /path/to/strategy_paper_decomposition.py \
  --general-insight /path/to/domain_or_review_insight.py
```

Useful options:

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
    "target_task": {...},
    "input_artifacts": {...},
    "strategies": [
        {
            "strategy_id": "S1",
            "title": "...",
            "problem": {...},
            "axioms": {...},
            "hypothesis": {...},
            "experiment": {...},
            "results": {...},
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
