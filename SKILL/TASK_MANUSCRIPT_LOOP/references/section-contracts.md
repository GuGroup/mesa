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

## Manuscript Display Order

Nature-family v1 exports sections in this manuscript-facing order:

- `abstract`
- `introduction`
- `results_and_discussion` or paired `results` / `discussion` content exported
  under "Results and Discussion"
- `computational_methods` or `methods`; detailed procedures may move to SI
- `conclusion`
- `si`

Methods may be compact in the main manuscript or moved largely to SI when the
target journal and manuscript strategy allow it. Do not let drafting order
override the exported manuscript order.

Supplementary information may include:

- `si-outline`
- `methods-detail`
- `tables`
- `figures`

## Gate Rules

- A section cannot use a claim outside `allowed_claims`.
- A section cannot cite a figure outside `required_figures` or optional figures
  explicitly listed for the section.
- Prose drafting can still start from Results/Discussion chunks for evidence
  control, but export order is Abstract, Introduction, Results and Discussion,
  Computational Methods/Methods, Conclusion, then SI.
- Abstract and title may use only claims already locked in Results and
  Discussion contracts.
