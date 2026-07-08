---
name: plot-sabatier-volcano
description: Create publication-ready Sabatier/volcano plots from user-provided descriptor and activity data using a Python matplotlib workflow. Use when Codex needs to plot catalytic activity versus binding-energy descriptors, fit or draw volcano envelopes, mark the optimum, compare catalyst families, label selected catalysts, or export editable SVG/PDF/PNG manuscript figures.
---

# Sabatier Volcano Plotter

## Workflow

1. Normalize the user's catalyst data into the JSON shape described in `references/input-schema.md`.
2. Prefer `scripts/plot_volcano.py` for deterministic output. Patch the script only when the requested behavior is not exposed by JSON fields.
3. Keep labels concise and readable. Label only important points by default; dense volcano plots should not label every catalyst unless requested.
4. Run the script and verify that the output file exists. For manuscript output, prefer SVG or PDF with editable text.
5. Report the output path and any unresolved modeling assumptions, such as whether the volcano envelope is theoretical, fitted, or user-supplied.

## Quick Start

Create a plot from user data:

```bash
python scripts/plot_volcano.py --input volcano.json --output volcano.svg
```

Use the generic demo only to inspect the style:

```bash
python scripts/plot_volcano.py --example --output volcano_demo.svg
```

The script requires `matplotlib` and `numpy`.

## Plotting Standards

- Use the descriptor on the x-axis and activity or limiting potential on the y-axis.
- Make clear whether higher y-values mean better activity. If lower is better, invert or relabel deliberately.
- Use a restrained palette: neutral points for context, one or two signal families, and sparse accent color for the optimum or target catalyst.
- Draw the volcano envelope as a quiet but visible line; do not imply a fitted law unless the data or user specifies one.
- Place the legend inside the axes, but avoid covering points, labels, the peak, or the volcano envelope. Keep `legend_loc: "auto"` unless the user explicitly asks for a fixed position.
- Use editable SVG/PDF text, bold axis labels, readable tick labels, and short catalyst labels.
- Preserve scientific meaning over visual polish. Flag missing units, unclear descriptor definitions, and ambiguous activity metrics.

## Customization

Read `references/input-schema.md` when changing data fields, curve construction, labels, family styling, or export behavior.
