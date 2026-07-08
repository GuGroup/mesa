---
name: resolve-manuscript-placeholders
description: Remove or replace unresolved placeholders in a manuscript DOCX using a project-provided JSON policy. Use when Codex must handle leftover tokens such as {{DATA_AVAILABILITY_TEXT}} without hardcoding project-specific placeholder behavior inside the skill.
---

# Manuscript Placeholder Polisher

## Scope

Use this skill near the end of manuscript assembly to remove or replace
unresolved `{{...}}` placeholders from a DOCX according to a JSON config.

It does not rewrite prose, references, notation, figures, or citations.

## Command

```bash
python SKILL/manuscript-placeholder-polisher/scripts/polish_placeholders.py \
  --input-docx manuscript.docx \
  --output-docx manuscript.no_placeholders.docx \
  --config placeholder_config.json
```

Config:

```json
{
  "policies": [
    {
      "placeholder": "{{DATA_AVAILABILITY_TEXT}}",
      "action": "remove_heading_and_placeholder",
      "heading": "Data availability"
    }
  ]
}
```

Supported actions:

- `remove_placeholder_paragraph`
- `remove_heading_and_placeholder`
- `replace_with_text`

See [references/config_schema.md](references/config_schema.md).
