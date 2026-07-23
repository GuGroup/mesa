---
name: inspect-surface-sites
description: Read-only inspection of slabuilder structures, adsorption sites, fragments, tags, and local site graphs. Use when Codex needs to understand saved slab or adsorbed structures, identify occupied sites, inspect nearby adsorption-site connectivity, validate atom groups, propose atom selections, check fragments or bonds before diffusion/dissociation, or answer site-analysis questions without generating new structures.
---

# Inspect Surface Sites

## Scope

Use this skill for read-only structural understanding. It may propose atom groups, fragments, site rows, neighbor edges, and local transform candidates, but it must not create new structures, place adsorbates, move atoms, or submit calculations.

## Quick Start

Script paths are relative to this skill directory.

Minimal required options:

```bash
mamba run -n modeling python scripts/inspect_surface_sites.py \
  --structure structures/Pt_111_CO/site0.extxyz
```

Representative read-only dissociation-oriented inspection example. Weighted-alpha
runtime override options are listed separately in the keyword reference.
Selection-specific options that do not match the chosen
`--selection-intent` are harmless but ignored by the packet builder.

```bash
mamba run -n modeling python scripts/inspect_surface_sites.py \
  --structure structures/Pt_111_CO/site0.extxyz \
  --metadata structures/Pt_111_CO/site0.metadata.json \
  --structure-id Pt111_CO_site0 \
  --min-distance 0.5 \
  --max-atoms 200 \
  --target-adsorbate CO \
  --site-backend acat \
  --max-site-distance 3.5 \
  --neighbor-shell 2 \
  --max-sites 120 \
  --max-edges 240 \
  --selection-intent explicit \
  --selection-indices 36 37 \
  --selection-layers 1 \
  --selection-tag 2 \
  --selection-element C \
  --include-fragments \
  --transform-type dissociation \
  --moving-fragment H \
  --remaining-fragment OH \
  --break-bond O H \
  --max-transform-candidates 20 \
  --out structures/Pt_111_CO/site0.inspect.json
```

## Keyword Reference

| Keyword | Required | Meaning |
| --- | --- | --- |
| `--structure` | yes | Structure file readable by ASE. |
| `--metadata` | no | Optional slabuilder metadata JSON paired with the structure. |
| `--structure-id` | no | Identifier copied into the output packet for traceability. |
| `--min-distance` | no | Validation threshold for too-close atoms in Angstrom. |
| `--max-atoms` | no | Validation limit for DFT-ready atom count. |
| `--target-adsorbate` | no | Adsorbate label used for site matching and local transform proposals. |
| `--site-backend` | no | Backend used to rebuild adsorption sites: legacy `acat`, `auto`, `catkit`, `pymatgen`, or strict `weighted_alpha`. |
| `--weighted-alpha-executable` | no | Optional audited executable override; pair with `--weighted-alpha-radius-file`. Omit both to use the trusted private Release. |
| `--weighted-alpha-radius-file` | no | Optional audited radius-table override paired with the executable. |
| `--weighted-alpha-expected-sha256` | no | Executable SHA-256 pin required for an audited explicit override. |
| `--weighted-alpha-expected-radius-sha256` | no | Radius-table SHA-256 pin required for an audited explicit override. |
| `--weighted-alpha-runtime-sha256-manifest` | no | Exact artifact→SHA-256 runtime manifest for an explicit override. |
| `--weighted-alpha-expected-runtime-manifest-sha256` | no | SHA-256 pin for the explicit runtime manifest. |
| `--weighted-alpha-allow-unpinned-runtime` | no | Unsafe local-development override; never use for audited runs. |
| `--weighted-alpha-*` physical flags | no | Alpha factor plus contact-anchor radius/gap/step/search-limit/timeout overrides. Numeric overrides work with the trusted first-party runtime. |
| `--max-site-distance` | no | Maximum distance in Angstrom for neighboring adsorption sites. |
| `--neighbor-shell` | no | Number of site-neighbor shells to include. |
| `--max-sites` | no | Maximum site rows included in the output packet. |
| `--max-edges` | no | Maximum site-neighbor edges included in the output packet. |
| `--selection-intent` | no | Atom selection mode: `adsorbate`, `fixed_slab`, `relaxable_slab`, `top_layers`, `bottom_layers`, `explicit`, `tag`, `element`, or `all`. |
| `--selection-indices` | no | Explicit atom indices for `--selection-intent explicit`. |
| `--selection-layers` | no | Number of top or bottom z-layers for layer-based selection intents. |
| `--selection-tag` | no | ASE tag value for `--selection-intent tag`. |
| `--selection-element` | no | Element symbol for `--selection-intent element`. |
| `--include-fragments` | no | Include covalent adsorbate fragment analysis. |
| `--transform-type` | no | Read-only proposal type: `diffusion` or `dissociation`. |
| `--moving-fragment` | no | Formula of the moving fragment for dissociation proposals. |
| `--remaining-fragment` | no | Formula of the remaining fragment for dissociation proposals. |
| `--break-bond A B` | no | Element pair for the bond to break in dissociation proposals. |
| `--max-transform-candidates` | no | Maximum local transform proposal rows. |
| `--out` | no | Optional JSON output path; output is always also printed to stdout. |

## Workflow

When `--site-backend weighted_alpha` is selected, both the main site packet and
local-transform proposals use the same strict backend and configuration. With no
explicit binary paths, MESA resolves the hash-pinned source-free Windows runtime
from the private GitHub Release and verified versioned cache. Failures propagate
rather than becoming an empty site map. Phase 1 requires pbc110, Cartesian +z
alignment, selected top-layer height spread <= 0.25 A, and complete upper-terrace
population. `auto` remains the legacy path and never invokes weighted-alpha. See
`../../../WEIGHTED_ALPHA_BACKEND.md`.

1. Identify the structure file and optional metadata JSON.
2. Analyze structure packet and validation checks.
3. Inspect requested atom selection, fragments, site graph, or local transform proposal.
4. Report bounded JSON/tables with structure id, kind, tags, quality flags, fragments, occupied/current site, nearby site graph, and warnings.

Keep site outputs bounded by `--max-sites`, `--max-edges`,
`--neighbor-shell`, and `--max-site-distance` unless the user requests a wider
graph. Use `--transform-type` only to propose rows; this skill never saves
endpoint structures.


## Tag Convention

Structures from `place-surface-adsorbates` encode atom roles in ASE tags
(`atoms.get_tags()`); read them instead of inferring from coordinates:

- `0` — fixed slab atom
- `1` — relaxable slab atom
- `2` — adsorbate atom

Supporting `atoms.info` keys: `slab_atom_count`, `adsorbate_atom_count`, and
`adsorption_site_indices` (comma-separated slab-atom indices anchoring the
site). Site anchors are stored here, not as a tag. Clean slabs from
`build-slab-models` are not tagged 0/1/2 — they use `FixAtoms` constraints
only, so treat untagged structures as clean slabs.

## Read-Only Boundary

- Do not build slabs; use `build-slab-models`.
- Do not place adsorbates; use `place-surface-adsorbates`.
- Do not generate endpoint pairs; this skill only proposes local transform rows.
- Do not infer exact atom indices manually from raw coordinates. Use the packet outputs.
