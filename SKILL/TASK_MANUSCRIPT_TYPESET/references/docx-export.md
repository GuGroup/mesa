# DOCX Export Contract

`export_docx.py` assembles a Pandoc-ready Markdown export from the canonical
paper workspace. DOCX is an exchange artifact, not the source of truth.

## Check-Only Mode

`--check-only` validates the paper workspace and writes:

- `manuscript.md`
- `docx-export-manifest.json`
- `qa/crossref-qa.txt`

It does not require Pandoc.

Recommended invocation:

```bash
mamba run -n mesa-manuscript python scripts/export_docx.py --paper /path/to/paper --out /tmp/mesa_docx --check-only
```

## Real Export Mode

Without `--check-only`, the script runs Pandoc to create `manuscript.docx`. If
Pandoc is unavailable, it exits non-zero with an installation/action message.
Use the `mesa-manuscript` environment from
`mesa/ENVIRONMENT/manuscript_tools/environment.yml` so Pandoc and the plotting
stack are available consistently.

Use `--reference-doc /path/to/reference.docx` when a Nature-family Word style
template is available. The reference document owns Word styles, fonts,
paragraph spacing, numbering, and caption appearance; generated Markdown owns
the manuscript structure and cross-reference consistency.

## Word Markdown Conventions

- Use heading levels for structure: `#` title, `##` top-level sections, and
  lower levels only for real subsections.
- Use Pandoc superscript and subscript notation for inline scientific text:
  `H~2~O`, `O~2~`, `e^-^`, `cm^-2^`, and `10^-3^`.
- Keep chemical formulas, charged species, facets, and adsorption notation in
  plain Markdown unless a later journal template requires Word equation fields.
- Put figure captions in manuscript source near their first mention when they
  are intended for the Word draft; the generated Figure Inventory is only a QA
  index.
- Do not manually edit generated `manuscript.md` or `manuscript.docx`; patch
  the canonical `paper/` sources and rerun export.

## Citation Boundary

The script may pass an existing `paper/manuscript/references.bib` to Pandoc, but
it does not search, verify, normalize, or export citations.
