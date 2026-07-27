---
name: place-surface-adsorbates
description: Identify adsorption sites and place adsorbates on slabuilder slabs. Use when Codex needs to resolve adsorbate formulas, names, or SMILES, find top/bridge/hollow/ACAT-compatible sites, create bounded adsorbate placement candidates, avoid occupied sites, validate site metadata and minimum distances, or create HER, ORR, OER, CO2RR, and related surface-intermediate starting structures.
---

# Place Surface Adsorbates

## Scope

Use this skill after a clean slab exists. It intentionally combines adsorption-site identification and adsorbate placement because placement without site detection is not meaningful. Use `inspect-surface-sites` when the user only wants read-only site analysis.

## Quick Start

Script paths are relative to this skill directory.

Minimal required options:

```bash
mamba run -n modeling python scripts/place_surface_adsorbates.py \
  --slab structures/Pt_111/Pt_mp-126_111_term0.extxyz \
  --adsorbate CO
```

Representative legacy-backend workflow example (weighted-alpha override options are
listed separately in the keyword reference):

```bash
mamba run -n modeling python scripts/place_surface_adsorbates.py \
  --slab structures/Pt_111/Pt_mp-126_111_term0.extxyz \
  --adsorbate CO \
  --max-sites 3 \
  --height 2.0 \
  --backend auto \
  --max-atoms 200 \
  --min-distance 0.5 \
  --outdir structures/Pt_111_CO
```

## Keyword Reference

| Keyword | Required | Meaning |
| --- | --- | --- |
| `--slab` | yes | Parent clean slab file, preferably extxyz with slabuilder metadata. |
| `--adsorbate` | yes | Adsorbate label, SMILES, `smiles:<SMILES>`, or chemical name. |
| `--max-sites` | no | Maximum adsorption-site candidates to place. |
| `--height` | no | Optional legacy-backend adsorbate height in Angstrom; ignored for weighted-alpha contact-anchor placement. |
| `--backend` | no | Site backend: legacy `auto`, `acat`, `catkit`, `pymatgen`, or strict `weighted_alpha`. |
| `--weighted-alpha-executable` | no | Optional audited executable override; pair with `--weighted-alpha-radius-file`. Omit both to use the trusted private Release. |
| `--weighted-alpha-radius-file` | no | Optional audited radius-table override paired with the executable. |
| `--weighted-alpha-expected-sha256` | no | Executable SHA-256 pin required for an audited explicit override. |
| `--weighted-alpha-expected-radius-sha256` | no | Radius-table SHA-256 pin required for an audited explicit override. |
| `--weighted-alpha-runtime-sha256-manifest` | no | Exact artifact→SHA-256 runtime manifest for an explicit override. |
| `--weighted-alpha-expected-runtime-manifest-sha256` | no | SHA-256 pin for the explicit runtime manifest. |
| `--weighted-alpha-allow-unpinned-runtime` | no | Unsafe local-development override; never use for audited runs. |
| `--weighted-alpha-*` physical flags | no | Alpha factor plus contact-anchor radius/gap/step/search-limit/timeout overrides. Numeric overrides work with the trusted first-party runtime. |
| `--max-atoms` | no | Validation limit for DFT-ready atom count after placement. |
| `--min-distance` | no | Validation threshold for too-close atoms in Angstrom. |
| `--outdir` | no | Output directory for extxyz, POSCAR, and metadata files. |

## Adsorbate Input

`--adsorbate` accepts, in resolution order:

1. `smiles:<SMILES>` — explicit SMILES, e.g. `smiles:O=C=O` (RDKit only, no Java).
2. A built-in label/alias — `CO`, `H`, `OH`, `O`, `N`, etc. (hand-tuned geometry / configured SMILES).
3. A bare RDKit-parseable SMILES — e.g. `O=C=O`, `[OH]`.
4. A chemical name — IUPAC or common, e.g. `carbon monoxide`, `methanol`. Names are resolved by OPSIN, which needs the `opsin` extra (`py2opsin`) plus **Java on PATH**. Without it, names fail; SMILES and labels still work.

Prefer `smiles:<SMILES>` or a known label when unambiguous. Use a name only when OPSIN is installed.

## Workflow

1. Confirm the parent slab file or saved structure id.
2. Resolve adsorbate input exactly; pass `smiles:<SMILES>` when the species is ambiguous.
3. Generate a bounded number of site candidates.
4. Save each adsorbed candidate as `extxyz`, `POSCAR`, and JSON metadata.
5. Validate atom count, minimum distance, tags, magmoms, site metadata, and placement warnings.
6. Report parent slab, adsorbate, candidate ids/files, site type, site sources, placement backend, atom count, and validation status.

## Defaults

- Use `max_sites=3` unless broader enumeration is requested.
- Keep `max_atoms=200` unless the user explicitly changes DFT-readiness.
- Leave placement height unset unless a chemically motivated height is supplied.
- Use `backend=auto`; let slabuilder try AutoAdsorbate/RDKit and fallback site detectors.
- Build a candidate table before large multi-material or multi-adsorbate generation.

## Weighted-alpha boundary

Use `backend=weighted_alpha` when the strict native geometry backend is requested.
With no explicit binary paths, MESA downloads the hash-pinned source-free Windows
bundle from the private GitHub Release and installs it in the verified versioned
cache. It fails closed and never falls back to legacy detectors. Phase 1 requires
pbc110, Cartesian +z alignment, selected top-layer height spread <= 0.25 A, and
complete upper-terrace population. `backend=auto` remains the legacy path.

For weighted-alpha sites, binding atom 0 is placed at
`anchor_position + normalize(direction) * contact_anchor_radius`; multi-atom
adsorbates are rigidly aligned to that normal and a minimum-image collision check
is mandatory. `--height` is ignored on this path and retains its old meaning for
legacy backends. See `../../../WEIGHTED_ALPHA_BACKEND.md` for distribution,
configuration, schema, provenance, and verification gates.

## Output Convention

Each generated structure carries a tag + metadata contract that downstream
relaxation and `inspect-surface-sites` rely on. Do not strip or overwrite it.

ASE tags (`atoms.get_tags()`):

- `0` — fixed slab atom
- `1` — relaxable slab atom
- `2` — adsorbate atom

`atoms.info` keys written alongside:

- `slab_atom_count`, `adsorbate_atom_count`
- `fixed_slab_tag` / `relaxable_slab_tag` / `adsorbate_tag` (the integer values above)
- `adsorption_site_indices` — comma-separated slab-atom indices anchoring the site
- `adsorption_site_atom_count`

The adsorption-site anchor atoms live in `info`/metadata, **not** in a tag,
because a site tag would overwrite the fixed/relaxable slab state. Read site
membership from the metadata fields or the `inspect-surface-sites` packet
outputs, not by guessing from coordinates.

## Boundaries

- Do not build the clean slab here except to state that `build-slab-models` is required first.
- Do not generate diffusion or dissociation endpoint pairs here.
- Do not claim adsorption energies unless a calculation workflow actually ran.
