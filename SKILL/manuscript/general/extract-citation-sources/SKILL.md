---
name: extract-citation-sources
description: Build a controlled citation library from local project PDFs and their explicit reference lists. Use before manuscript citation insertion when Codex needs citation_sources.json and library.bib without additive literature search.
---

For MESA end-to-end use, read `SKILL/manuscript/workflow.md` before applying this skill.

# Citation Source Extractor

## Scope

Use this skill when a manuscript-writing workflow needs a bounded citation
source universe. The skill reads local project PDFs and extracts:

1. primary papers: PDFs directly stored in the project literature folders
2. second-neighbor references: bibliography entries explicitly cited by those
   primary PDFs
3. citation contexts: sentences in a primary paper where a parsed
   second-neighbor reference number is cited

It does not search the web, recommend citation placement, rewrite manuscript
text, or decide whether a citation supports a specific sentence. Those steps
belong to later citation-selection or citation-insertion skills.

Default output:

```text
project/<project>/references/
  citation_sources.json
  library.bib
  citation_source_summary.md
```

## Workflow

Run:

```bash
python SKILL/manuscript/general/extract-citation-sources/scripts/extract_citation_sources.py \
  --project project/<project>
```

Defaults:

```text
primary PDF roots:
  project/<project>/strategy_generation/papers
  project/<project>/strategy_generation/experimental_data

metadata context, if present:
  project/<project>/strategy_generation/paper_search/search_report.md

output directory:
  project/<project>/references
```

Override paths when needed:

```bash
--pdf-root path/to/papers
--pdf-root path/to/more_papers
--search-report path/to/search_report.md
--outdir path/to/references
```

## Extraction Rules

- Use only local PDFs and references printed inside those PDFs.
- Do not add papers from search reports unless a local PDF is present and can be
  matched to that report entry.
- Do not perform additive web search, DOI lookup, CrossRef lookup, or Zotero
  lookup in this skill.
- Preserve uncertainty in `warnings`; do not invent titles, authors, DOI values,
  or publication years.
- Keep raw reference strings for second-neighbor references because reference
  styles vary across publishers.
- For numbered reference lists, preserve the source-paper reference number and
  citation-context sentences when they can be found in the primary-paper body.
- Use raw PDF text order for citation-context sentences, while using layout text
  for reference-list parsing.
- Two-column reference lists must be split on numbered markers even when
  multiple references appear on one extracted text line.
- Use `library.bib` as a convenience export, not as a perfect bibliographic
  database. Later Zotero/BibTeX cleaning may improve these entries.

Read [references/citation_source_schema.md](references/citation_source_schema.md)
when consuming or revising the JSON contract.
