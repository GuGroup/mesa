---
name: insert-citations
description: Create a BibTeX/Pandoc cited DOCX from citation-selector output. Use after citation-selector when Codex must convert cited_section_text.json placeholders such as {{cite:Wang2015;Hinnemann2005}} into Pandoc citeproc citations, generate used_references.bib, apply a local numeric CSL style, and save a cited DOCX with bibliography without changing citation choices.
---

# Citation Inserter

## Scope

Use this skill after `citation-selector` has produced `cited_section_text.json`.

The inserter converts selected citation placeholders into Pandoc citation
syntax, writes a BibTeX file for the used references, applies a local numeric
CSL style, and generates a DOCX with formatted citations and bibliography. When
`--input-docx` is provided, it also applies the numeric citations directly to
the existing manuscript DOCX package so the manuscript skeleton is preserved.
When multiple `--cited-section-json` paths are provided, it combines those
section citation layers, assigns one first-appearance citation numbering order,
and writes a single merged References block.

It does not select citations, search references, call an LLM, use live Zotero
Word fields, or change selector decisions. Human-check flags are ignored for
rendering in this version.

Default output:

```text
project/<project>/strategy_execution/<strategy_id>_methods/citations/pandoc/
  cited_section.docx
  cited_section.md
  used_references.bib
  minimal_numeric.csl
  manuscript_with_citations.docx      # when --input-docx/--output-docx is used
  citation_docx_report.json
  citation_docx_summary.md
```

## Workflow

Run:

```bash
python SKILL/citation-inserter/scripts/insert_citations.py \
  --cited-section-json project/<project>/strategy_execution/<strategy_id>_methods/citations/cited_section_text.json
```

Useful options:

```bash
--reference-docx project/.../manuscript_without_citations.docx
--output-docx project/.../methods_with_citations.docx
--outdir project/.../citations/pandoc
--title "Methods"
```

Skeleton-preserving manuscript update:

```bash
python SKILL/citation-inserter/scripts/insert_citations.py \
  --cited-section-json project/<project>/strategy_execution/<strategy_id>_methods/citations/cited_section_text.json \
  --input-docx project/<project>/manuscript/S1/S1_manuscript_with_figures_and_methods.docx \
  --output-docx project/<project>/manuscript/S1/S1_manuscript_with_citations.docx
```

Global manuscript citation update:

```bash
python SKILL/citation-inserter/scripts/insert_citations.py \
  --cited-section-json \
    project/<project>/strategy_execution/<strategy_id>_results/citations/cited_section_text.json \
    project/<project>/strategy_execution/<strategy_id>_methods/citations/cited_section_text.json \
  --input-docx project/<project>/manuscript/S1/S1_manuscript_with_uncited_sections.docx \
  --output-docx project/<project>/manuscript/S1/S1_manuscript_with_global_citations.docx
```

Pandoc is required. The script first checks `PATH`, then the repo-local
`DEPENDENCY/tools/pandoc/bin/pandoc`.

## Rendering Rules

- Preserve selector decisions; do not add, remove, or reorder citation keys
  inside a placeholder.
- Convert `{{cite:Key1;Key2}}` to Pandoc syntax `[@Key1; @Key2]`.
- Build `used_references.bib` only from top-level `citation_sources_used`.
- Use the local generated `minimal_numeric.csl` to create numeric citations and
  a bibliography in DOCX.
- For multiple cited sections, merge `citation_sources_used`, preserve each
  section's placeholder decisions, and number citations in first appearance
  order across the combined manuscript section order supplied on the command
  line.
- In `--input-docx` mode, keep the Pandoc DOCX as an audit/intermediate file,
  but edit the existing manuscript package in place by replacing only matched
  manuscript paragraph text and the `{{REFERENCES_TEXT}}` paragraph. If the
  placeholder has already been replaced, stale numeric bibliography paragraphs
  directly under the `References` heading are removed before inserting the
  merged bibliography. Do not rebuild the whole manuscript through Pandoc.
- If `--reference-docx` is provided, write a sanitized copy before passing it to
  Pandoc so known unbound XML namespace prefixes from earlier manuscript edits do
  not propagate into the cited DOCX.
- Render all placeholders, including citations whose selector decision had
  `needs_human_check: true`.
- Preserve equations through Pandoc Markdown math conversion.
- Validate every DOCX XML part, not only the ZIP container. Record missing
  citation keys, unresolved raw citation keys, raw placeholders, and XML parse
  failures as warnings.
- Normalize Word compatibility namespaces before writing DOCX packages. In
  particular, keep `mc:Ignorable` synchronized with declared prefixes such as
  `w14` so Microsoft Word does not need to repair otherwise parseable XML.

Read [references/output_schema.md](references/output_schema.md) when consuming
or revising the output contract.
