# Results Section Writer Output Schema

`results_section_text.json` contains:

- `schema_version`
- `strategy_id`
- `source_digest`
- `source_manuscript_docx`
- `section_source`
- `target_placeholders`
- `sections`
- `missing_details`
- `validation`

Schema version 2 writes 2-4 focused local subsections:

```json
{
  "section_id": "results_free_energy_profiles",
  "title": "Results and Discussion",
  "small_title": "Free-Energy Profiles",
  "text": "Compatibility field from paragraph blocks.",
  "content_blocks": [
    {
      "type": "paragraph",
      "text": "Academic Results and Discussion prose with figure references."
    }
  ]
}
```

All sections are inserted under the manuscript's existing "Results and
Discussion" heading. `small_title` should be specific to the local paragraphs,
not a generic title for the whole section.

Unavailable or limited evidence should affect claim strength only. Version 2
outputs should not contain standalone limitation, scope, missing-evidence, or
future-work paragraphs, and should not enumerate analyses that were not
performed.

Outputs should also avoid meta-interpretation disclaimer sentences such as
"the agreement should be interpreted..." or "the result should be understood..."
and should instead state the supported thermodynamic conclusion directly.

The intended DOCX placeholders are:

```json
{
  "small_title": "{{RESULTS_AND_DISCUSSIONS_SMALL_TITLE}}",
  "text": "{{RESULTS_AND_DISCUSSIONS_TEXT}}"
}
```

`manuscript_context.json` is a compact preprocessing artifact extracted from
the DOCX. It may include section headings, target placeholder presence, Methods
text, figure-caption paragraphs, and existing skeleton placeholders. The LLM
must use it only for manuscript continuity and target awareness; the factual
source of Results claims remains `results_writer_digest.json`.
