---
name: build-gas-phase-models
description: Build neutral isolated gas-phase molecule structures for reaction reference calculations. Use when Codex needs POSCAR/metadata files for gas reservoirs or gas products such as H2(g), H2O(g), CO(g), CO2(g), NH3(g), NOx species, alcohols, or SMILES-defined molecules before VASP relax/static/frequency handoff.
---

# Build Gas Phase Models

## Scope

Use this skill to create neutral gas-phase starting structures only. It builds a
molecule from an existing slabuilder adsorbate/gas geometry resolver, centers it
in a cubic box, writes POSCAR and metadata, and stops.

Do not use this skill for slab generation, adsorbate placement on surfaces,
VASP input generation, relaxation, static energies, or frequency calculations.
Use `vasp-job` after this skill for calculation setup.

## Charge and Spin Boundary

This skill does not support charge or spin policy:

- no charge option;
- no multiplicity option;
- no spin-state inference;
- no `magmom` generation;
- no charged-cell or dipole-correction policy.

If a calculation needs spin or charge settings, set them explicitly in the
downstream `vasp-job` spec. Do not infer them here.

## Quick Start

Script paths are relative to this skill directory.

```bash
mamba run -n modeling python scripts/build_gas_phase_model.py \
  --species H2O \
  --outdir structures/gas/H2O
```

SMILES input:

```bash
mamba run -n modeling python scripts/build_gas_phase_model.py \
  --species 'smiles:O=C=O' \
  --label CO2 \
  --box-size 15.0 \
  --outdir structures/gas/CO2
```

## Keyword Reference

| Keyword | Required | Meaning |
| --- | --- | --- |
| `--species` | yes | Label, alias, raw SMILES, `smiles:<SMILES>`, or name supported by slabuilder's molecule resolver. |
| `--label` | no | Output label. Defaults to a safe name derived from `--species`. |
| `--box-size` | no | Cubic cell length in Angstrom. Default: `15.0`. |
| `--min-distance` | no | Minimum intramolecular distance sanity threshold. Default: `0.5`. |
| `--max-atoms` | no | Atom-count validation threshold. Default: `80`. |
| `--write-extxyz` | no | Also write an extxyz file. Off by default. |
| `--outdir` | no | Output directory. |

## Workflow

1. Resolve the gas molecule identity from reaction metadata or user input.
2. Build the molecule with `slabuilder.build_adsorbate_atoms`; do not implement
   a second molecule builder.
3. Put the molecule in a cubic box, centered in the cell.
4. Write POSCAR and JSON metadata.
5. Validate atom count, cell size, and minimum intramolecular distance.
6. Report paths and explicitly state that charge/spin and relax/freq are
   downstream `vasp-job` responsibilities.

## Output Contract

Each metadata file records:

- `kind: gas_molecule`;
- input species and output label;
- molecular formula and atom count;
- cubic box size and cell lengths;
- builder provenance copied from slabuilder;
- `charge_spin_policy: unsupported`;
- validation checks;
- POSCAR and optional extxyz paths.

## Boundaries

- Do not build slabs; use `build-slab-models`.
- Do not place this gas molecule on a surface; use `place-surface-adsorbates`.
- Do not create VASP INCAR/KPOINTS/POTCAR files; use `vasp-job`.
- Do not submit calculations from this skill.
