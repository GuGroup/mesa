---
name: import-bulk-structure
description: Resolve bulk crystal source structures before any relaxation or slab generation. Use when Codex needs to import a Materials Project bulk structure, register a local crystallographic bulk file, register an existing code-generated bulk unit cell, or directly create a bulk unit cell from supplied crystallographic instructions while preserving source metadata such as MP identifiers and initial magnetic moments.
---

For MESA end-to-end use, read `SKILL/modeling/workflow.md` before applying this skill.

# Import Bulk Structure

## Scope

Create the unoptimized bulk-source artifact that precedes bulk optimization.
Stop after writing, registering, or creating the source bulk and its metadata.
Do not optimize the bulk, build slabs, place adsorbates, run calculations, or
choose a calculation backend here. This skill owns all Materials Project
retrieval — `build-slab-models` must never fetch MP structures directly.

## Inputs

Use the source information supplied for the task:

- a Materials Project identifier such as `mp-126`;
- a formula, chemical system, or element set when the task calls for Materials Project lookup;
- a local crystallographic bulk file (POSCAR, CIF, extxyz);
- a code-generated bulk unit cell from another modeling step;
- supplied crystallographic instructions sufficient to create a bulk
  cell directly (composition, lattice parameters, prototype, Wyckoff/site
  definitions, or a deterministic generation rule).

## Materials Project Retrieval

Use the vendored `slabuilder.fetch_bulk_structures` API only — never call
`mp-api` directly, and never fetch MP structures outside this skill.
`MP_API_KEY` or `PMG_MAPI_KEY` must be set in `DEPENDENCY/.env`.

```python
from slabuilder import fetch_bulk_structures

# Known mp-id: no ambiguity, always prefer this when the task supplies one.
entries = fetch_bulk_structures("mp-2815", search_mode="material_id")

# Composition only: returns every matching candidate, sorted ascending by
# energy_above_hull (pass sort_by="formation_energy" to sort by that instead).
entries = fetch_bulk_structures("MoS2", search_mode="formula", max_results=25)
# search_mode also accepts "chemsys" (e.g. "Mo-S") and "elements" (["Mo", "S"])

for e in entries:
    print(e.mpid, e.space_group_symbol, e.space_group_number,
          e.energy_above_hull, e.formation_energy, e.theoretical)
```

### Candidate selection order

1. **Exact mp-id given** — fetch with `search_mode="material_id"` and stop; no
   selection needed.
2. **Composition given** — fetch by `formula` (or `chemsys`/`elements`) first
   to see whether more than one candidate exists at all.
3. **Multiple candidates** — check `space_group_symbol`/`space_group_number`
   on each. If the input names a space group, prototype, or polytype (e.g.
   "2H-MoS2", `P6_3/mmc`), match it explicitly and record the match. Never
   pick `entries[0]` on formula alone when candidates differ in space group.
4. **Still ambiguous** (no specified space group, or several
   candidates share one) — compare `energy_above_hull` and
   `formation_energy`. Prefer the lowest `energy_above_hull`. If the leading
   candidates are near-degenerate (e.g. within ~0.01 eV/atom) but differ in
   space group, do not auto-pick — stop and record the tie for the user to resolve.
5. If supplied XRD peak positions are available, compare them with simulated
   peaks from the candidate structures. Report any remaining ambiguity.

Record every candidate considered and the explicit selection reason,
regardless of outcome. Do not let slab generation silently choose a different
MP candidate later.

Preserve MP-derived site metadata beyond coordinates: keep `initial_magmoms`
aligned to the imported sites when MP provides them — downstream calculation
setup may use these as initial magnetic moments.

## Workflow

1. Identify the source and required crystallographic information.
2. Resolve the source bulk in this precedence order:
   - Materials Project: fetch and select per **Materials Project Retrieval**.
   - Local/code-generated: copy or link the exact source artifact into the
     requested output directory.
   - No importable source: create the bulk cell directly from recipe-provided
     crystallographic instructions (see **Direct Bulk Creation**). Do not
     guess missing lattice, prototype, site, oxidation-state, or magnetic
     information.
   - Not enough information to import, register, or create: report which input is missing.
3. Record source metadata before any optimization:
   - source type: `materials_project`, `local_file`, `code_generated`, or
     `direct_created`;
   - source identifier (`mpid`, file path, or generator command);
   - formula and composition;
   - MP stability metadata when available (`energy_above_hull`,
     `formation_energy`, `space_group_symbol`/`number`);
   - MP-provided `initial_magmoms` when present;
   - import/registration/creation timestamp and command provenance.
4. Write an unoptimized bulk structure artifact and sidecar metadata. Name the
   artifact file `{formula}_{source_id}` unless the user specifies otherwise
   — `source_id` is the MP id for `materials_project` sources, the original
   file stem for `local_file`, or a short generator label for
   `code_generated`/`direct_created`. Never use a generic/constant stem (e.g.
   `POSCAR`, `bulk`) — `build-slab-models` derives its own output naming from
   this file's stem, so a generic name causes parallel candidates for the same composition to silently collide downstream.
5. Run `scripts/validate_bulk_structure.py` on every saved source bulk. Keep
   the JSON result and stop if it is rejected.
6. Hand the accepted artifact to the calculation workflow for bulk optimization using the requested backend.

## Direct Bulk Creation

Create a bulk cell directly only when the task provides enough
crystallographic detail to make the structure deterministic. Record the exact
inputs used and label the source type `direct_created`.

Run direct-creation generators within this skill, record the command, and
validate the output:

```bash
mamba run -n modeling python scripts/validate_bulk_structure.py \
  --structure structures/CoRe_direct.vasp \
  --output structures/CoRe_direct.bulk_validation.json
```

The validator requires a finite, nonempty 3D periodic cell, minimum distance
`>= 0.5 Å`, and longest/shortest cell-vector ratio `<= 5.0`.

If only the composition is known and no source structure or crystallographic
details are available, report the missing structure information.

## Handoff Contract

Before handing the bulk to optimization, provide:

- unoptimized bulk structure path and source metadata path;
- source identifier, including MP id when applicable;
- candidate-selection record (all candidates considered, selection reason)
  when applicable — when multiple candidates are carried forward unresolved,
  list every parallel bulk artifact path with the shared candidate-selection
  record instead of a single winner;
- direct-creation inputs and generator provenance when applicable;
- passed validation report bound to the structure by SHA-256;
- preserved site metadata such as `initial_magmoms` when present;
- caveats or unsupported source metadata.

## Boundaries

- Do not run bulk optimization, build a slab, or place adsorbates here.
- Do not hand off a source bulk with a missing or rejected validation result.
- Do not fetch Materials Project structures from `build-slab-models`.
- Use the task's backend settings during any subsequent calculation.
