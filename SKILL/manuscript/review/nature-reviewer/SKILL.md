---
name: nature-reviewer
description: >-
  Simulate a Nature-style reviewer assessment from the referee perspective rather than
  an author rebuttal. Use when the user wants a pre-submission review, reviewer report,
  peer-review style critique, novelty/significance/technical soundness assessment,
  reviewer-style manuscript evaluation, mock peer review, pre-submission critique, or
  Nature reviewer report. Return 3 reviewer reports plus a cross-review synthesis,
  grounded only in the local Nature reviewer source basis.
version: 0.1.0
status: Draft
---

# Nature Reviewer Assessment Skill

Use this skill to simulate a `Nature`-style reviewer assessment package from the referee side.

This skill is for reviewer-style manuscript evaluation, not for drafting the authors' response. If the user wants rebuttal writing, route to `nature-response`.

## Default stance

- Ground the review only in the local source basis plus manuscript facts supplied by the user.
- Evaluate the manuscript against source-grounded axes: `originality`, `scientific importance`, `interdisciplinary readership`, `technical soundness`, and `readability for nonspecialists`.
- Return exactly `3 reviewer reports + 1 cross-review synthesis` unless the user explicitly asks for another structure.
- The three reviewers may differ only in `emphasis`; do not invent reviewer identities, specialties, institutions, or biographies.
- Identify who would be interested in the results and why.
- Identify technical failings that must be addressed before the authors' case is established.
- Distinguish clearly between what is supported, what is weak, and what is not assessable from the provided material.
- Do not claim the editor's final decision or certainty about fit to `Nature`.

## Accepted inputs

The skill may receive:

- full manuscript draft
- abstract, summary paragraph, or cover-summary style text
- introduction, results, discussion, or methods excerpts
- figure legends, selected figures, or result notes
- author notes describing the claimed contribution
- pre-submission positioning notes

If the provided material is partial, perform a bounded review and mark the assessment boundary explicitly.

## Workflow

1. Identify the input scope and whether the job is a reviewer-style assessment rather than rebuttal drafting.
2. Extract a shared manuscript fact base: main claim, visible evidence, claimed significance, likely readership, and visible limitations.
3. Check readiness and label missing evidence or missing sections instead of inventing them.
4. Assess the manuscript using the source-grounded axes.
5. Generate `Reviewer 1`, `Reviewer 2`, and `Reviewer 3` using shared facts but different emphasis.
6. Generate a `Cross-review synthesis` that captures consensus and weighting differences.
7. Run QA for groundedness, coverage, role boundaries, and non-invention.

## Output format

Unless the user asks for another format, return:

```text
Review setup
- Input scope:
- Assessment boundary:
- Shared manuscript claim summary:
- Visible evidence base:
- Missing materials affecting confidence:

Reviewer 1
- Overall assessment:
- Who would be interested in the results, and why:
- Major strengths:
- Major concerns:
- Technical failings that need to be addressed before the case is established:
- Assessment against Nature-style criteria:
- Recommendation posture:

Reviewer 2
[Same structure]

Reviewer 3
[Same structure]

Cross-review synthesis
- Consensus strengths:
- Consensus technical risks:
- Where emphasis differs across reviewers:
- Broad-interest / significance readout:
- Most important issues to resolve before a strong Nature-style case is established:

Risk / unsupported claims
- [specific unsupported or not-assessable items]
```

## Red lines

- Do not invent reviewer identities, specialty roles, or selection history.
- Do not use private peer-review claims unless the user provides them.
- Do not present a likely editorial decision as fact.
- Do not write the authors' point-by-point response; route that to `nature-response`.
