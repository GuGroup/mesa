# Section JSON Schema

The inserter accepts a JSON object with:

- `sections`: required list of section objects
- `strategy_id`: optional value used only for the insertion report
- `schema_version`: optional value used only for the insertion report
- `missing_details`: optional list, not inserted into the DOCX body by default

Each section object supports:

- `section_id`: stable identifier
- `title`: manuscript subsection title
- `small_title`: optional DOCX intro title override used before `title`
- `render_title`: optional boolean, defaults to `true`; set to `false` to insert
  the first paragraph as body text without a bold title prefix
- `paragraph_style`: optional direct paragraph formatting for inserted paragraph
  text, supporting `bold`, `italic`, `font_size_pt`, and `align`
- `text`: optional compatibility body text
- `content_blocks`: preferred ordered manuscript content
- `equations`: optional legacy equation list used only when `content_blocks` is absent

`content_blocks` preserves manuscript order. Supported block forms:

```json
{"type": "paragraph", "text": "Academic Methods prose."}
```

```json
{
  "type": "equation",
  "label": "Alkaline hydrogen reference",
  "latex": "\\mathrm{H_2O(l)} + e^- \\rightleftharpoons \\frac{1}{2}\\mathrm{H_2(g)} + \\mathrm{OH^-(aq)}",
  "explanation": "This identity was used to assemble alkaline hydrogen-evolution free energies."
}
```

The DOCX v1.5 output converts LaTeX equations to Word-native OMML equation
objects by default with Pandoc. Equation `label` values are not rendered into
the DOCX manuscript body. Each logical equation block is rendered with one blank
paragraph before and after the equation block. Use `--equation-mode text` only when
plain centered LaTeX text is explicitly desired.

When `small_title` is present, the inserted bold intro title uses
`small_title`; otherwise it uses `title`. This lets section writers keep a
large manuscript heading such as "Results and Discussion" while inserting a
short subsection lead such as "Ni-S Edge Descriptor Balance".

When `render_title` is `false`, the inserter ignores the title for rendering
and inserts the first paragraph as ordinary body text. Use this for sections
such as Introduction when the skeleton already contains the visible section
heading and the section JSON should replace only `{{INTRODUCTION_TEXT}}`.

Use `paragraph_style` for placeholders that need direct formatting independent
of the placeholder style. For example, a manuscript title can set:

```json
"paragraph_style": {"bold": true, "font_size_pt": 14}
```

`--distribute-figures` is an insertion-time option, not a section JSON field. It
detects existing main-text captions that start with `Fig. N |`, moves the
associated drawing and caption block after the first inserted paragraph that
mentions `Fig. N`, and records moved/unmoved figures in the insertion report.
It intentionally does not move `Fig. S...` Supporting Information figures.

For DOCX output, a LaTeX `aligned` environment is split by row. Each row
separated by `\\` is rendered as its own Word equation object, while the JSON
still retains one logical equation block. Blank paragraph spacing is applied
around the split group, not between every split row.
