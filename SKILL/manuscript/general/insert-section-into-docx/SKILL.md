---
name: insert-section-into-docx
description: Insert structured manuscript section JSON into a DOCX skeleton/template. Use when Codex must place generated section text such as methods_section_text.json into a Word manuscript, replace placeholders like {{METHOD_TEXT}}, preserve DOCX integrity, render section headings, paragraphs, and simple LaTeX equation blocks, and write insertion reports without rewriting the scientific prose.
---

For MESA end-to-end use, read `SKILL/manuscript/workflow.md` before applying this skill.

# Manuscript Section DOCX Inserter

## Overview

Use this skill after a manuscript section writer has produced structured JSON
with a `sections` array. It edits DOCX export artifacts only; it does not write,
polish, cite, or scientifically revise the section text.

Supported v1 content:

- ordered `content_blocks` from the section JSON
- bold section titles from `section.small_title` when present, otherwise
  `section.title`, followed by one space and the first paragraph block in the
  same DOCX paragraph
- `section.render_title: false` to insert the first paragraph as ordinary body
  text without a bold local title, useful when the DOCX skeleton already has the
  section heading
- optional `section.paragraph_style` for direct paragraph formatting, currently
  supporting `bold`, `italic`, `font_size_pt`, and `align`
- remaining paragraph blocks in manuscript order
- Word-native OMML equations converted from LaTeX equation blocks by Pandoc
- one blank paragraph before and after each logical equation block
- equation explanations as regular manuscript paragraphs
- aligned multi-row LaTeX equations split into one rendered Word equation per row
- optional movement of existing main-text figure drawing/caption blocks after
  inserted paragraphs that first mention each figure

Equation `label` values are retained in JSON and reports but are not rendered in
the DOCX manuscript body.

Equation rendering defaults to `--equation-mode omml`, which requires Pandoc.
The script first checks `PATH`, then the repo-local
`DEPENDENCY/tools/pandoc/bin/pandoc`. Use `--equation-mode text` only when the
user explicitly asks for plain-text equations. A manuscript-ready DOCX must not
show raw LaTeX equation strings in place of Word-native equations.

If a LaTeX equation is wrapped in `\begin{aligned}...\end{aligned}`, each row
separated by `\\` is rendered as a separate Word equation object. Blank
paragraph spacing is added only before the first split row and after the last
split row.

## Command

```bash
python SKILL/manuscript/general/insert-section-into-docx/scripts/insert_section_docx.py \
  --template RESOURCE/manuscript_skeleton_polished.docx \
  --section-json project/<project>/strategy_execution/<strategy>_methods/text/methods_section_text.json \
  --output project/<project>/manuscript/<strategy>/<strategy>_manuscript_with_methods.docx
```

Defaults are tuned for Methods insertion:

- `--placeholder "{{METHOD_TEXT}}"`
- `--title-placeholder "{{METHODS_SMALL_TITLE}}"`
- `--equation-mode omml`
- remove the title placeholder after using its paragraph style for section headings

Use `--placeholder` to target other manuscript sections. Use
`--keep-title-placeholder` only when the target skeleton still needs that
placeholder for another pass.

For Results insertion, use `--distribute-figures` when the DOCX already contains
main-text figure blocks after the Results placeholder and the inserted Results
paragraphs cite those figures. The script moves existing `Fig. N |` drawing and
caption blocks; it does not edit figure images or captions. Supporting
Information figures such as `Fig. S1` are not moved by this option.

## Rules

- Prefer structured JSON over Markdown when both are available.
- Displayed equations must be represented as `content_blocks` with
  `type: "equation"` and `latex`; do not place LaTeX math delimiters or raw TeX
  in paragraph text as a substitute for equation blocks.
- Do not overwrite the template DOCX.
- Do not insert `missing_details` into the manuscript body by default.
- Keep citation keys as literal text if present; citation resolution belongs to
  a later reference skill.
- Preserve DOCX root namespace declarations when editing `word/document.xml`;
  missing declarations referenced by Word compatibility metadata can force
  Microsoft Word to open the document in recovery mode.
- Preserve canonical Word compatibility namespace prefixes such as `mc` and
  `w14`, and keep `mc:Ignorable` synchronized with actually used compatibility
  prefixes.
- When moving figures, move only existing DOCX blocks. Do not regenerate,
  rewrite, or duplicate figures.

Read [references/section_json_schema.md](references/section_json_schema.md)
when revising the accepted input contract.
