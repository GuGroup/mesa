---
name: mesa-manuscript-typeset
description: Build Nature-family Word/DOCX export artifacts from a canonical MESA paper workspace without changing manuscript source files.
---

# MESA Manuscript Word Export

Use this skill after the manuscript loop has produced a canonical `paper/`
workspace. The source of truth is still Markdown, YAML, BibTeX, and figure files
under `paper/`; generated Markdown and DOCX files are disposable export
artifacts.

## Inputs

Required paper inputs:

- `paper/manuscript/outline.md`
- `paper/manuscript/section-contracts.yaml`
- `paper/manuscript/sections/*.md`
- `paper/manuscript/si/*.md`
- `paper/manuscript/references.bib`
- `paper/logic/claim-matrix.yaml`
- `paper/logic/figure-map.yaml`
- `paper/logic/notation.yaml`
- figure source, exported, and QA files named by `figure-map.yaml`

## Command

Check and assemble DOCX Markdown without requiring Pandoc:

```bash
python3 scripts/export_docx.py --paper /path/to/paper --out /tmp/mesa_docx --check-only
```

Export DOCX when Pandoc is installed:

```bash
python3 scripts/export_docx.py --paper /path/to/paper --out /tmp/mesa_docx
```

Apply a Word style template when one is provided:

```bash
python3 scripts/export_docx.py --paper /path/to/paper --out /tmp/mesa_docx --reference-doc /path/to/reference.docx
```

## Boundaries

- Do not run calculations, literature search, citation verification, or
  reference export.
- Do not edit `paper/` source files.
- Do not treat successful export as scientific approval; it only proves the
  canonical workspace can be assembled and cross-references are internally
  consistent.

## Routing

- DOCX export: load `references/docx-export.md`.
- Word formatting, section styles, equations, and subscript/superscript
  conventions: load `references/word-style.md`.
- Cross-reference and stale-artifact checks: load `references/crossref-qa.md`.
