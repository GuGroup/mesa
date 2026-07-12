# d-DOS plot styles — which one to use

`analyze_dband.py` renders three d-DOS layouts. Pick by how many systems you are
comparing and what the figure must show.

| Command | Layout | Best for |
| --- | --- | --- |
| `single` | one panel, energy on **x**, DOS on **y** | one system; a quick look with the ε_d marker |
| `compare` | overlaid curves, energy on **x** | 2–3 systems where the **shape overlap** is the point (band shift/broadening on top of each other) |
| `columns` | **one colored column per system, energy on the shared y-axis, DOS on x** | comparing **d-band centres across several systems** — the conventional publication layout |

## Prefer `columns` for d-band-centre comparisons

In practice, d-band centres are compared by drawing each system as its own
vertical column with a horizontal dashed line at ε_d and the value printed in the
panel (energy runs up the shared y-axis, DOS across x). Use `columns` for this —
it scales cleanly to many systems and reads at a glance, where an overlay gets
crowded past ~3 curves.

```bash
mamba run -n modeling python scripts/analyze_dband.py columns \
    --vaspruns A/vasprun.xml B/vasprun.xml C/vasprun.xml \
    --labels "Ni(111)" "Ni+Co-dopant" "Co(111)" \
    --elements Ni Co Co \
    --colors "#3f9a57" "#7663ab" "#c8557c" \
    --output dband_columns.svg
```

- `--elements` takes **one metal per column** (project the active-site metal in
  each system, e.g. Ni-d for Ni(111) but the Co dopant for the alloy). Pass a
  single value to broadcast it to every column.
- Each panel draws: filled metal d-DOS, a dashed **d-band-centre** line with the
  `ε_d` value printed **just below that line, right-aligned** in the column (not at
  the panel bottom), and the **Fermi level** (dash-dot at 0 eV). Keeping the value
  next to its line makes the per-column centres easy to read off and compare.

## Shared conventions across all styles

These keep panels/curves comparable — apply them consistently:

- **Per-atom DOS** (`states eV⁻¹ atom⁻¹`): the DOS is normalized by the number of
  atoms of the projected element, so a single dopant atom and a full slab are on
  the same footing. This is a constant factor and does **not** change ε_d.
- **Same energy window**: default `--emin -8 --emax 2` (trimmed to the d-band;
  cut the empty tails). Use the same window for every figure in a comparison.
- **Same DOS scale**: lock it with `--ymax` (`single`/`compare`) or `--xmax`
  (`columns`) so intensities/widths are directly comparable, not auto-scaled.
- **Light Gaussian broadening**: `--smear 0.05` (eV) by default for a clean curve
  (see the tool-convention note in the script). It is **plot-only** — ε_d, width
  and filling are always computed from the raw DOS. Set `--smear 0` for raw.

## Not recommended

2D DOS heat-maps / contour maps (energy vs. site, colour = DOS) are **not** used
for d-band-centre comparison — they bury the single number the reader wants.
Stick to the `columns` layout for cross-system d-band comparison.
