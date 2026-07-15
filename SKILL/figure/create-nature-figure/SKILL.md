---
name: create-nature-figure
description: >-
  Create, revise, audit, or polish submission-grade scientific figures for
  Nature-family and other high-impact journals using Python, matplotlib, and
  seaborn. Use for multi-panel manuscript figures, figures4papers-style plots,
  and journal-ready SVG/PDF/TIFF exports when the source data or panels already
  exist. Define the figure conclusion, evidence logic, export needs, and review
  risks before plotting. Not for dashboards or Illustrator/Figma-first
  infographics.
---

For MESA end-to-end use, read `SKILL/figure/workflow.md` before applying this skill.

# Nature Figure Making

This is a Python-only publication-figure workflow. Use the static contract and
Python fragment instead of reconstructing the plotting rules from memory.

## Required Loading

1. Read `manifest.yaml`.
2. Read every file under `always_load`:
   - `static/core/contract.md`
   - `static/core/stance.md`
   - `static/fragments/backend/python.md`
3. Load additional references only when their `references.on_demand` condition
   matches the task.

## Workflow

1. State the one-sentence conclusion the figure must support.
2. Map each panel to a distinct piece of accepted evidence and remove panels
   that do not carry unique information.
3. Select the figure archetype, final dimensions, source-data requirements,
   statistics, and editable export formats.
4. Check the Python runtime and required plotting packages before rendering.
5. Build and export with the Python fragment and relevant references.
6. Inspect the rendered output at final size and apply `references/qa-contract.md`
   before delivery.

If Python or a required package is unavailable, stop before rendering and report
the exact missing dependency. Do not claim that a figure was generated.
