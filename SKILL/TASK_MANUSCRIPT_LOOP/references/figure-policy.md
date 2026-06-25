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

## Scope Boundaries

This skill may plan and review figures, but v1 does not implement plotting
logic here. Reuse existing MESA outputs or catalyst plotting skills when later
Todos add scripts.
