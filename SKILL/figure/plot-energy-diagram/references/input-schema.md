# Input Schema

Create a JSON object with these fields:

```json
{
  "data": {
    "Catalyst A": [0.0, -0.13, 0.38, -0.76, -0.20, 0.0],
    "Catalyst B": [0.0, -0.96, -1.02, -1.03, 0.09, 0.0]
  },
  "x_labels": ["H$_2$O+*+e$^-$", "H$_2$O*", "TS", "H*+OH*", "OH*+$\\frac{1}{2}$H$_2$", "*+OH$^-$+$\\frac{1}{2}$H$_2$"],
  "colors": {
    "Catalyst A": "#2166ac",
    "Catalyst B": "#d6604d"
  },
  "skip_points": {
    "Catalyst B": [2]
  },
  "ylabel": "$\\Delta G_{\\mathrm{rel}}$ (eV)",
  "xlabel": "Reaction Coordinate"
}
```

Required fields:

- `data`: mapping of path label to numeric energies. All full paths should share the same intended x positions.

Optional fields:

- `x_labels`: labels for each reaction coordinate. If omitted, numeric positions are used.
- `colors`: mapping of path label to matplotlib-compatible colors.
- `skip_points`: mapping of path label to zero-based x indices to omit from that path. Use this for paths without a transition-state plateau or missing intermediate.
- `ylabel`, `xlabel`: axis text overrides.
- `title`: accepted for backward-compatible input files but always ignored. Do not render plot titles; add figure titles or panel labels outside the exported diagram.
- `figsize`: two-number array. Default: `[5.4, 4]` for tighter physical spacing between reaction states.
- `fontsize`: base font size.
- `x_number_min_max`: two-number range for automatic energy labels, such as `[0.5, 4.5]`.
- `zero_label_positions`: x positions where a shared `0.00` label should be drawn once.
- `show_zero_line`: whether to draw a horizontal zero-reference line. Default: `false`; enable it only when the user explicitly requests a baseline.
- `show_state_ticks`: whether to draw short vertical tick bars under each reaction state. Default: `true`.
- `legend_loc`: in-box matplotlib legend location. Default: `upper right`; after rendering, inspect the image directly and move this if it overlaps paths, annotations, state labels, or the boxed frame.

Notes:

- Labels may use matplotlib mathtext, for example `MO$_2$`.
- Prefer matplotlib mathtext for final labels, for example `H$_2$O+*+e$^-$`, instead of relying on Unicode subscripts and superscripts.
- The original inline snippet had an ordering bug: `offset = ... dia.fig ...` was declared before `dia` existed. Always create `EnergyDiagram` before computing transforms that depend on `dia.fig`.
- The original inline snippet is a style reference, not a data template. Replace all path names, energies, labels, colors, and skipped points with the user's actual system.
- If user prose and code disagree about which path should omit a point, ask or preserve the data exactly as provided and flag the ambiguity.
- The default style follows a compact publication figure hierarchy: a `5.4 × 4 in` canvas, wider plateaus, compact bold state labels, a slightly inset boxed frame, editable SVG/PDF text, visible state tick bars centered on the x-axis spine, and an in-box legend placed where it least interferes with the paths. Preserve the full tight-layout canvas instead of applying a second tight bounding-box crop.
- Keep the horizontal export bounds flush with the outer state-label extents. Do not add blank left or right canvas margins around those labels.
- Keep x-axis state labels and legend labels concise. They do not need to be cryptic abbreviations, but they should be short enough to scan, such as `Initial`, `Adsorbed H2O`, `TS`, `H* + OH*`, `OH* + H2`, `Final`.
- Always inspect a rendered preview before final handoff. If the legend or labels overlap the plotted energy diagram, change `legend_loc`, shorten labels, or adjust canvas/limits and regenerate.
