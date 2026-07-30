---
name: import-bulk-structure
description: Resolve recipe-backed bulk crystal source structures before any relaxation or slab generation. Use when Codex needs to import a Materials Project bulk structure, register a local crystallographic bulk file, register an existing code-generated bulk unit cell, or directly create a bulk unit cell from recipe-provided crystallographic instructions while preserving source metadata such as MP identifiers and initial magnetic moments.
---

For MESA end-to-end use, read `SKILL/modeling/workflow.md` before applying this skill.

# Import Bulk Structure

## Scope

Use this skill to create the unoptimized bulk-source artifact that precedes bulk
optimization. Stop after writing, registering, or directly creating the source
bulk structure and metadata.

This skill owns source-bulk resolution at the modeling-skill level. That
includes Materials Project retrieval, local/source artifact registration, and
direct bulk unit-cell creation when no importable source exists. Slab building
must not fetch Materials Project structures directly.

Do not optimize the bulk, build slabs, place adsorbates, run calculations, or
choose a calculation backend in this skill.

## Inputs

Start only from recipe-authorized requirements:

- a Materials Project identifier such as `mp-126`;
- a formula, chemical system, or element set when the recipe authorizes MP
  candidate selection;
- a local crystallographic bulk file such as POSCAR, CIF, or extxyz;
- a code-generated bulk unit cell produced by another recipe-backed step;
- recipe-provided crystallographic instructions sufficient to create a bulk
  unit cell directly, such as composition, lattice parameters, prototype,
  Wyckoff/site definitions, or a deterministic structure-generation rule.

## Workflow

1. Confirm the source is authorized by the recipe and execution plan.
2. Resolve the source bulk in this precedence order:
   - For Materials Project sources, use the project Materials Project access
     path through the vendored `slabuilder.fetch_bulk_structures` API.
   - For local or code-generated sources, copy or link the exact source bulk
     artifact into the recipe-local execution structure directory.
   - If no importable source artifact exists, create the bulk unit cell directly
     from recipe-provided crystallographic instructions and record the generator
     inputs. Do not guess missing lattice, prototype, site, oxidation-state, or
     magnetic information.
   - If the recipe lacks enough information to import, register, or create the
     bulk, stop and return to recipe generation, execution planning, or
     E-level manifest-diagnosis-repair handling.
3. Record source metadata before any optimization:
   - source type: `materials_project`, `local_file`, `code_generated`, or
     `direct_created`;
   - source identifier such as `mpid`, file path, or generator command;
   - formula and composition;
   - MP stability metadata when available, such as `energy_above_hull` and
     `formation_energy`;
   - MP-provided `initial_magmoms` when present;
   - import, registration, or creation timestamp and command provenance.
4. Write an unoptimized bulk structure artifact and sidecar metadata.
5. Hand the artifact to the calculation workflow for bulk optimization under the
   active project profile's calculation policy.

## Direct Bulk Creation

Create a bulk unit cell directly only when the recipe provides enough
crystallographic detail to make the structure deterministic. Record the exact
inputs used to create the cell and label the source type as `direct_created`.

Do not use direct creation to fill scientific gaps. If a recipe names only a
composition without lattice/prototype/site information and does not authorize a
Materials Project or local source, stop, record and diagnose the failed E
attempt, and record missing evidence only after repair handling terminates.

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
- direct-creation inputs and generator provenance when applicable;
- preserved site metadata such as `initial_magmoms` when present;
- caveats or unsupported source metadata.

## Boundaries

- Do not run bulk optimization in this skill.
- Do not build a slab in this skill.
- Do not fetch Materials Project structures from `build-slab-models`.
- Do not choose a calculation backend here; inherit the active calculation
  policy from the project profile during the later calculation step.
