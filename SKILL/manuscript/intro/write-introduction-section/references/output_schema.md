# Introduction Section Writer Output Schema

`introduction_section_text.json` contains:

- `schema_version`
- `strategy_id`
- `source_digest`
- `source_manuscript_docx`
- `section_source`
- `target_placeholders`
- `sections`
- `missing_details`
- `validation`

Schema version 1 writes one Introduction section:

```json
{
  "section_id": "introduction",
  "title": "",
  "small_title": "",
  "render_title": false,
  "text": "Paragraph one.\n\nParagraph two.",
  "content_blocks": [
    {
      "type": "paragraph",
      "text": "Academic Introduction prose without citations."
    }
  ]
}
```

The intended DOCX placeholder is:

```json
{
  "text": "{{INTRODUCTION_TEXT}}"
}
```

The writer output should not contain citation placeholders or visible reference
numbers. Run `citation-selector` after writing to add citation annotations.
