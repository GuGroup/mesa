# Section Writing Policy

Section writing expands locked logic into prose. It is not a discovery stage.

## Preconditions

Before writing any prose chunk:

- `paper/logic/claim-matrix.yaml` has no unsupported main claim for the chunk.
- `paper/logic/figure-map.yaml` has no blocked required figure for the chunk.
- `paper/state/reviewer-issues.yaml` has no open `BLOCKER` or unresolved major
  issue for the chunk.
- `paper/manuscript/section-contracts.yaml` marks the section
  `ready-to-draft`.
- Required source files exist under `paper/inputs/`, `paper/logic/`, or
  `paper/figures/`.

## Writing Order

Write sections in this order:

1. Results
2. Methods
3. SI
4. Discussion
5. Introduction
6. Abstract
7. Title

Before drafting a section, load `references/skill-routing.md` and use
`SKILL/nature-writing` with target journal set to `nature` for Nature-family
argument structure. After accepted reviewer issues are resolved and the section
content is claim-locked, use `SKILL/nature-polishing` for concision, flow,
terminology, and journal-style refinement.

## Chunk Policy

Write in flow-sized chunks, such as one Results subsection or one Methods block.
Do not send the whole manuscript as context unless the named issue requires it.
When revising, patch only the chunk named by an accepted issue and read adjacent
chunks only for transition context.

## Non-Invention Rules

Do not introduce new claims, numbers, calculations, citations, methods, or
figures in prose. If prose needs a new claim, return to the claim matrix and
gate review.

Imported writing/polishing skills are style and structure guides only. They may
not override the claim matrix, figure map, section contract, reviewer issue
state, or the v1 exclusion on literature search and citation work.
