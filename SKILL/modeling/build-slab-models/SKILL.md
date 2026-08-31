---
name: build-slab-models
description: Build DFT-ready clean slab models from an already optimized bulk structure with slabuilder. Use when Codex needs to generate Miller-index slabs, choose terminations, tune target atom count, lateral size, slab thickness, supercell repeats, layer counts, fix bottom support layers by fraction or explicit layer count, and validate clean slab quality before clean-slab optimization or adsorbate placement.
---

For MESA end-to-end use, read `SKILL/modeling/workflow.md` before applying this skill.

# Build Slab Models

## Scope

Use this skill to generate clean slabs only. Stop at validated slab files and
metadata. The higher-level surface order is defined in
`SKILL/modeling/workflow.md`.

The `slabuilder` engine this skill drives is vendored in this repo
(`ENVIRONMENT/build_tools/slabuilder`) and installed with the project, so no
external checkout is required.

This skill does not import source bulk structures, optimize the bulk, optimize
the clean slab, choose calculation backends, or place adsorbates.

## Bulk Source Policy

Slab generation must start from an accepted optimized bulk artifact.

- Use `--bulk-file <POSCAR|CIF|extxyz>` for the optimized bulk handoff.
- Use `import-bulk-structure` first to import, register, or directly create the
  source bulk, then complete the required bulk optimization under the root
  calculation policy, then run this skill with the optimized bulk file.
- For VASP-backed optimized bulk inputs, prefer volume-scan/EOS-derived cells
  when practical; accept other backend-authorized optimized bulk artifacts.
- Require a passed source-bulk validation result from `import-bulk-structure`.
- If `import-bulk-structure` carried forward multiple unresolved MP candidates
  (near-degenerate energy and no XRD match), run this skill once per optimized
  candidate bulk file rather than picking one. Output naming keys on the
  `--bulk-file` filename stem, so per-candidate slab sets do not collide as
  long as `import-bulk-structure`'s output-naming rule was followed (source id
  in the filename, never a generic stem). Return every candidate's slab set to
  the recipe-backed execution plan for resolution — the same handling this
  skill already uses for ambiguous terminations.

```bash
mamba run -n modeling python scripts/build_slab_model.py \
  --bulk-file path/to/optimized_bulk_POSCAR \
  --miller 1 1 1
```

## Quick Start

Script paths are relative to this skill directory.

Minimal required options:

```bash
mamba run -n modeling python scripts/build_slab_model.py \
  --bulk-file path/to/optimized_bulk_POSCAR \
  --miller 1 1 1
```

Full option example:

This example shows every common slab-generation option. Omit `--write-extxyz`
for the default POSCAR-only output policy. Use `--all-terminations` only for
deliberate enumeration; normal workflows omit `--termination` and let it
default to the recommended (dipole-safe/symmetric) termination, or pass an
explicit index only to deliberately override that recommendation.

```bash
mamba run -n modeling python scripts/build_slab_model.py \
  --bulk-file path/to/optimized_bulk_POSCAR \
  --miller 1 1 1 \
  --backend auto \
  --prefer-symmetry \
  --target-n-atoms 70 \
  --target-lateral-size 7.5 \
  --target-slab-thickness 8.0 \
  --vacuum 15.0 \
  --supercell-na 2 \
  --supercell-nb 2 \
  --n-layers 6 \
  --fix-layers 2 \
  --fix-ratio 0.48 \
  --termination 0 \
  --allow-nonstoichiometric \
  --write-extxyz \
  --max-atoms 120 \
  --min-distance 0.5 \
  --outdir structures/Pt_111
```

## Keyword Reference

