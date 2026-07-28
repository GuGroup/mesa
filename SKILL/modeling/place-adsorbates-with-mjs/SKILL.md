---
name: place-adsorbates-with-mjs
description: Extract regular P0/P1/P2 adsorption sites (top/bridge/hollow) from a slab POSCAR/CIF with the weighted-alpha engine and emit the fixed result set — regular_adsorption_sites.json/csv/xyz plus an N-each Plotly HTML report (and optional pre-DFT adsorbate POSCARs). Use when Codex is given a slab structure plus an adsorbate radius and a PBC mask and only the corresponding result artifacts are wanted. Input in -> results out; no orientation sweep, force-field, or DFT relaxation.
---

# Place Adsorbates With MJS

## Overview

Given a slab (`POSCAR`/`CIF`), an adsorbate radius, and a PBC mask, this skill runs the
weighted-alpha engine and extracts **regular** adsorption sites, mapping node types to
site kinds: `P0 -> top`, `P1 -> bridge`, `P2 -> hollow`. It writes a fixed, deterministic
result set for that input and nothing else.

Site acceptance policy is `regular_p1_p2_with_p0_top_exception_v1`:

- **top (P0)**: surface-node exception (`P0_top_surface_node_exception`).
- **bridge (P1)**: `classification == regular` required.
- **hollow (P2)**: regular P2 topology required.
- Only `position_source == placement.position` (clearance-optimised placement) is accepted;
  fallback/anchor estimates are excluded.

## Engine (not bundled)

The weighted-alpha C++ executable and the element radius table are **not shipped in this repo**
(the native engine is internal-only / do-not-publish). They are located by explicit flag or, if
omitted, by environment — **no PATH discovery** (same contract as `slabuilder.weighted_alpha_backend` /
`WEIGHTED_ALPHA_BACKEND.md`):

- `--exe` or `MESA_WEIGHTED_ALPHA_EXE` → the `weighted_alpha_complex` executable.
- `--radius-file` or `MESA_WEIGHTED_ALPHA_RADIUS_FILE` → element radius table such as `UFF.rad`.

Provenance is SHA-256 pinned when an expected digest is supplied (verified fail-closed):

- `--expected-exe-sha256` or `MESA_WEIGHTED_ALPHA_EXPECTED_SHA256`.
- `--expected-radius-sha256` or `MESA_WEIGHTED_ALPHA_EXPECTED_RADIUS_SHA256`.

Without a pin the run proceeds but prints an unpinned-provenance warning (suppress with
`--allow-unpinned-runtime` for local dev). Audited/mesa runs should always pass the pins.

## Quick Start

Script paths are relative to this skill directory. Run inside the `modeling` env:

```bash
mamba run -n modeling python scripts/place_adsorbates_with_mjs.py \
  -f path/to/slab.POSCAR \
  -a 1.52 \
  --pbc 110 \
  --open-axis-side open-max \
  --exe "$WEIGHTED_ALPHA_EXE" \
  --radius-file "$WEIGHTED_ALPHA_RADIUS_FILE" \
  --out-dir path/to/result
```

`--dry-run` prepares the input and writes `engine_command.txt` + metadata without executing the engine.

## Options

| Flag | Required | Default | Meaning |
|---|---|---|---|
| `-f, --input` | yes | – | slab `POSCAR`/`CIF` |
| `-a, --adsorbate-radius` | yes | – | adsorbate probe radius (= `--precursor-radius`); also engine `-a` unless `--engine-alpha` set |
| `--pbc` | yes | – | PBC mask `111`/`110`/`000` or comma form `1,1,0` |
| `--exe` | yes* | env | weighted-alpha executable (not bundled); *or `MESA_WEIGHTED_ALPHA_EXE` |
| `--radius-file` | yes* | env | element radius table (not bundled); *or `MESA_WEIGHTED_ALPHA_RADIUS_FILE` |
| `--expected-exe-sha256` | no | env | expected exe SHA-256, verified fail-closed; or `MESA_WEIGHTED_ALPHA_EXPECTED_SHA256` |
| `--expected-radius-sha256` | no | env | expected radius-file SHA-256; or `MESA_WEIGHTED_ALPHA_EXPECTED_RADIUS_SHA256` |
| `--allow-unpinned-runtime` | no | off | suppress the unpinned-provenance warning (local dev only) |
| `--engine-alpha` | no | `-a` | explicit weighted-alpha coefficient (kept separate from probe radius) |
| `--gap` | no | `0.1` | required clearance |
| `--dedup-distance` | no | `0.6` | per-kind dedup distance |
| `--candidate-distance` | no | `3.0` | fallback anchor+normal distance |
| `--normal-source` | no | `current` | `current` or `geompy` |
| `--open-axis-side` | no | `both` | `both`/`zmax`/`zmin`/`open-max`/`open-min` |
| `--placement-step` | no | `0.0125` | placement search step |
| `--placement-max-distance` | no | `8.0` | max placement distance |
| `--sample-per-kind` | no | `5` | N per kind shown in the `{N}each.html` report |
| `--out-dir` | no | auto | output directory |
| `--dry-run` | no | off | prepare metadata only, skip engine |

## Outputs (fixed set, in `--out-dir`)

- `regular_adsorption_sites.json` — `metadata`, `counts`, `rejected`, `framework_atom_count`, `raw_site_count`, `sites[]` (full 35-field records).
- `regular_adsorption_sites.csv` — 17 columns (`site_id,site_kind,node_type,source_node_id,classification,min_clearance,nearest_atom,position_source,placement_status,open_axis_side,x,y,z,normal_x,normal_y,normal_z,atoms`).
- `regular_adsorption_sites.xyz` — site positions.
- `regular_adsorption_sites_{N}each.html` — self-contained Plotly 2.35.2 report: header list, table (`kind|source node|min clearance|position|classification`), and 3D scatter (framework + top/bridge/hollow). Shows the top-N sites per kind by `min_clearance`.
- `engine_command.txt`, `prepared_input/`, `engine_run/`.

## Notes

- `pip`/env deps: the post-processing is pure stdlib; `prepare_poscar_input` uses ASE (in the `modeling` env).
- `input in -> result out` only; results are unrelaxed initial guesses.
- Full output contract and provenance: see `references/output_contract.md`.
