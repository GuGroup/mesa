# Citation Inserter Output Schema

The BibTeX/Pandoc inserter produces a cited DOCX plus auditable intermediate
files.

## Files

```text
cited_section.docx
cited_section.md
used_references.bib
minimal_numeric.csl
manuscript_with_citations.docx
citation_docx_report.json
citation_docx_summary.md
```

## Report Schema

```json
{
  "schema_version": 2,
  "input_cited_section_json": "project/.../cited_section_text.json",
  "input_cited_section_jsons": ["project/.../results/cited_section_text.json", "project/.../methods/cited_section_text.json"],
  "global_citation_mode": true,
  "input_docx": "project/.../manuscript_without_citations.docx",
  "output_docx": "project/.../manuscript_with_citations.docx",
  "standalone_docx": "project/.../cited_section.docx",
  "markdown_path": "project/.../cited_section.md",
  "bib_path": "project/.../used_references.bib",
  "csl_path": "project/.../minimal_numeric.csl",
  "reference_docx": null,
  "sanitized_reference_docx": null,
  "reference_sanitized_parts": 0,
  "output_sanitized_parts": 0,
  "pandoc_path": "DEPENDENCY/tools/pandoc/bin/pandoc",
  "pandoc_command": ["pandoc", "..."],
  "citation_keys": ["Wang2015"],
  "citation_count": 1,
  "human_check_flags_ignored": true,
  "standalone_docx_validation": {
    "docx_path": "project/.../cited_section.docx",
    "has_document_xml": true,
    "xml_parts_parseable": true,
    "bad_xml_parts": [],
    "contains_raw_citation_placeholders": false,
    "contains_raw_pandoc_citation_keys": false,
    "contains_bibliography_heading": true,
    "ignorable_prefixes": ["w14"],
    "undeclared_ignorable_prefixes": [],
    "synthetic_namespace_prefixes": [],
    "document_xml_bytes": 12345
  },
  "docx_validation": {
    "docx_path": "project/.../manuscript_with_citations.docx",
    "has_document_xml": true,
    "xml_parts_parseable": true,
    "bad_xml_parts": [],
    "contains_raw_citation_placeholders": false,
    "contains_raw_pandoc_citation_keys": false,
    "contains_bibliography_heading": true,
    "ignorable_prefixes": ["w14"],
    "undeclared_ignorable_prefixes": [],
    "synthetic_namespace_prefixes": [],
    "document_xml_bytes": 12345
  },
  "manuscript_update": {
    "input_docx": "project/.../manuscript_without_citations.docx",
    "output_docx": "project/.../manuscript_with_citations.docx",
    "matched_paragraphs": 14,
    "unmatched_paragraphs": [],
    "bibliography_paragraphs_inserted": 8,
    "before_structure": {"body_paragraphs": 105, "body_tables": 0, "drawings": 8},
    "after_structure": {"body_paragraphs": 112, "body_tables": 0, "drawings": 8}
  },
  "warnings": []
}
```

The generated Markdown is the citation-bearing source of truth for Pandoc. It
contains Pandoc citation syntax such as `[@Wang2015; @Hinnemann2005]`. The DOCX
should not contain unresolved raw `@Key` citation markers after citeproc runs.
All XML and relationship parts in the generated DOCX should also be parseable;
otherwise Microsoft Word may refuse to open the file even if the ZIP container
passes a basic integrity test.
The `undeclared_ignorable_prefixes` and `synthetic_namespace_prefixes` fields
guard against a Word-specific repair condition where parseable XML still has
noncanonical compatibility prefixes such as `ns1:Ignorable` or references
undeclared prefixes in `mc:Ignorable`.

When `input_docx` is provided, `output_docx` is the skeleton-preserving
manuscript. `standalone_docx` remains the Pandoc-rendered cited section used as
an audit file and as the source of formatted bibliography text.

When multiple cited section JSON files are supplied, `input_cited_section_jsons`
records all inputs and `global_citation_mode` is `true`. Citation keys are
numbered by first appearance across the combined section order supplied on the
command line, and the generated bibliography is a single merged reference list.