| Keyword | Required | Meaning |
| --- | --- | --- |
| `--bulk-file` | yes | Optimized bulk structure file (POSCAR/CIF/extxyz/...). This is the only valid bulk input for slab generation. |
| `--miller H K L` | yes | Surface Miller index, e.g. `1 1 1`. |
| `--backend` | no | Slab backend: `auto`, `catkit`, `pymatgen`, or `surfaxe`. |
| `--prefer-symmetry` | no | In `auto` mode, prefer pymatgen symmetry/non-polar filtering. |
| `--target-n-atoms` | no | Target total atom count for automatic layer and supercell selection. |
| `--target-lateral-size` | no | Target in-plane a/b lengths in Angstrom. |
| `--target-slab-thickness` | no | Target material thickness in Angstrom, excluding vacuum. |
| `--vacuum` | no | Vacuum thickness in Angstrom. |
| `--supercell-na` | no | Explicit repeat along the first surface lattice vector. |
| `--supercell-nb` | no | Explicit repeat along the second surface lattice vector. |
| `--n-layers` | no | Explicit slab layer count override. |
| `--preserve-bulk-cell` | no | Skip conventional/primitive reduction; slice `--bulk-file` exactly as given, with `--miller` interpreted against that exact lattice. See **Bulk Cell Standardization** below. |
| `--fix-layers` | no | Explicit number of bottom layers to fix; overrides `--fix-ratio`. |
| `--fix-ratio` | no | Fraction of material thickness fixed from the bottom. |
| `--termination` | no | Termination index to save when `--all-terminations` is not used. Defaults to the recommended (nonpolar/dipole-safe, symmetric, stoichiometric) termination among all generated ones when omitted — not a positional index-0 pick. |
| `--all-terminations` | no | Advanced/diagnostic mode to save every generated termination. Prefer one termination per run. |
| `--allow-nonstoichiometric` | no | Save O-rich/O-poor or otherwise non-stoichiometric terminations; without this flag, only terminations matching the bulk reduced formula are saved. |
| `--write-extxyz` | no | Also write extxyz files and POSCAR/extxyz index mapping metadata. Off by default. |
| `--max-atoms` | no | Validation limit for DFT-ready atom count. |
| `--min-distance` | no | Validation threshold for too-close atoms in Angstrom. |
| `--outdir` | no | Output directory for POSCAR and metadata files. |

## Bulk Cell Standardization

By default (`--preserve-bulk-cell` not set), `slabuilder` reduces `--bulk-file`
to its conventional/primitive form (spglib symmetry analysis) before slicing,
for every backend — including CatKit, which does this internally. This is a
pure geometry-and-species analysis; it does not consider per-site properties
such as `magmom`, so passing a large or intentionally-built supercell as
`--bulk-file` has no effect by default — it is reduced back down before
generation.

Pass `--preserve-bulk-cell` when the supplied bulk encodes site-level physics
that this reduction could silently collapse or misassign — e.g.
antiferromagnetic ordering (alternating `magmom` on otherwise
crystallographically-equivalent sites), a dopant supercell, or a defect cell.
With this flag:

- No conventional/primitive reduction is applied, by this skill or by CatKit.
- `--miller H K L` is interpreted against the exact lattice vectors of
  `--bulk-file`, not a re-derived standard cell — Miller indices are only
  physically meaningful relative to the basis they are expressed in, so a
  non-standard supercell needs indices re-expressed in its own basis.
- `standardize_bulk` is recorded in the output metadata and
  `termination_summary.json` for provenance.

`generate_slab` also warns automatically when `--bulk-file` carries a
`magmom` pattern that differs within the same species (a signal of AFM-like
ordering) while `--preserve-bulk-cell` is not set — that is the risky default
combination. Do not silence or ignore this warning; either confirm the
reduction is safe for this material or rerun with `--preserve-bulk-cell`.

## Workflow

1. Confirm the recipe-authorized optimized bulk artifact, Miller index, and
   handoff metadata.
2. Start from the optimized bulk artifact with `--bulk-file`. Preserve inherited
   source metadata such as MP id and initial magnetic moments in sidecar
   metadata and handoff notes; do not refetch MP in this skill.
3. Generate compact slabs with target-based sizing.
4. Screen terminations before selection when the surface is multicomponent,
   oxide, nitride, oxynitride, carbide, sulfide, perovskite, polar, or otherwise
   chemically ambiguous. Use `--all-terminations` and inspect
   `termination_summary.json`. The heuristic `score`/`recommended_termination`
   here is a safety triage, not an energy ranking. When an ambiguous surface
   requires energy-based screening, return the top candidates to the
   recipe-backed execution plan; do not run that calculation in this skill.
