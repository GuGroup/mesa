# Supporting Information Output Schema

The writer emits one combined file and five inserter-ready section JSON files.

Combined file:

```json
{
  "schema_version": 1,
  "strategy_id": "S1",
  "source_manuscript_docx": "project/.../manuscript.docx",
  "si_large_content_title": "1. Supplementary figures",
  "si_large_content_text": "Short SI figure overview.",
  "si_small_content_title": "1.1. Optimized local geometries",
  "si_small_content_text": "Short local-geometry bridge text.",
  "dft_calculation_details": {
    "paragraphs": ["Geometry optimization ..."]
  },
  "section_json_paths": {
    "si_large_content_title": "si_large_content_title_section_text.json",
    "si_large_content_text": "si_large_content_text_section_text.json",
    "si_small_content_title": "si_small_content_title_section_text.json",
    "si_small_content_text": "si_small_content_text_section_text.json",
    "dft_calculation_details": "dft_calculation_details_section_text.json"
  },
  "validation": {"ok": true}
}
```

All section JSON files use `render_title: false` and target exactly one
placeholder. Inserted public text uses at most two decimal places for
non-integer values; extracted source metadata retains its original precision.
