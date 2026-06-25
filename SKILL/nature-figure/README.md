# `nature-figure` skill

`nature-figure` is a publication-grade figure workflow for Nature-family and other high-impact scientific manuscripts. It supports Python and R backends, but the backend must be selected before drawing.

## Capabilities

- Define the figure contract before plotting: conclusion, evidence logic, panel map, export needs, and review risks.
- Route to Python (`matplotlib` / `seaborn`) or R (`ggplot2`, `patchwork`, `ComplexHeatmap`) and use only the selected backend.
- Provide publication-oriented defaults for palettes, typography, panel structure, and editable SVG/PDF export.
- Use on-demand references for chart types, common patterns, design theory, demos, and QA.

## Required Gate

If the user has not chosen a backend, ask exactly:

```text
Python or R?
```

Stop until the user answers. Do not guess, generate mock data, or switch backends mid-task.

## Structure

```text
nature-figure/
  SKILL.md
  manifest.yaml
  static/core/
  static/fragments/backend/
  references/
  assets/
```

## Default Workflow

1. Load the manifest and core contract.
2. Resolve the backend.
3. Load the selected backend fragment only.
4. Write or infer the figure contract.
5. Build, export, and visually inspect the figure through the chosen backend.
6. Report generated files and any remaining scientific or rendering risks.

## Status

Stable for local scientific-figure work when the backend runtime is available.
