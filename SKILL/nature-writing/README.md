# `nature-writing` skill

`nature-writing` drafts, restructures, or plans Nature-style manuscript sections from author-provided claims, results, figures, notes, or draft material.

## Capabilities

- Draft titles, abstracts, introductions, related work, methods, experiments, discussion, conclusions, and manuscript outlines.
- Rebuild an argument around claim, evidence, boundary, and contribution.
- Surface missing evidence before drafting.
- Apply Nature-family or generic journal framing when requested.
- Use on-demand examples and section references only when the task needs them.

## Structure

```text
nature-writing/
  SKILL.md
  manifest.yaml
  static/core/
  static/fragments/
  references/
```

## Default Workflow

1. Detect paper type, section, source language, and journal target.
2. Load only the matching fragments.
3. Write the one-sentence argument before drafting prose.
4. Draft from evidence and boundary, not from unsupported novelty claims.
5. Return assumptions, missing inputs, and rejection-risk notes where relevant.

## Status

Draft. The workflow is useful for section drafting and argument repair, but author review is required before manuscript use.
