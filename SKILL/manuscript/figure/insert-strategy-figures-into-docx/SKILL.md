---
name: insert-strategy-figures-into-docx
description: Insert realized strategy figures into a manuscript DOCX skeleton. Use after strategy-figure-realizer and strategy-figure-captioner when Codex must place exported PNG figures and public figure_title/caption text into a Word skeleton, assign deterministic main/SI figure numbers, skip blocked figures, and write insertion reports without rewriting scientific captions.
---

# Strategy Figure DOCX Inserter

## Scope

Use this skill after `strategy-figure-captioner`.
It edits DOCX export artifacts only; it does not choose scientific figure types,
draw figures, write captions, or change manuscript claims.

Required inputs:

- DOCX skeleton/template, preferably `RESOURCE/manuscript_skeleton_polished.docx`
- `caption_info.json` from `strategy-figure-captioner`
- optional `figure_realization.json` for figure levels and fallback image paths
- optional location map for explicit main/SI/skip placement and ordering

Default output:

```text
project/<project>/manuscript/<strategy>/
  <name>_with_figures.docx
  <name>_with_figures.insertion_report.json
  <name>_with_figures.insertion_report.md
```

## Numbering Rules

Assign labels deterministically after ordering:

- Main figures: `Fig. 1`, `Fig. 2`, ...
- Supporting Information figures: `Fig. S1`, `Fig. S2`, ...
- Blocked, skipped, failed, excluded, or image-missing figures: no number

Do not use `Supplementary Fig. 1` unless the user explicitly asks for that style.

## Placement Rules

Use an explicit location map when supplied. Supported values are:

- `main`, `paper`, `manuscript`, `body`, `results`
- `si`, `supplementary`, `supporting`, `supporting-information`
- `skip`, `archive`, `unnecessary`

Without a location map:

- `level: supplementary` becomes SI
- `level: archive`, `unnecessary`, or blocked states are skipped
- all other realized figures are main-text figures

For a skeleton with `{{FIGURE_NUMBER}} | {{FIGURE_TITLE}} {{FIGURE_CAPTION}}`,
replace that paragraph with all main figure blocks. Insert SI figure blocks
after `{{SI_SMALL_CONTENT_TEXT}}` by default.

Format figure captions as:

```text
Fig. N | Figure title. Caption text.
```

Apply bold formatting to the figure number label, separator, and figure title.
Keep the caption body regular.

Scale each image to fit both width and height constraints while preserving
aspect ratio. The default limits are `--max-width-in 6.25` and
`--max-height-in 9.0`.

## Command

```bash
python SKILL/strategy-figure-docx-inserter/scripts/insert_strategy_figures_docx.py \
  --template RESOURCE/manuscript_skeleton_polished.docx \
  --caption-info project/<project>/strategy_execution/<strategy>_figure/caption/caption_info.json \
  --realization project/<project>/strategy_execution/<strategy>_figure/realization/figure_realization.json \
  --output project/<project>/manuscript/<strategy>/<strategy>_manuscript_with_figures.docx
```

Optional location map:

```json
{
  "figures": [
    {"figure_id": "F3", "placement": "main", "order": 1},
    {"figure_id": "F8", "placement": "si", "order": 1}
  ]
}
```

Use `--figure-prefix "Fig"` only if the target journal requires labels without
periods, like `Fig 1` and `Fig S1`.

Use `--max-height-in` to make tall figures fit the page vertically. The script
uses the smaller of the horizontal and vertical scale factors.

## Boundaries

- Use only `figure_title`, `caption`, and `extended_caption` from
  `caption_info.json` for public caption text.
- Keep provenance, procedure IDs, caveats, and blockers out of DOCX captions.
- Do not overwrite the skeleton. Always write a new DOCX.
- Write the JSON and Markdown insertion reports for audit.
- Preserve DOCX root namespace declarations when editing `word/document.xml`;
  missing declarations referenced by Word compatibility metadata can force
  Microsoft Word to open the document in recovery mode.
