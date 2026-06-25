# DOCX Export Contract

`export_docx.py` assembles a Pandoc-ready Markdown export from the canonical
paper workspace. DOCX is an exchange artifact, not the source of truth.

## Check-Only Mode

`--check-only` validates the paper workspace and writes:

- `manuscript.md`
- `docx-export-manifest.json`
- `qa/crossref-qa.txt`

It does not require Pandoc and does not create a `.docx` file. Treat
`manuscript.md` as the Pandoc-ready preview of what the Word export will
consume.

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
the manuscript structure and cross-reference consistency. After Pandoc export,
the script still applies MESA defaults to the generated `.docx`: Times New
Roman, body 12 pt with 1.5 line spacing, and caption styles 11 pt with single
line spacing.

## Word Markdown Conventions

- Exported section order is Abstract, Introduction, Results and Discussion,
  Computational Methods/Methods, Conclusion, then Supplementary Information.
- Use heading levels for structure: `#` title, `##` top-level sections, and
  lower levels only for real subsections.
- Section source files should not carry a duplicate top-level self-heading; the
  exporter inserts section headings from `section-contracts.yaml` and strips an
  accidental matching `# Section` self-heading.
- Results and Discussion topic blocks must use `**Bold topic title**` as its
  own paragraph, followed by a blank line and then the body text. Use this same
  structure for figure-led or table-led discussion blocks.
- Supplementary Information blocks may use the compact inline form
  `**Section name** | body text starts here.`
- Use Pandoc superscript and subscript notation for inline scientific text:
  `H~2~O`, `O~2~`, `NO~3~^-^`, `e^-^`, `cm^-2^`, and `10^-3^`.
- Use `$...$` math spans for variables, Greek symbols, and formal expressions:
  `$E_{\\mathrm{ads}}$`, `$\\Delta G$`, `$\\Delta\\Delta G$`, `$\\delta$`.
  Do not leave raw `\delta` or `\Delta` outside math spans.
  Never wrap `$...$` math in backticks; code spans remain literal text in Word
  and block equation conversion.
- In manuscript body text, use math spans for italic variables and Markdown
  italics for accepted Latin terms such as `*ab initio*`, `*in situ*`,
  `*ex situ*`, and `*operando*`.
  Do not italicize chemical formulas, surface labels, caption labels, or
  stylistic emphasis.
- Use canonical caption paragraphs for journal captions:
  `**Figure 1 |** Caption sentence...` and
  `**Table 1 |** Caption sentence...`. The label and pipe are bold only, never
  italic. The caption paragraph must not be styled as all-italic. Caption body
  text may still italicize accepted Latin terms or variables where scientifically
  appropriate. The DOCX postprocessor maps those paragraphs to the Word Caption
  style (11 pt, 1.0 line spacing).
- Do not use bullet inventories or exported-file paths as figure captions.
- Do not manually edit generated `manuscript.md` or `manuscript.docx`; patch
  the canonical `paper/` sources and rerun export.

## Citation Boundary

The script may pass an existing `paper/manuscript/references.bib` to Pandoc, but
it does not search, verify, normalize, or export citations.
