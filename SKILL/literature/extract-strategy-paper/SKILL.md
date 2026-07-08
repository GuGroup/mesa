---
name: extract-strategy-paper
description: Extract a computational chemistry scientific paper PDF into a structured Python dictionary covering problem, inherited axioms with sources, hypothesis, computational and experimental procedures, current-paper results, integrated computation-experiment findings, and conclusion. Use when Codex needs to analyze a local scientific PDF rather than summarize it loosely.
---

For MESA end-to-end use, read `SKILL/literature/workflow.md` before applying this skill.

# Decompose Chemistry Paper PDF

## Overview

Use this skill to decompose a local computational chemistry paper PDF into a structured knowledge representation. Always use the bundled script so the extraction prompt remains fixed and the output schema remains stable.

## Workflow

1. Confirm the target file is a PDF and is under 50 MB.
2. Run `scripts/decompose_pdf.py` with the PDF path.
3. Use `--task-note` only for non-conflicting context, such as a target catalyst, material, reaction, or section range.
4. Treat unresolved citations conservatively: if a referenced source cannot be identified from the PDF, leave its source as `null`.
5. Preserve the model output as evidence-bearing extraction, not ground truth. If the output feeds another workflow, keep the PDF path and response file for auditability.

## Script

Run:

```bash
python3 SKILL/literature/extract-strategy-paper/scripts/decompose_pdf.py /path/to/paper.pdf
```

Useful options:

- `--model`: override the model. Defaults to `OPENAI_MODEL`, then `gpt-5.5`.
- `--task-note`: append narrow, non-conflicting context to the fixed prompt.
- `--save-response`: write the full API response JSON for debugging.
- `--dry-run`: validate inputs and show request metadata without calling the API.

The script reads `OPENAI_API_KEY` from the environment and uses only the Python standard library. It asks for exactly one Python assignment named `paper_decomposition` with these top-level keys:

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

## Extraction Boundaries

The output must distinguish inherited knowledge from findings established by the current paper.

- `axioms`: prior claims assumed, inherited, or built upon; include full bibliographic source metadata when available.
- `hypothesis`: only the new mechanism or prediction proposed before results.
- `experiment`: calculations, simulations, measurements, datasets, models, and procedures used to test the hypothesis; include DFT details such as slab model, adsorption site, exchange-correlation functional, code, pseudopotentials, cutoff, k-point mesh, convergence criteria, dispersion correction, solvation, spin, charge, and transition-state settings when reported.
- `results`: only current-paper findings, each with `{"statement": "...", "novelty": "current paper"}`.
- `integrated_results`: store inside `results`; include cases where computation explains experiment, experiment validates computation, or theory and experiment disagree.

Do not invent references, mechanisms, settings, or missing values. Prefer author names over citation numbers and resolve reference numbers into full bibliography entries whenever the PDF provides them.
