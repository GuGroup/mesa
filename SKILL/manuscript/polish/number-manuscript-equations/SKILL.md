---
name: number-manuscript-equations
description: Add configured equation numbers to manuscript DOCX equations, including one number for a multi-line equation group. Use when Codex must number displayed equations near the end of manuscript polishing without hardcoding project-specific equation text.
---

# Manuscript Equation Number Polisher

## Scope

Use this skill near the end of manuscript assembly to add equation numbers to
displayed equations in a DOCX.

The skill is config-driven. By default it automatically discovers displayed
OMML equation paragraphs, numbers them sequentially, and replaces each numbered
equation group with a borderless three-column table:

```text
empty side column | centered equation/group | right-aligned number
```

Consecutive displayed equation paragraphs are treated as one equation group and
receive one number.

Manual group matching is still available when a manuscript needs explicit
exceptions.

It does not rewrite prose, convert equations, or renumber citations.

## Command

```bash
python SKILL/manuscript-equation-number-polisher/scripts/number_equations.py \
  --input-docx manuscript.docx \
  --output-docx manuscript.equation_numbered.docx \
  --config equation_number_config.json
```

See [references/config_schema.md](references/config_schema.md).