5. Save exactly one selected termination as `POSCAR` and JSON metadata:
   omitting `--termination` saves the recommended (dipole-safe/symmetric)
   termination automatically; pass `--termination N` only to deliberately
   override it, e.g. when recipe-backed energy screening has chosen a
   different one.
6. Validate atom count, cell sanity, minimum distance, tags, and metadata.
7. Report source bulk path, inherited source identifiers, Miller index,
   termination, backend, atom count, lateral lengths, slab thickness, vacuum,
   fixed atom count, validation status, warnings, and output paths.

## Defaults

- Keep `max_atoms=120` unless the user explicitly asks for a larger
  non-DFT-ready model.
- Use compact target-based sizing: `target_n_atoms=70`,
  `target_lateral_size=7.5`, `target_slab_thickness=8`, `vacuum=15`.
- Leave `backend=auto` unless the task requires `catkit`, `pymatgen`, or
  `surfaxe`.
- Prefer compact, square-like in-plane cells. Slabuilder estimates an
  appropriate 2D copy count from the initial surface unit cell's area and atom
  count, then scores non-diagonal 2D transforms for near-90° angle, similar a/b
  lengths, target side length/area, and atom-count control. In CatKit workflows
  this scoring is repeated against the actual CatKit surface cell before
  writing POSCAR, so an estimator-good matrix that makes an oblique final cell
  should be rejected when a better square-like alternative is available.
- Bottom fixing defaults to `--fix-ratio 0.48`: the bottom 48% of the slab's
  material thickness is fixed, measured in c-axis fractional coordinates
  (tilt-safe, independent of added vacuum). Change the fraction with
  `--fix-ratio`, or pass `--fix-layers N` to fix an explicit layer count instead
  (overrides the ratio).
- Leave `--termination` unset by default. It then saves the recommended
  termination — lowest-penalty among ALL generated terminations, favoring
  nonpolar/dipole-safe, symmetric top/bottom, and stoichiometric — computed
  from the full termination set even though only one is written to disk. This
  is not a positional index-0 pick.
- Pass `--termination N` only to deliberately override the recommendation
  (e.g. recipe-backed energy screening chose a different one). An override
  that differs from the recommendation, or a tie among equally-good
  candidates, or no safe candidate existing at all, prints a `WARNING:`
  banner to stderr in addition to `selection_warnings` in the JSON output —
  do not treat a clean-looking stdout summary as sufficient without checking
  stderr.
- For ambiguous surfaces (see Workflow step 4), still run `--all-terminations`
  and inspect `termination_summary.json` rather than trusting the single
  auto-picked termination, since the heuristic score is a safety triage, not
  an energy ranking.
- Save POSCAR and metadata by default. Add `--write-extxyz` only when an extxyz
  artifact or POSCAR/extxyz index map is needed.
- Save only stoichiometric terminations by default. In the CatKit backend this
  uses CatKit's `stoich` layer mode; `--allow-nonstoichiometric` switches CatKit
  to `trim` so O-rich/O-poor or reconstructed surface compositions can be saved
  intentionally.
- Prefer automatic layer selection. Use explicit `--n-layers`, `--supercell-na`,
  or `--supercell-nb` only when requested or needed.
- Leave `--preserve-bulk-cell` unset unless the bulk carries site-level physics
  (magnetic ordering, dopant/defect pattern) that reduction would erase; see
  **Bulk Cell Standardization**.
- Ask before generation when termination or atom-count policy is scientifically
  ambiguous.

## Handoff Contract

Before handing a clean slab back for clean slab optimization and later adsorbate
placement, have:

- optimized bulk path and relaxation provenance;
- source bulk identifier such as MP id, local path, or direct-creation
  provenance when applicable;
- preserved source metadata, including initial magnetic moments when present;
- Miller index;
- selected termination index;
- `termination_summary.json` for ambiguous surfaces;
- clean slab `POSCAR` and metadata;
- validation status and warnings.

## Boundaries

- Do not import or fetch source bulk structures in this skill.
- Do not perform bulk optimization or clean slab optimization in this skill.
- Do not choose a calculation backend in this skill.
- Do not place adsorbates in this skill.
- Do not submit calculation jobs in this skill.
- Do not claim adsorption energies, surface energies, or reaction barriers from generated structures alone.
