# Reference Config Schema

## Default configuration

```json
{
  "reference_style": "acs_numeric",
  "references": {
    "1": "Author, A. Title. Journal Year, Volume, pages. DOI: ...",
    "2": "..."
  },
  "main_references_heading": "References",
  "stop_at_heading": "Supporting Information",
  "main_references_heading_occurrence": 1,
  "stop_at_heading_occurrence": 1,
  "case_sensitive_headings": true,
  "reference_label_pattern": "^\\[(?P<number>\\d+)\\]\\s*",
  "replacement_template": "[{number}] {reference}",
  "require_all_configured_references": true
}
```

## Fields

- `references` — required non-empty mapping of positive integer labels to final
  plain-text bibliography records.
- `reference_style` — optional provenance metadata recorded in the report; it
  does not change formatting behavior.
- `main_references_heading` — start heading; defaults to `References`.
- `stop_at_heading` — first boundary after the start heading; defaults to
  `Supporting Information`. Set to `null` to scope through the document end.
- `main_references_heading_occurrence` — 1-based occurrence of the start
  heading; defaults to `1`.
- `stop_at_heading_occurrence` — 1-based occurrence of the stop heading after
  the selected start; defaults to `1`.
- `case_sensitive_headings` — defaults to `true`.
- `reference_label_pattern` — Python regular expression anchored at the start
  of a reference paragraph. It must contain a named `number` group matching
  positive integer labels.
- `replacement_template` — supports `{number}` and `{reference}`; defaults to
  `[{number}] {reference}`.
- `require_all_configured_references` — when `true`, fail if a configured record
  is absent from the scoped bibliography. Set to `false` when the config is an
  intentional superset of references used in the document.

## Alternative numbering

For labels such as `1. Reference text`:

```json
{
  "references": {
    "1": "First normalized record.",
    "2": "Second normalized record."
  },
  "reference_label_pattern": "^(?P<number>\\d+)\\.\\s*",
  "replacement_template": "{number}. {reference}",
  "stop_at_heading": null
}
```

The skill replaces textual contents of matched reference paragraphs. It
preserves paragraph properties and all content outside those paragraphs, but it
does not preserve intentional mixed inline styling within an old bibliography
record.
