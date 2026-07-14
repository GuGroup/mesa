# Figure Domain Workflow

Use this manual for standalone scientific figures generated from accepted or
caveated project evidence.

Manuscript figure mapping, realization, captions, and DOCX insertion are
controlled by `SKILL/manuscript/workflow.md`. The figure skills here may be
called by manuscript figure realization when specialized plots or renders are
needed.

# Skills

- `render-adsorbate-structure-grid`
- `plot-energy-diagram`
- `plot-sabatier-volcano`
- `plot-dos`
- `create-nature-figure`

# Entry Requirements

Before generating a figure, confirm:

- the data or structures come from recipe-backed, validated artifacts;
- acceptance state and caveats are known;
- missing required data are not being invented visually;
- the figure purpose is clear: inspection, result artifact, manuscript input,
  or supplementary figure.

# Structure Grids

Use `render-adsorbate-structure-grid` for adsorbate, slab, gas, or surface
structure panels where the input structures already exist.

Do not use a rendered structure panel as evidence for an uncomputed adsorption
state.

# Energy Diagrams

Use `plot-energy-diagram` when a validated energy or free-energy table exists
and the plotted quantities match the chemistry and units.

Do not plot electronic-energy proxies as free-energy diagrams unless the figure
and caption explicitly label the boundary.

# Volcano Plots

Use `plot-sabatier-volcano` when descriptor data, activity proxy data, or
benchmark points are available and compatible with the skill.

Do not imply experimental activity proof from a descriptor-only volcano unless
that claim is explicitly supported.

# Nature-Style Figures

Use `create-nature-figure` for assembling publication-style multi-panel figure
layouts from existing panels and accepted data.

It may organize panels and styling. It must not create scientific evidence that
does not exist in the source artifacts.

# Output Rules

Save figure outputs under the relevant project, strategy, or manuscript figure
folder. Preserve enough metadata to trace:

- source data or structure paths;
- source recipe or result artifact;
- plotting script or skill;
- units, labels, and transformations;
- figure caveats and acceptance state.

For the current DOCX manuscript workflow, manuscript figure exports are PNG.
Standalone archival figures may also keep SVG, PDF, or source files when the
called skill supports them.
