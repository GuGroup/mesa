# Cross-Reference QA

Typeset/export checks cover mechanical consistency only.

## Required Checks

- Every section contract path exists.
- Every section `allowed_claims` entry exists in `claim-matrix.yaml`.
- Every section `required_figures` entry exists in `figure-map.yaml`.
- Required section figures are not `blocked`, `needs-source`, or `excluded`.
- Every section `required_sources` path exists.
- Every claim evidence path exists.
- Every claim figure ID exists in the figure map.
- Every figure source, exported, and QA path exists.
- `notation.yaml` declares the required top-level categories.

## Non-Goals

The QA does not approve scientific claims, visual design quality, citation
correctness, or journal compliance beyond the internal Nature-family Word export
shape.
