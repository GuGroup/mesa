# Figure Policy

Figures are evidence-bearing artifacts. They must be planned and reviewed before
section prose relies on them.

## Source of Truth

- Figure source specs, scripts, or data live under `paper/figures/source/`.
- Exported assets live under `paper/figures/exported/`.
- Review notes live under `paper/figures/qa/`.
- Figure-to-claim mapping lives in `paper/logic/figure-map.yaml`.

## Visual QA Rules

- No legend or annotation may overlap plotted data.
- Axis labels must be chemically meaningful and readable.
- Tick marks must be visible and centered across the axis line.
- Structure panels must identify system, site, and view without relying on
  prose-only context.
- Do not embed "Figure 1." caption text in the image.
- Prefer SVG or PDF source exports before raster formats.

## Generation Routing

Use imported figure skills explicitly when generating or revising figure assets:

- Use `SKILL/nature-figure` for general Nature-family figure planning,
  composition, export contract, and QA.
- Use `SKILL/energy-diagram-plotter` for reaction-coordinate, adsorption, or
  free-energy profile figures.
- Use `SKILL/sabatier-volcano-plotter` for descriptor/activity, Sabatier, or
  volcano figures.
- Use `SKILL/adsorbate-structure-grid` for optimized slab/adsorbate structure
  grids and single structure renders.

Each figure-generation task must write source specs/scripts/data under
`paper/figures/source/`, exported assets under `paper/figures/exported/`, and
QA notes under `paper/figures/qa/`, then update `paper/logic/figure-map.yaml`.
Do not generate a figure that is not tied to at least one claim ID or an
explicit SI/negative-result role.

## Environment

Run imported plotting and structure-rendering scripts through the manuscript
tooling environment:

```bash
mamba run -n mesa-manuscript python mesa/SKILL/energy-diagram-plotter/scripts/plot_energy_diagram.py --help
mamba run -n mesa-manuscript python mesa/SKILL/sabatier-volcano-plotter/scripts/plot_volcano.py --help
mamba run -n mesa-manuscript python mesa/SKILL/adsorbate-structure-grid/scripts/build_grid_figure.py --help
```
