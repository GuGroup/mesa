# Input Schema — DOS Plotter (`plot_dos.py`)

Create a JSON object with these fields:

```json
{
  "vasprun": "path/to/vasprun.xml",
  "mode": "element_pdos",
  "elements": ["Pt.d", "Ni.d"],
  "emin": -10,
  "emax": 5,
  "plot_total": true,
  "legend_cutoff": 3.0,
  "xlabel": "Energy (eV)",
  "ylabel": "DOS",
  "title": null,
  "figsize": [4.4, 3.2],
  "legend_columns": 2,
  "colors": {
    "Pt.d": "#0075dc",
    "Ni.d": "#d6604d"
  }
}
```

## Required fields

- `vasprun`: path to a `vasprun.xml` or `vasprun.xml.gz` file (not required when using `--vasprun` CLI flag or `--example`).

## Optional fields

- `elements`: list of `Element` or `Element.orbital` strings to filter projected DOS. If omitted, all elements and orbitals are shown. Examples:
  - `["Pt"]` — all orbitals for Pt
  - `["Pt.d", "Ni.d"]` — only d-orbitals for Pt and Ni
  - `["O.p", "Ti.d"]` — p-orbitals for O, d-orbitals for Ti
- `emin`, `emax`: energy range in eV relative to Fermi level. Default: `−6` to `6`.
- `plot_total`: whether to plot total DOS. Default: `true`.
- `legend_cutoff`: percentage of max DOS below which orbital labels are hidden from the legend. Default: `3.0`.
- `xlabel`, `ylabel`, `title`: axis and title labels.
- `figsize`: `[width, height]` in inches.
- `legend_columns`: number of legend columns. Default: `2`.
- `colors`: custom color mapping for element-orbital combinations.

## CLI equivalents

All JSON fields can be overridden via CLI flags:

```bash
mamba run -n modeling python scripts/plot_dos.py --vasprun vasprun.xml --elements Pt.d Ni.d --emin -10 --emax 5 --output pdos.svg
```

## Notes

- The VASP calculation must use `LORBIT = 11` (or higher) to include projected DOS in `vasprun.xml`. Without this, element/orbital decomposition is unavailable and the scripts will report an error.
- DOS/static calculations should be electronically converged. Use `NELM = 300`
  and `EDIFF = 1E-5` as a conservative default; if pymatgen reports an
  unconverged `vasprun.xml`, treat plots as diagnostics only and rerun before
  interpreting d-band trends.
- Energy values are always relative to the Fermi level.
- Prefer `Element.orbital` notation when you want specific projections, bare `Element` for all orbitals.
- Use matplotlib mathtext for labels: `$\Delta E$ (eV)`.
