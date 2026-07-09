# Input Schema — D-Band Analyzer (`analyze_dband.py`)

The d-band analyzer uses subcommands and does not require a JSON input file.

## Single analysis

```bash
mamba run -n modeling python scripts/analyze_dband.py single --vasprun vasprun.xml --elements Pt --output dband.svg --json dband.json
```

## Comparison

```bash
mamba run -n modeling python scripts/analyze_dband.py compare \
    --vaspruns sys_a/vasprun.xml sys_b/vasprun.xml \
    --labels "Pt(111)" "PtNi(111)" \
    --element Pt \
    --output dband_compare.svg \
    --json comparison.json
```

## Example (synthetic demo)

```bash
mamba run -n modeling python scripts/analyze_dband.py example --output dband_example.svg
```

## JSON output format

Single analysis:
```json
{
  "fermi": 5.2341,
  "elements": {
    "Pt": {
      "d_band_center": -2.2500,
      "d_band_width": 1.8200,
      "d_band_filling": 0.9100
    }
  }
}
```

Comparison:
```json
[
  {
    "label": "Pt(111)",
    "d_band_center": -2.2500,
    "d_band_width": 1.8200,
    "d_band_filling": 0.9100
  },
  {
    "label": "PtNi(111)",
    "d_band_center": -2.7800,
    "d_band_width": 1.6500,
    "d_band_filling": 0.8700
  }
]
```

## Notes

- The VASP calculation must use `LORBIT = 11` (or higher) to include projected DOS in `vasprun.xml`. Without this, element/orbital decomposition is unavailable and the scripts will report an error.
- DOS/static calculations should be electronically converged. Use `NELM = 300`
  and `EDIFF = 1E-5` as a conservative default; if pymatgen reports an
  unconverged `vasprun.xml`, treat plots as diagnostics only and rerun before
  interpreting d-band trends.
- Energy values are always relative to the Fermi level.
