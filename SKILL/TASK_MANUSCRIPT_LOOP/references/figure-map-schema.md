# Figure Map Schema

`paper/logic/figure-map.yaml` maps figures to claims and source files. The map
must pass before section prose generation.

## Top-Level Shape

```yaml
version: 1
figures:
  - id: F1
    label: "Figure 1"
    role: main
    title: "Energy landscape for CO on Pt(111)"
    caption: "Energy landscape for CO adsorption on Pt(111), showing the evaluated states and the corresponding adsorption-energy reference."
    claim_ids: [C1]
    source_files:
      - paper/figures/source/fig1_energy_diagram.spec.yaml
    exported_files:
      - paper/figures/exported/fig1_energy_diagram.svg
    qa_files:
      - paper/figures/qa/fig1_energy_diagram.md
    status: qa-passed
    blockers: []
```

## Required Figure Fields

- `id`: stable ID such as `F1`, `F2`, or `SF1`.
- `label`: manuscript-facing label.
- `role`: `main`, `extended-data`, `si`, or `candidate`.
- `title`: short working title without embedded caption text.
- `caption`: Nature-style caption body without the leading label. The DOCX
  exporter renders this as `**Figure N |** caption`, with the label and pipe
  bold only. Use `title` only as a fallback when a caption is not yet
  available.
- `claim_ids`: claim IDs from `paper/logic/claim-matrix.yaml`.
- `source_files`: script, data, or spec files under `paper/figures/source/`.
- `exported_files`: figure outputs under `paper/figures/exported/`.
- `qa_files`: review notes under `paper/figures/qa/`.
- `status`: `planned`, `needs-source`, `generated`, `qa-passed`, `blocked`, or
  `excluded`.
- `blockers`: unresolved issues or empty list.

## Gate Rules

- Every main figure must support at least one claim ID.
- Every main claim needs exactly one primary story position: main figure, SI
  item, or text-only support recorded in the claim matrix.
- No section contract may require a figure whose status is `blocked`,
  `needs-source`, or `excluded`.
- Captions are prose artifacts and must not be embedded in image files.
- Captions must not contain exported-file paths or QA notes.
