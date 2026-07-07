# AKC-Title Output Schema

The writer emits a combined file:

```json
{
  "schema_version": 1,
  "strategy_id": "S1",
  "source_manuscript_docx": "project/.../manuscript.docx",
  "section_source": "llm",
  "title": {"text": "Manuscript title"},
  "abstract": {"text": "One paragraph."},
  "keywords": ["keyword one", "keyword two"],
  "conclusion": {"paragraphs": ["Paragraph 1.", "Paragraph 2."]},
  "section_json_paths": {
    "title": "title_section_text.json",
    "abstract": "abstract_section_text.json",
    "keywords": "keywords_section_text.json",
    "conclusion": "conclusion_section_text.json"
  },
  "missing_details": [],
  "validation": {"ok": true}
}
```

It also emits four `manuscript-section-docx-inserter` compatible files:

- `title_section_text.json`, targeting `{{TITLE}}`
- `abstract_section_text.json`, targeting `{{ABSTRACT_TEXT}}`
- `keywords_section_text.json`, targeting `{{KEYWORDS_TEXT}}`
- `conclusion_section_text.json`, targeting `{{CONCLUSION_TEXT}}`

Each section uses `render_title: false` because the manuscript skeleton already
contains the major heading or placeholder context.

The keywords section renders as one paragraph with semicolon-separated phrases.
