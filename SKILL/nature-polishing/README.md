# `nature-polishing` skill

`nature-polishing` polishes, restructures, or translates academic prose toward concise Nature-style English.

## Capabilities

- Polish manuscript paragraphs and sections.
- Improve title, abstract, introduction, results, discussion, conclusion, and methods prose.
- Repair claim-evidence-boundary problems before sentence-level polishing.
- Apply Nature-family or Nature Communications style guidance when requested.
- Diagnose LaTeX layout and typesetting problems when the task is layout-oriented rather than prose-oriented.

## Structure

```text
nature-polishing/
  SKILL.md
  manifest.yaml
  static/core/
  static/fragments/
  references/
```

## Default Workflow

1. Detect paper type, section, source language, and target journal.
2. Load only the matching fragments.
3. Fix structural problems before sentence polish.
4. Preserve evidence boundaries and flag missing content instead of inventing it.
5. Return polished text plus short notes on unresolved risks.

## Status

Stable for local manuscript polishing and revision workflows.
