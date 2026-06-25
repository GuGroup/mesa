# `nature-reviewer` skill

`nature-reviewer` simulates a conservative Nature-style pre-submission reviewer assessment from the referee perspective. It is not for writing the authors' rebuttal; route rebuttal work to `nature-response`.

## Capabilities

- Read manuscript drafts, abstracts, selected sections, figures, legends, and author notes.
- Evaluate originality, scientific importance, interdisciplinary readership, technical soundness, and readability for nonspecialists.
- Generate three reviewer reports with different emphasis but the same fact base.
- Produce a cross-review synthesis.
- Mark unsupported claims and not-assessable points explicitly.

## Rules

- Ground the review only in the local reviewer source basis and user-provided manuscript facts.
- Do not invent reviewer identities, institutions, specialties, or hidden knowledge.
- Identify who would be interested in the results and why.
- Identify technical failings that must be addressed before the authors' case is established.
- Do not claim the editor's final decision.

## Structure

```text
nature-reviewer/
  SKILL.md
  references/
```

## Status

Draft. The first version is source-defined and structured, but not yet validated against a broad anonymous manuscript-review example set.
