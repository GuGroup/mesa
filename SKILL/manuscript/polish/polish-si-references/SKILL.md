---
name: polish-si-references
description: Create an independent Supporting Information reference zone in a DOCX using a project-provided citation map and SI reference config. Use when Codex must convert SI-local citations such as [2] into [S1] and insert SI references without hardcoding mappings in the skill.
---

# Manuscript SI Reference Polisher

## Scope

Use this skill after main references are stable and the DOCX contains a
Supporting Information section.

The skill:

- detects the SI citation region from a configured heading
- replaces configured SI-local citation markers
- inserts an independent SI `References` block from config

It does not infer citation mappings.

## Command

```bash
python SKILL/manuscript-si-reference-polisher/scripts/polish_si_references.py \
  --input-docx manuscript.docx \
  --output-docx manuscript.si_refs.docx \
  --config si_reference_config.json
```

See [references/config_schema.md](references/config_schema.md).
