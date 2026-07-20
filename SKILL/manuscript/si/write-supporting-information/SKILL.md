---
name: write-supporting-information
description: Create minimal Supporting Information section JSON from an assembled computational catalysis manuscript DOCX. Use when Codex must fill SI placeholders such as supplementary figure headings/text and Density Functional Theory calculation details, using existing manuscript text, SI figure captions, and Methods detail paragraphs without adding new scientific claims.
---

For MESA end-to-end use, read `SKILL/manuscript/workflow.md` before applying this skill.

# Supporting Information Writer

## Scope

Use this skill after main text, figures, title, abstract, keywords, conclusion,
and references have been assembled in a DOCX.

This skill writes minimal, inserter-ready JSON for:

- `{{SI_LARGE_CONTENT_TITLE}}`
- `{{SI_LARGE_CONTENT_TEXT}}`
- `{{SI_SMALL_CONTENT_TITLE}}`
- `{{SI_SMALL_CONTENT_TEXT}}`
- `{{DENSITY_FUNCTIONAL_THEORY_CALCULATION_DETAILS_TEXT}}`

It is additive only. It does not remove detail from the main Methods section;
use `methods-to-si-mover` after SI insertion for that.

## Workflow

Run:

```bash
python SKILL/manuscript/si/write-supporting-information/scripts/write_supporting_information.py \
  --manuscript-docx project/<project>/manuscript/<strategy>/<manuscript>.docx \
  --strategy-id <strategy>
```

Default output:

```text
project/<project>/strategy_execution/<strategy_id>_si/text/
  supporting_information_text.json
  supporting_information_text.md
  si_large_content_title_section_text.json
  si_large_content_text_section_text.json
  si_small_content_title_section_text.json
  si_small_content_text_section_text.json
  dft_calculation_details_section_text.json
```

## Rules

- Keep SI text compact and mechanical.
- Write supplementary figure text only for existing SI figures; otherwise write
  compact no-content placeholder text.
- Move detected detailed calculation/geometry-optimization details into the DFT
  calculation details placeholder; do not create new parameters.
- Preserve existing numeric citation markers if extracted from the manuscript.
- Round non-integer values in inserted SI text to at most two decimal places
  (for example, `1.184` becomes `1.18`); leave integers as integers. Preserve
  full precision in extracted source metadata.
- Do not add new claims, new calculations, limitations prose, or future work.

Read [references/output_schema.md](references/output_schema.md) when consuming
or revising the output contract.
