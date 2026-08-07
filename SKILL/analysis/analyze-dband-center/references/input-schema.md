# Input Schema — D-Band Analyzer (`analyze_dband.py`)

The d-band analyzer uses subcommands and does not require a JSON input file.

## Structure-state requirement

For a conventional d-band descriptor calculation, every `vasprun.xml` MUST come
from an **adsorbate-free clean slab**. Relax the clean slab, then run the static
DOS calculation on that clean relaxed geometry. Do not use a CONTCAR from an
adsorbate relaxation.

The CLI does not infer whether a structure is clean or adsorbate-covered. The
caller must inspect the structure associated with each `vasprun.xml` before
running the command. An adsorbate-covered input is allowed only for an
explicitly requested post-adsorption analysis and must be paired with the
corresponding clean slab; it must not be reported as the conventional
clean-surface descriptor.

The CLI output is **element-resolved**, aggregated over every atom of the
selected element. It is not site-resolved.

## Single analysis

```bash
mamba run -n modeling python scripts/analyze_dband.py single --vasprun clean_slab/vasprun.xml --elements Pt --output dband.svg --json dband.json
```

## Comparison

```bash
mamba run -n modeling python scripts/analyze_dband.py compare \
    --vaspruns clean_sys_a/vasprun.xml clean_sys_b/vasprun.xml \
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

- Keep adsorbate coverage at zero across conventional descriptor comparisons.
- "Same adsorbate" means that the adsorption energies being correlated use the
  same target adsorbate; it does not mean the DOS inputs should contain it.
- The VASP calculation must use `LORBIT = 11` (or higher) to include projected DOS in `vasprun.xml`. Without this, element/orbital decomposition is unavailable and the scripts will report an error.
- DOS/static calculations should be electronically converged. Use `NELM = 300`
  and `EDIFF = 1E-5` as a conservative default; if pymatgen reports an
  unconverged `vasprun.xml`, treat plots as diagnostics only and rerun before
  interpreting d-band trends.
- Energy values are always relative to the Fermi level.
