# DOCX Export Contract

`export_docx.py` assembles a Pandoc-ready Markdown export from the same canonical
paper workspace used by the Typst builder. DOCX is an exchange artifact, not the
source of truth.

## Check-Only Mode

`--check-only` validates the paper workspace and writes:

- `manuscript.md`
- `docx-export-manifest.json`
- `qa/crossref-qa.txt`

It does not require Pandoc.

## Real Export Mode

Without `--check-only`, the script runs Pandoc to create `manuscript.docx`. If
Pandoc is unavailable, it exits non-zero with an installation/action message.

## Citation Boundary

The script may pass an existing `paper/manuscript/references.bib` to Pandoc, but
it does not search, verify, normalize, or export citations.
