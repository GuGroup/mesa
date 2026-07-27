# Output Contract — place-adsorbates-with-mjs

Reference run (golden):
`ytk_agent_test_slab_universal_contact_NO3_radius1p52_pbc110_openmax_step0p0125`.

## Engine invocation (built by the script)

```
<exe> -f <prepared slab.POSCAR> -a <engine_alpha> --pbc <mask>
  --voro-construction-mode pbc_masked_image_aware
  --radius-file <radius file> --precursor-radius <adsorbate_radius>
  --placement-gap <gap> --placement-step <step>
  --placement-max-distance <max> --emit-geompy-normals
```

`engine_alpha` (`-a`, default 1.0 via `--engine-alpha`/adsorbate radius) and
`--precursor-radius` (adsorbate probe radius, e.g. 1.52) are **distinct** and must not be conflated.

## Graph census invariants (regression gate)

`p0_count=54, p1_count=357, p2_count=679, p3_count=331, p2_topology_invalid_count=0`
(backend `mixed_periodic_image_aware_core`). Reference counts: `top=5, bridge=15, hollow=12, total=32`;
minimum accepted clearance ≈ `0.10005`; every accepted clearance `>= gap`.

## Site acceptance — `regular_p1_p2_with_p0_top_exception_v1`

| kind | node | regular_policy | classification | value_type |
|---|---|---|---|---|
| top | P0 | P0_top_surface_node_exception | atom | atom_radius |
| bridge | P1 | classification_regular_required | regular | edge_length |
| hollow | P2 | regular_p2_topology_required | regular | face_area |

Only `position_source == placement.position` accepted; fallback/anchor estimates excluded.

## Files (in `--out-dir`)

- **json** — top-level `metadata, counts, rejected, framework_atom_count, raw_site_count, sites`.
  Each site carries 35 fields incl. `adsorption_position, anchor_position, normal, min_clearance,
  atoms, placement_status, position_source, open_axis_*, value/value_type`.
- **csv** — 17 columns (see SKILL.md).
- **xyz** — site positions.
- **`{N}each.html`** — Plotly `2.35.2` self-contained report. Header `<ul>` (input, pbc, radius,
  `engine sha256_12`, shown counts), table (`kind|source node|min clearance|position|classification`),
  embedded `payload={atoms,sites,metadata}`, 3D scatter with colors `top=#1f77b4 / bridge=#2ca02c /
  hollow=#d62728`, title `"slab regular adsorption sites: 5 each P0/P1/P2 when available"`.
  Selection = top-N per kind by `min_clearance` (fewer if unavailable).

## Verification status (2026-07-24, sandbox)

Packaged from the proven generator (`audit/adsorption_site_regular_workcopy`). Reproduced against
the golden reference: **CSV byte-identical, XYZ byte-identical, N-each selection identical**;
`write_html` emits the expected Plotly report; 10/10 unit tests pass. Engine-execution path
(`run_weighted_alpha`, ASE prepare) requires the native engine and is unchanged from the reference code.
