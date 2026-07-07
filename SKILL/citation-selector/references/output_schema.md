# Citation Selector Output Schema

`cited_section_text.json` preserves the input section JSON and adds citation
metadata. The original paragraph `text` is not changed.

## Top-Level Additions

```json
{
  "citation_schema_version": 2,
  "citation_sources_used": [
    {
      "source_id": "P004",
      "citation_key": "Example2024",
      "source_role": "primary_project_pdf",
      "title": "Example catalyst source title",
      "authors": ["A. Author"],
      "year": "2024",
      "doi": "10.0000/example",
      "raw_reference": null,
      "collection": "strategy",
      "source_reference_numbers": []
    }
  ]
}
```

`citation_sources_used` is a compact first-use-ordered source map for selected
citations only. It is intentionally smaller than the full `citation_sources.json`.

## Paragraph Block Additions

```json
{
  "type": "paragraph",
  "text": "Original paragraph text.",
  "text_with_citation_placeholders": "Sentence. {{cite:Key1;Key2}}",
  "citation_annotations": [
    {
      "sentence_id": "S001",
      "sentence": "Sentence selected for citation.",
      "citation_keys": ["Key1"],
      "citation_source_ids": ["P004"],
      "sentence_type": "method_formalism",
      "confidence": "high",
      "reason": "Why the citation supports this sentence.",
      "needs_human_check": false
    }
  ]
}
```

Equation blocks are copied unchanged.

## Citation Decision Record

```json
{
  "sentence_id": "S001",
  "section_id": "geometry_optimization",
  "block_index": 1,
  "sentence_index": 0,
  "sentence": "The sentence being evaluated.",
  "sentence_type": "method_formalism",
  "selected_citation_keys": ["Kresse1996"],
  "selected_citation_source_ids": ["R0024"],
  "confidence": "high",
  "needs_human_check": false,
  "reason": "Concise rationale.",
  "candidate_citations": [
    {
      "citation_key": "Kresse1996",
      "source_role": "second_neighbor_reference",
      "score": 18.5,
      "title": null,
      "year": "1996",
      "evidence_snippet": "Candidate source text."
    }
  ]
}
```

`citation_decisions.json` contains all sentence-level decisions plus aggregate
counts and validation warnings.
