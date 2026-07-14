---
name: import-bulk-structure
description: Import or register recipe-backed bulk crystal structures before any relaxation or slab generation. Use when Codex needs a Materials Project bulk structure, a local crystallographic bulk file, or a code-generated bulk unit cell prepared as the source artifact for bulk optimization while preserving source metadata such as MP identifiers and initial magnetic moments.
---

For MESA end-to-end use, read `SKILL/modeling/workflow.md` before applying this skill.

# Import Bulk Structure

## Scope

Use this skill to create the unoptimized bulk-source artifact that precedes bulk
optimization. Stop after writing or registering the source bulk structure and
metadata.

This skill owns Materials Project retrieval at the modeling-skill level. Slab
building must not fetch Materials Project structures directly.

Do not optimize the bulk, build slabs, place adsorbates, run calculations, or
choose a calculation backend in this skill.

## Inputs

Start only from recipe-authorized requirements:

- a Materials Project identifier such as `mp-126`;
- a formula, chemical system, or element set when the recipe authorizes MP
  candidate selection;
- a local crystallographic bulk file such as POSCAR, CIF, or extxyz;
- a code-generated bulk unit cell produced by another recipe-backed step.

## Workflow

1. Confirm the source is authorized by the recipe and execution plan.
2. Import or register the bulk structure.
   - For Materials Project sources, use the project Materials Project access
     path through the vendored `slabuilder.fetch_bulk_structures` API.
   - For local or code-generated sources, copy or link the exact source bulk
     artifact into the recipe-local execution structure directory.
3. Record source metadata before any optimization:
   - source type: `materials_project`, `local_file`, or `code_generated`;
   - source identifier such as `mpid`, file path, or generator command;
   - formula and composition;
   - MP stability metadata when available, such as `energy_above_hull` and
     `formation_energy`;
   - MP-provided `initial_magmoms` when present;
   - import timestamp or command provenance.
4. Write an unoptimized bulk structure artifact and sidecar metadata.
5. Hand the artifact to the calculation workflow for bulk optimization under the
   root calculation policy.

## Materials Project Metadata

Preserve MP-derived site metadata instead of treating MP as only a coordinate
source. In particular, keep `initial_magmoms` aligned to the imported structure
sites when MP provides them. Downstream calculation setup may use these values as
initial magnetic moments.

If the import chooses among multiple MP candidates, record every candidate that
was considered and the explicit selection reason. Do not let slab generation
silently choose a different MP candidate later.

## Handoff Contract

Before handing the bulk to optimization, provide:

- unoptimized bulk structure path;
- source metadata path;
- recipe and procedure identifiers;
- source identifier, including MP id when applicable;
- candidate-selection record when applicable;
- preserved site metadata such as `initial_magmoms` when present;
- caveats or unsupported source metadata.

## Boundaries

- Do not run bulk optimization in this skill.
- Do not build a slab in this skill.
- Do not fetch Materials Project structures from `build-slab-models`.
- Do not choose a calculation backend here; inherit the active calculation
  policy from the root workflow during the later calculation step.
