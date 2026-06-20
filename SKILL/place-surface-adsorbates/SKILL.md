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
  --slab structures/Pt_111/Pt_mp-126_111_term0_POSCAR.vasp \
  --adsorbate CO
```

Full option example:

This example shows every available option.

```bash
mamba run -n modeling python scripts/place_surface_adsorbates.py \
  --slab structures/Pt_111/Pt_mp-126_111_term0_POSCAR.vasp \
  --adsorbate CO \
  --max-sites 3 \
  --height 2.0 \
  --backend auto \
  --write-extxyz \
  --max-atoms 120 \
  --min-distance 0.5 \
  --outdir structures/Pt_111_CO
```

## Keyword Reference

| Keyword | Required | Meaning |
| --- | --- | --- |
| `--slab` | yes | Parent clean slab file, usually POSCAR/VASP from `build-slab-models`. |
| `--adsorbate` | yes | Adsorbate label, SMILES, `smiles:<SMILES>`, or chemical name. |
| `--max-sites` | no | Maximum adsorption-site candidates to place. |
| `--height` | no | Optional adsorbate anchor height above the site in Angstrom. |
| `--backend` | no | Site/placement backend: `auto`, `acat`, `catkit`, or `pymatgen`. |
| `--write-extxyz` | no | Also write extxyz files and POSCAR/extxyz index mapping metadata. Off by default. |
| `--max-atoms` | no | Validation limit for DFT-ready atom count after placement. |
| `--min-distance` | no | Validation threshold for too-close atoms in Angstrom. |
| `--outdir` | no | Output directory for POSCAR and metadata files. |

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
4. Save each adsorbed candidate as `POSCAR` and JSON metadata. Add `--write-extxyz` only when an extxyz artifact is needed.
5. Validate atom count, minimum distance, tags, magmoms, site metadata, and placement warnings.
6. Report parent slab, adsorbate, candidate ids/files, site type, site sources, placement backend, atom count, and validation status.

## Defaults

- Use `max_sites=3` unless broader enumeration is requested.
- Keep `max_atoms=120` unless the user explicitly changes DFT-readiness.
- Leave placement height unset unless a chemically motivated height is supplied.
- Use `backend=auto`; let slabuilder try AutoAdsorbate/RDKit and fallback site detectors.
- Build a candidate table before large multi-material or multi-adsorbate generation.

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
