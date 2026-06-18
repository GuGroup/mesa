---
name: build-slab-models
description: Build DFT-ready clean slab models with slabuilder. Use when Codex needs to fetch or select Materials Project bulk structures, generate Miller-index slabs, choose terminations, tune target atom count, lateral size, slab thickness, supercell repeats, layer counts, fix bottom support layers by fraction or explicit layer count, and validate clean slab quality before adsorption or calculation workflows.
---

# Build Slab Models

## Scope

Use this skill to generate clean slabs only. Stop at validated slab files and metadata. Use `place-surface-adsorbates` after this skill when the next step is adsorption-site identification and adsorbate placement.

The `slabuilder` engine this skill drives is vendored in this repo (`./slabuilder`) and installed with the project, so no external checkout is required.

## Prerequisite

Bulk structures are fetched from the Materials Project, so an API key must be set as the `MP_API_KEY` or `PMG_MAPI_KEY` environment variable (or in a `.env` file in the working directory). Generation fails immediately without it.

## Quick Start

Use the bundled script for a direct Python workflow. Script paths are relative
to this skill directory.

Minimal required options:

```bash
mamba run -n modeling python scripts/build_slab_model.py \
  --formula Pt \
  --miller 1 1 1
```

Full option example:

This example shows every available option. Omit `--all-terminations` when you
want `--termination` to select only one termination. Omit
`--allow-nonstoichiometric` for the default stoichiometric-only policy.

```bash
mamba run -n modeling python scripts/build_slab_model.py \
  --formula Pt \
  --miller 1 1 1 \
  --search-mode formula \
  --max-results 5 \
  --entry-index 0 \
  --backend auto \
  --prefer-symmetry \
  --target-n-atoms 100 \
  --target-lateral-size 10.0 \
  --target-slab-thickness 8.0 \
  --vacuum 15.0 \
  --supercell-na 2 \
  --supercell-nb 2 \
  --n-layers 6 \
  --fix-layers 2 \
  --fix-ratio 0.4 \
  --termination 0 \
  --all-terminations \
  --allow-nonstoichiometric \
  --max-atoms 200 \
  --min-distance 0.5 \
  --outdir structures/Pt_111
```

## Keyword Reference

| Keyword | Required | Meaning |
| --- | --- | --- |
| `--formula` | yes | Formula, chemical system, element set, or `mp-*` id to fetch from Materials Project. |
| `--miller H K L` | yes | Surface Miller index, e.g. `1 1 1`. |
| `--search-mode` | no | Materials Project lookup mode: `formula`, `material_id`, `chemsys`, or `elements`; omitted values auto-detect `mp-*` ids. |
| `--max-results` | no | Number of MP bulk candidates fetched before slabuilder sorting. |
| `--entry-index` | no | Candidate index after sorting; use this when the lowest-energy candidate is not desired. |
| `--backend` | no | Slab backend: `auto`, `catkit`, `pymatgen`, or `surfaxe`. |
| `--prefer-symmetry` | no | In `auto` mode, prefer pymatgen symmetry/non-polar filtering. |
| `--target-n-atoms` | no | Target total atom count for automatic layer and supercell selection. |
| `--target-lateral-size` | no | Target in-plane a/b lengths in Angstrom. |
| `--target-slab-thickness` | no | Target material thickness in Angstrom, excluding vacuum. |
| `--vacuum` | no | Vacuum thickness in Angstrom. |
| `--supercell-na` | no | Explicit repeat along the first surface lattice vector. |
| `--supercell-nb` | no | Explicit repeat along the second surface lattice vector. |
| `--n-layers` | no | Explicit slab layer count override. |
| `--fix-layers` | no | Explicit number of bottom layers to fix; overrides `--fix-ratio`. |
| `--fix-ratio` | no | Fraction of material thickness fixed from the bottom. |
| `--termination` | no | Termination index to save when `--all-terminations` is not used. |
| `--all-terminations` | no | Save every generated termination. |
| `--allow-nonstoichiometric` | no | Save O-rich/O-poor or otherwise non-stoichiometric terminations; without this flag, only terminations matching the bulk reduced formula are saved. |
| `--max-atoms` | no | Validation limit for DFT-ready atom count. |
| `--min-distance` | no | Validation threshold for too-close atoms in Angstrom. |
| `--outdir` | no | Output directory for extxyz, POSCAR, and metadata files. |

## Workflow

1. Confirm material, Miller index, and DFT-readiness policy.
2. Fetch/select the bulk. Use a specific MP id when supplied; otherwise select the lowest energy-above-hull candidate returned by slabuilder.
3. Generate slabs with target-based sizing.
4. Save the selected termination or all terminations as `extxyz`, `POSCAR`, and JSON metadata.
5. Validate atom count, cell sanity, minimum distance, tags, and metadata.
6. Report MP id, Miller index, termination, backend, atom count, lateral lengths, slab thickness, vacuum, fixed atom count, validation status, and output paths.

## Defaults

- Keep `max_atoms=200` unless the user explicitly asks for a larger non-DFT-ready model.
- Use target-based sizing: `target_n_atoms=100`, `target_lateral_size=10`, `target_slab_thickness=8`, `vacuum=15`.
- Leave `backend=auto` unless the task requires `catkit`, `pymatgen`, or `surfaxe`.
- Bottom fixing defaults to `--fix-ratio 0.4`: the bottom 40% of the slab's material thickness is fixed, measured in c-axis fractional coordinates (tilt-safe, independent of added vacuum). Change the fraction with `--fix-ratio`, or pass `--fix-layers N` to fix an explicit layer count instead (overrides the ratio).
- Save one termination with `--termination N` (default 0) or every distinct termination with `--all-terminations`.
- Save only stoichiometric terminations by default. In the CatKit backend this uses CatKit's `stoich` layer mode; `--allow-nonstoichiometric` switches CatKit to `trim` so O-rich/O-poor or reconstructed surface compositions can be saved intentionally.
- Prefer automatic layer selection. Use explicit `--n-layers`, `--supercell-na`, or `--supercell-nb` only when requested or needed.
- Select the bulk candidate with `--entry-index` (default 0) after `--max-results` fetches; use `--search-mode` / a `mp-…` id for exact lookups.
- Ask before generation when bulk candidate, termination, or atom-count policy is scientifically ambiguous.

## Boundaries

- Do not place adsorbates in this skill.
- Do not submit MLIP/VASP calculations in this skill.
- Do not claim adsorption energies, surface energies, or reaction barriers from generated structures alone.
