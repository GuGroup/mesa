# Word Style and Notation Guide

This guide controls Word/DOCX export expectations for Nature-family manuscript
drafts. It is a formatting contract for export artifacts, not permission to edit
canonical `paper/` sources outside the manuscript loop.

## Style Source of Truth

- The canonical text remains in `paper/manuscript/sections/*.md`.
- The Word style source is an optional `--reference-doc` file passed to
  `export_docx.py`.
- After Pandoc export, `export_docx.py` applies MESA default Word styles to the
  generated `.docx`: Times New Roman throughout, body text 12 pt with 1.5 line
  spacing, and caption styles 11 pt with single line spacing.
- The reference document should define styles for Title, Heading 1, Heading 2,
  Body Text, Figure Caption, Table Caption, References, and Normal.
- If no reference document is available, the export still applies the MESA
  default Word styles, but it is not a final journal-specific layout.
- `--check-only` creates `manuscript.md`, not a `.docx`. A real Word document
  requires running `export_docx.py` without `--check-only` and with Pandoc
  available in the execution environment.

## Section Formatting

- Export order is Abstract, Introduction, Results and Discussion,
  Computational Methods/Methods, Conclusion, and Supplementary Information.
- Section source files should normally omit their own top-level heading because
  the exporter inserts section headings from `section-contracts.yaml`. If a
  section file starts with `# Results`, `# Methods`, or the matching section
  name, the exporter strips that self-heading from the disposable export.
- Use semantic Markdown headings for real subsections only. Do not emulate
  spacing with blank paragraphs.
- Keep Results before Methods only when the manuscript loop section contracts
  require that order.
- Put supplementary sections under manuscript source files that are marked as
  SI in `section-contracts.yaml`.
- Do not manually renumber headings in Markdown; Word styles and Pandoc handle
  numbering when the reference document enables it.
- Results and Discussion topic blocks, including figure-led discussion blocks,
  must use `**Bold topic title**` as its own paragraph, followed by a blank
  line and then the body text. Do not use the pipe form in Results and
  Discussion.
- Supplementary Information blocks may use the compact inline form
  `**Section name** | body text starts here.`

## Word Defaults

- Font family: Times New Roman for Normal/body, headings, captions, and symbol
  text where Word allows the font to be set.
- Body/Normal: 12 pt, 1.5 line spacing.
- Figure Caption, Table Caption, and Caption styles: 11 pt, 1.0 line spacing.
- Use Word styles rather than manual spacing. Do not add blank lines to mimic
  1.5 spacing or caption spacing.

## Inline Scientific Notation

Use Pandoc Markdown notation so DOCX output can map to native Word
super/subscript runs:

- Subscripts: `H~2~O`, `O~2~`, `CO~2~`, `NO~3~^-^`, `NH~4~^+^`.
- Superscripts: `e^-^`, `cm^-2^`, `10^-3^`, `K^-1^`, `mA cm^-2^`.
- Surface facets: `Pt(111)`, `Cu(100)`, and `Miller (hkl)` stay plain text.
- Adsorbates: `*CO`, `*OH`, `*NO~3~` stay inline unless an equation is needed.
- Charges and oxidation states should be explicit: `Fe^3+^`, `NO~3~^-^`,
  `OH^-^`. Do not rely on visual formatting alone to carry meaning.
- Variables and formal symbols should be italicized through math where possible:
  `$E_{\\mathrm{ads}}$`, `$\\Delta G$`, `$\\Delta\\Delta G$`, `$\\delta$`.
  Use plain text for chemical species and surfaces.
- Accepted Latin terms may use Markdown italics, e.g. `*ab initio*`,
  `*in situ*`, `*ex situ*`, and `*operando*`.
- Do not use Markdown italics for chemical formulas, surface labels, caption
  labels, or stylistic emphasis.
- Do not leave raw TeX commands such as `\delta`, `\Delta`, `\mathrm`, or
  `_{ads}` outside `$...$` math spans; they will appear literally in Word.
- Do not wrap `$...$` math in backticks. Backticked math is a code span, so
  Pandoc exports it as literal text rather than Word equation markup.
- Use Unicode Greek letters only for prose-level symbols that do not need math
  layout, e.g. `ΔΔG` in a figure caption. Prefer math spans for equations or
  variable definitions.

## Equations and Symbols

- Use inline math for short variables and expressions: `$E_{\\mathrm{ads}}$`,
  `$\\Delta\\Delta G_i(*X)$`, and `$U_{\\mathrm{RHE}}$`.
- Use display math only for equations that reviewers need to inspect as
  equations.
- Keep simple reaction steps as text when they are part of a paragraph.
- Define every symbol in `paper/logic/notation.yaml` before export.
- Do not introduce new notation in generated `manuscript.md` or DOCX.

## Figures and Captions

- Figure files come from `paper/logic/figure-map.yaml` and must already have QA
  status before export.
- Figure captions must be canonical caption paragraphs:
  `**Figure 1 |** Caption sentence...`. Table captions use
  `**Table 1 |** Caption sentence...`.
- The `Figure N |` or `Table N |` label is bold only, never italic. Caption
  body text may italicize accepted Latin terms or variables inside math spans
  only. The caption paragraph/style itself must remain roman, not all-italic.
- Caption paragraphs are postprocessed to the Word Caption style: Times New
  Roman, 11 pt, 1.0 line spacing.
- Do not include exported-file paths in caption text. Exported paths belong in
  cross-reference QA, not the manuscript body.

## Manual Cleanup Boundary

Manual Word cleanup is allowed only after source files are locked for that
round. Any scientific text, notation, figure identity, or claim change must go
back to `paper/` and be re-exported.
