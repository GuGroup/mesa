---
name: polish-manuscript-notation
description: Apply configured scientific notation formatting to manuscript DOCX text. Use when Codex must convert plain tokens such as MoS2, Delta G_H, or project-specific descriptors into DOCX subscript/superscript runs from a JSON ruleset, without hardcoding chemistry terms in the skill.
---

# Manuscript Notation Polisher

## Scope

Use this skill for final mechanical notation cleanup in DOCX manuscripts.

The skill reads notation rules from JSON and applies them to paragraph text
while preserving paragraph order and existing paragraph/run style as much as
possible.

It does not rewrite prose, references, placeholders, or citations.

## Command

```bash
python SKILL/manuscript-notation-polisher/scripts/polish_notation.py \
  --input-docx manuscript.docx \
  --output-docx manuscript.notation.docx \
  --config notation_config.json
```

See [references/config_schema.md](references/config_schema.md).
