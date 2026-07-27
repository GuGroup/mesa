---
name: polish-manuscript-references
description: Normalize a scoped numeric bibliography in a DOCX from a project-provided JSON config while preserving Word equations, figures, package parts, and content outside the reference section. Use when Codex must replace existing numbered reference paragraphs, support split Word runs or configurable numeric-label syntax, and avoid renumbering in-text citations or modifying Supporting Information references.
---

For MESA end-to-end use, read `SKILL/manuscript/workflow.md` before applying this skill.

# Manuscript Reference Polisher

## Scope

Replace numeric reference paragraphs, such as `[1] ...`, only between configured
start and stop headings. Supply all bibliography text through JSON; keep this
skill independent of catalyst, discipline, journal, and metadata provider.

The script:

- matches headings and labels across split Word runs;
- changes only text nodes in matched reference paragraphs;
- leaves non-document package parts byte-identical;
- preserves OMML equation and drawing counts;
- validates the temporary DOCX before atomically promoting the output;
- fails closed on missing scope headings, duplicate labels, unconfigured
  references, or absent configured references.

It does not search for sources, infer metadata, format records automatically,
renumber citations, or edit SI references.

## Command

```bash
python3 SKILL/manuscript/polish/polish-manuscript-references/scripts/polish_references.py \
  --input-docx manuscript.docx \
  --output-docx manuscript.refs.docx \
  --config reference_config.json
```

Use distinct input and output paths. The script writes a JSON report beside the
output by default and returns exit code `2` without publishing a new output when
validation fails.

Read [references/config_schema.md](references/config_schema.md) when the
manuscript uses non-default headings, numbering syntax, or scope occurrences.

## Required checks

Before accepting the output, confirm in the report:

- `validation.ok` is `true`;
- `output_written` is `true`;
- `non_document_parts_unchanged` is `true`;
- untouched paragraphs and target paragraph structure are unchanged;
- OMML equation and drawing counts are unchanged;
- normalized reference numbers match the intended bibliography.
