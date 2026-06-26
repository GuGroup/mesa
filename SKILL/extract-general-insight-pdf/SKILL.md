---
name: extract-general-insight-pdf
description: Extract broad, topic-level scientific insights from a local paper PDF, especially review papers, perspective articles, roadmap papers, and domain-overview papers that do not report one detailed computational workflow. Use when Codex needs a loose but structured synthesis of general mechanisms, design principles, progress, challenges, opportunities, and reusable lessons from a scientific PDF.
---

# Extract General Insight PDF

## Overview

Use this skill to extract general insight from scientific review papers and domain-overview papers. Always use the bundled script so the prompt stays consistent and the output remains structured enough to reuse.

## Workflow

1. Confirm the target file is a PDF and is under 50 MB.
2. Run `scripts/extract_general_insight.py` with the PDF path.
3. Use `--topic` when the user wants insight about a specific topic within the paper, such as high-entropy alloys for catalysis, catalyst design, surface segregation, or computational screening.
4. Use `--task-note` only for non-conflicting context, such as the user's intended downstream use.
5. Treat output as a structured synthesis of the paper's content. For review papers, preserve broad conclusions and cited consensus rather than force a detailed experiment/result decomposition.

## Script

Run:

```bash
python3 /path/to/extract-general-insight-pdf/scripts/extract_general_insight.py /path/to/review.pdf --topic "high-entropy alloys in catalysis"
```

Useful options:

- `--model`: override the model. Defaults to `OPENAI_MODEL`, then `gpt-5.5`.
- `--topic`: focus extraction on a specific topic covered by the paper.
- `--task-note`: append narrow, non-conflicting context.
- `--save-response`: write the full API response JSON for debugging.
- `--dry-run`: validate inputs and show request metadata without calling the API.

The script reads `OPENAI_API_KEY` from the environment and uses only the Python standard library. It outputs exactly one Python assignment named `paper_general_insight`.

## Extraction Boundaries

Prefer generalizable scientific insight over exhaustive detail:

- Capture the paper's central thesis, field context, organizing concepts, mechanisms, design principles, challenges, and future opportunities.
- For review papers, distinguish `reviewed_consensus` from the review authors' own `synthesis_or_perspective`.
- Include representative examples only when they support a general insight.
- Do not force missing DFT settings, experimental protocols, or paper-specific result schemas.
- Do not invent citations or convert broad claims into falsely precise mechanisms.
- Keep uncertainty visible when the paper frames a point as unresolved, debated, or prospective.
