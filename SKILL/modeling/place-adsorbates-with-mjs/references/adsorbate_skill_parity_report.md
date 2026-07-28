# Adsorbate Skill Parity Report

Golden reference case: `ytk_agent_test_slab_universal_contact_NO3_radius1p52_pbc110_openmax_step0p0125`.
Verification performed in the Linux sandbox on the committed reference artifacts; the native
Windows engine was **not** re-executed here (see "Unresolved").

## Reference input

- Slab: `prepared_input/slab.POSCAR` (Cu/Ni/Ru/Co multi-metal slab, z-vacuum).
- Parameters (from `engine_command.txt` + `placement_step_0p0125_summary.md`):
  radius 1.52 Å, engine alpha 1.0, `pbc 110`, open-max, gap 0.1 Å, step 0.0125 Å, max 8.0 Å,
  `--voro-construction-mode pbc_masked_image_aware`, `--emit-geompy-normals`.

## Reference output (golden)

- `regular_adsorption_sites.json` — counts `{top:5, bridge:15, hollow:12, total:32}`.
- `regular_adsorption_sites.csv` (33 rows incl. header), `.xyz` (32 sites).
- `regular_adsorption_sites_5each.html` — Plotly 2.35.2, 54 framework atoms + 15 sites (5/kind).

## Reference generator

The ytk pipeline invoking the geom_paper build (`engine sha256_12 = d988bb24cee1`) →
`weighted_alpha_graph.json` → `regular_p1_p2_with_p0_top_exception_v1` extraction.

## C++ direct run (independent)

Mesa's own `verification/run_ytk_public_api_acceptance.py` runs the pinned
`portable_bin_semantic\weighted_alpha_complex.exe` (sha256 `0487c0d7…`) through
`slabuilder.adsorption.identify_adsorption_sites` → **candidate_count = 32**, first candidates
`p2_85`/`p2_61` (fcc hollow). Matches the golden total of 32.

## Mesa skill run (this skill, sandbox)

`place_adsorbates_with_mjs.extract_regular_sites(...)` run on the committed reference
`engine_run/weighted_alpha_graph.json` (bypassing the Windows exe), then `write_sites_csv/xyz`,
`select_sites_for_html`, `write_html` with `normal_source=current`, `gap=0.1`, `pbc=110`,
`open_axis_side=open-max`, `adsorbate_radius=1.52`, `dedup=0.6`.

## Semantic comparison

| Payload | Result |
|---|---|
| Counts (top/bridge/hollow/total) | `5/15/12/32` — **identical** |
| CSV (17 cols: id, kind, node, source, class, min_clearance, nearest, source, status, side, x,y,z, nx,ny,nz, atoms) | **byte-identical** |
| XYZ (32 site positions) | **byte-identical** |
| HTML 5-each selection (15 `source_node_id`) | **identical set** (`p0_10,11,12,14,15; p1_47,50,53,101,116; p2_61,85,122,153,428`) |
| HTML framework atoms | 54 — **identical** |
| Renderer | Plotly 2.35.2 CDN — **identical** |
| `normal_source` | `current` reproduces byte-exact; `geompy` differs only in normal columns (expected alternate) |

## Tolerance

CSV/XYZ compared **byte-exact** (no numeric tolerance needed — full-precision float repr matches).
Full-set (32) byte-identity of CSV implies every per-site field (position, normal, clearance,
atoms, status) matches, not just the 15 shown in HTML.

## Differences

None in scientific payload. Whole-file HTML byte-equality is *not* expected (and not required):
the header embeds the engine `sha256_12` (differs by which build produced the graph), absolute
input paths, and Plotly array ordering — hence semantic-payload comparison per spec.

## Unresolved / not run here

- The native `weighted_alpha_complex.exe` was not executed in this Linux sandbox (Windows PE +
  qhull/stdc++ DLLs). The engine→graph step is covered by the reference `engine_run/` artifacts and
  Mesa's `run_ytk_public_api_acceptance.py` (candidate_count = 32).
- High-symmetry (non-jittered 2H-type) inputs can stall the current engine build; out of scope for
  this reference case and handled by `--jitter` / the fixed engine build.

## Skill convention alignment (this pass)

Added, additive + backward-compatible, to match the closest sibling `place-surface-adsorbates`:
`MESA_WEIGHTED_ALPHA_EXE`/`_RADIUS_FILE` locator (flag → env, no PATH), and SHA-256 pins
(`--expected-exe-sha256` / `--expected-radius-sha256` + env), verified fail-closed; missing pin
warns (documented divergence: standalone skill stays usable unpinned in local dev).

## Verification levels

| Aspect | Level |
|---|---|
| Mesa architecture / skill lifecycle / closest sibling | ANALYZED (file-cited) |
| C++ engine CLI contract | ANALYZED (source-cited) |
| Skill post-engine pipeline vs golden | **REFERENCE_PARITY_VERIFIED** (CSV/XYZ byte-identical, counts, 5-each ids) |
| Skill unit tests (incl. new locator/pin) | UNIT_TESTED — 12/12 pass |
| Engine `.exe` execution in this sandbox | NOT_RUN (Windows binary; covered by Mesa acceptance = 32) |
