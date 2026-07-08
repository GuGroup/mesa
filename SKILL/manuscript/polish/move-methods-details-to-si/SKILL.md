---
name: move-methods-details-to-si
description: Compress detailed Methods text after Supporting Information insertion by moving geometry-optimization details out of the main manuscript Methods section. Use when Codex must remove duplicate detailed DFT/relaxation setup from main text while preserving a concise Methods bridge to Supporting Information in a DOCX.
---

# Methods To SI Mover

## Scope

Use this skill after `supporting-information-writer` has inserted DFT details
into the Supporting Information.

This mover edits only the DOCX Methods section. It replaces a configured
detailed Methods paragraph block with one concise bridge paragraph and removes
configured continuation paragraphs.

It does not rewrite other Methods subsections, citations, figures, references,
or SI content.

## Workflow

Run:

```bash
python SKILL/methods-to-si-mover/scripts/move_methods_details_to_si.py \
  --input-docx project/<project>/manuscript/<strategy>/<manuscript_with_si>.docx \
  --output-docx project/<project>/manuscript/<strategy>/<manuscript_methods_moved>.docx \
  --config optional_methods_to_si_config.json
```

Default report paths are written beside the output DOCX.

## Rules

- Only remove detail that has already been inserted into SI.
- Preserve the main Methods structure and concise bridge paragraph.
- Do not touch equations, figure blocks, references, title, or SI content.
- Validate that the configured detail block was replaced and not duplicated.

Read [references/move_report_schema.md](references/move_report_schema.md) when
consuming or revising the report contract.
