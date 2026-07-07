# Methods-To-SI Move Report Schema

```json
{
  "schema_version": 1,
  "input_docx": "project/.../input.docx",
  "output_docx": "project/.../output.docx",
  "mode": "replace-geometry-optimization-block",
  "removed_paragraphs": ["Relaxations used ..."],
  "replacement_paragraph": "Geometry optimization ...",
  "validation": {
    "ok": true,
    "removed_details_present_in_si": true,
    "method_detail_removed": true
  },
  "warnings": []
}
```
