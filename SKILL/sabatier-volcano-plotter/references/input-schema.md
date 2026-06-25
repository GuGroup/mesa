# Input Schema

Create a JSON object with these fields:

```json
{
  "points": [
    {"label": "Pt", "descriptor": -0.10, "activity": 1.00, "family": "noble", "highlight": true},
    {"label": "Ni", "descriptor": -0.55, "activity": 0.38, "family": "base"},
    {"label": "Ag", "descriptor": 0.45, "activity": 0.22, "family": "noble"}
  ],
  "curve": {
    "mode": "piecewise",
    "peak_x": 0.0,
    "peak_y": 1.05,
    "left_slope": 1.15,
    "right_slope": -1.35,
    "x_min": -0.9,
    "x_max": 0.8
  },
  "xlabel": "$\\Delta G_{\\mathrm{ads}}$ (eV)",
  "ylabel": "Activity (a.u.)",
  "title": null,
  "legend_loc": "auto"
}
```

Required fields:

- `points`: list of catalyst points.
- Each point requires `label`, `descriptor`, and `activity`.

Optional point fields:

- `family`: categorical group for color/marker styling.
- `highlight`: true for emphasized catalysts.
- `label_point`: false to suppress a label on a specific point. By default, highlighted points are labeled; non-highlighted points may be labeled when the dataset is small.

Optional top-level fields:

- `curve`: volcano envelope definition.
  - `mode: "piecewise"` draws a Sabatier volcano from `peak_x`, `peak_y`, `left_slope`, and `right_slope`.
  - `mode: "points"` draws a user-supplied envelope from arrays `x` and `y`.
  - omit `curve` to draw only the scatter plot.
- `xlabel`, `ylabel`, `title`: figure text.
- `family_styles`: mapping of family to `color` and optional `marker`.
- `optimum_label`: label next to the volcano peak. Default: `Optimum`.
- `legend_loc`: in-box matplotlib legend location. Default: `auto`, which tests several in-box locations and picks the one with the least overlap against points and the volcano envelope.
- `figsize`: two-number array. Default: `[5.0, 3.6]`.
- `xlim`, `ylim`: axis limits.
- `higher_is_better`: boolean used only for documentation/QA. Default: `true`.

Style notes:

- Keep catalyst labels short and chemically meaningful.
- For dense datasets, set `label_point: false` except for the optimum, benchmark, and proposed catalysts.
- Keep `legend_loc: "auto"` unless the user explicitly wants a fixed legend position; the script should avoid covering plotted points or the volcano envelope.
- Use SVG or PDF when the figure will be edited in Illustrator/Inkscape.
- If the envelope is theoretical or hand-drawn, say so in the response or caption. Do not present it as a fitted model.
