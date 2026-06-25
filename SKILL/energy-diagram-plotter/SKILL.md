---
name: energy-diagram-plotter
description: Create publication-ready reaction coordinate and free-energy diagrams from user-provided energy data using the provided matplotlib/chemdiagrams visual style: boxed energy profile, bold reaction-coordinate labels, colorblind-friendly comparative paths, auto energy annotations, shared zero-reference labels, and SVG/PDF/PNG export. Use when Codex needs to plot catalyst energy profiles, adsorption/reaction intermediates, transition-state paths, or comparative surface energetics from arbitrary systems.
---

# Energy Diagram Plotter

## Workflow

1. Normalize the user's own energies into the JSON shape described in `references/input-schema.md`. Do not hard-code catalyst/material names from examples unless the user supplied them.
2. Prefer `scripts/plot_energy_diagram.py` for deterministic output. Patch the script only when the requested visual behavior is not exposed by command-line flags or JSON fields.
3. Run the script and verify that the output file is created. For manuscript figures, inspect SVG/PDF text and spacing if the user asks for final-quality layout.
4. Report the output path and any dependency issues clearly.

## Quick Start

Create a plot from the user's JSON data:

```bash
python scripts/plot_energy_diagram.py --input energies.json --output energy_diagram.svg
```

Use the generic demo only to check installation or inspect the style:

```bash
python scripts/plot_energy_diagram.py --example --output style_demo.svg
```

The script requires `matplotlib` and `chemdiagrams`. If `chemdiagrams` is missing, install it in the active project environment before plotting.

## Plotting Standards

- Use colorblind-friendly, high-contrast line colors.
- Keep reaction labels short; use newline or leading spacing only when needed to avoid collisions.
- Use concise, readable state labels and legend labels. Do not force unexplained abbreviations, but shorten phrases until each label scans cleanly on the axis.
- Label common zero-energy endpoints once when multiple paths share the same reference.
- Use SVG or PDF for editable manuscript figures; use PNG only for previews.
- Move label offsets after creating `EnergyDiagram`; `dia.fig` does not exist before `dia = EnergyDiagram(...)`.
- Treat any inline example snippet as a style reference only: line widths, boxed frame, label weights, annotation style, legend style, and export settings.
- Keep the energy diagram compact and manuscript-ready: editable SVG/PDF text, bold in-box legend labels, short prominent bold state labels, x-axis state tick bars centered on the axis spine, restrained line widths, and a quiet zero-reference line unless the user asks for another layout.

## Customization

Read `references/input-schema.md` when changing the input structure, skipping selected transition states, or tuning figure styling.
