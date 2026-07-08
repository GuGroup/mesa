---
name: polish-manuscript-references
description: Normalize main manuscript reference paragraphs in a DOCX from a project-provided reference config. Use when Codex must standardize existing numeric references without hardcoding bibliography records in the skill and without renumbering in-text citations.
---

# Manuscript Reference Polisher

## Scope

Use this skill to replace main numeric reference paragraphs, such as `[1] ...`,
with normalized strings supplied by a JSON config.

It does not search for references, infer missing metadata, renumber citations,
or modify SI references.

## Command

```bash
python SKILL/manuscript-reference-polisher/scripts/polish_references.py \
  --input-docx manuscript.docx \
  --output-docx manuscript.refs.docx \
  --config reference_config.json
```

See [references/config_schema.md](references/config_schema.md).
