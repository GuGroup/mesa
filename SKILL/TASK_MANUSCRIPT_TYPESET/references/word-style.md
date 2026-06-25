# Word Style and Notation Guide

This guide controls Word/DOCX export expectations for Nature-family manuscript
drafts. It is a formatting contract for export artifacts, not permission to edit
canonical `paper/` sources outside the manuscript loop.

## Style Source of Truth

- The canonical text remains in `paper/manuscript/sections/*.md`.
- The Word style source is an optional `--reference-doc` file passed to
  `export_docx.py`.
- The reference document should define styles for Title, Heading 1, Heading 2,
  Body Text, Figure Caption, Table Caption, References, and Normal.
- If no reference document is available, the export is a structurally valid
  Word draft but not a final journal-style layout.

## Section Formatting

- Use one title line and semantic Markdown headings. Do not emulate spacing
  with blank paragraphs.
- Keep Results before Methods only when the manuscript loop section contracts
  require that order.
- Put supplementary sections under manuscript source files that are marked as
  SI in `section-contracts.yaml`.
- Do not manually renumber headings in Markdown; Word styles and Pandoc handle
  numbering when the reference document enables it.

## Inline Scientific Notation

Use Pandoc Markdown notation so DOCX output can map to native Word
super/subscript runs:

- Subscripts: `H~2~O`, `O~2~`, `CO~2~`, `NO~3~^-^`.
- Superscripts: `e^-^`, `cm^-2^`, `10^-3^`, `K^-1^`.
- Surface facets: `Pt(111)`, `Cu(100)`, and `Miller (hkl)` stay plain text.
- Adsorbates: `*CO`, `*OH`, `*NO~3~` stay inline unless an equation is needed.
- Charges and oxidation states should be unambiguous in source text before
  export; do not rely on visual formatting alone to carry meaning.

## Equations and Symbols

- Use display math only for equations that reviewers need to inspect as
  equations.
- Keep simple reaction steps as text when they are part of a paragraph.
- Define every symbol in `paper/logic/notation.yaml` before export.
- Do not introduce new notation in generated `manuscript.md` or DOCX.

## Figures and Captions

- Figure files come from `paper/logic/figure-map.yaml` and must already have QA
  status before export.
- Figure captions belong in canonical section text when they are part of the
  draft narrative.
- The generated Figure Inventory is an export QA aid, not a journal caption
  section.

## Manual Cleanup Boundary

Manual Word cleanup is allowed only after source files are locked for that
round. Any scientific text, notation, figure identity, or claim change must go
back to `paper/` and be re-exported.
