# Section Contracts

`paper/manuscript/section-contracts.yaml` controls which claims, figures, and
source files each manuscript section may use.

## Required Shape

```yaml
version: 1
sections:
  - id: results
    path: paper/manuscript/sections/results.md
    status: ready-to-draft
    allowed_claims: [C1]
    required_figures: [F1]
    required_sources:
      - paper/inputs/results/co_pt111_energy.yaml
    required_caveats: []
    blocked_by: []
    chunk_policy:
      unit: flow-sized-result-block
      locked_chunks: []
```

## Section Status

Use one of `not-ready`, `ready-to-draft`, `drafted`, `locked`, or `blocked`.
A section is `ready-to-draft` only when all allowed claims are supported or
qualified, all required figures have passed QA, and all blocker issues tied to
the section are closed.

## Required Sections

Nature-family v1 expects at least:

- `abstract`
- `introduction`
- `results`
- `discussion`
- `methods`

Supplementary information may include:

- `si-outline`
- `methods-detail`
- `tables`
- `figures`

## Gate Rules

- A section cannot use a claim outside `allowed_claims`.
- A section cannot cite a figure outside `required_figures` or optional figures
  explicitly listed for the section.
- Drafting order is Results, Methods, SI, Discussion, Introduction, Abstract,
  then Title.
- Abstract and title may use only claims already locked in Results and
  Discussion contracts.
