---
name: build-gas-phase-models
description: Build neutral isolated gas-phase molecule structures for reaction reference calculations. Use when Codex needs POSCAR/metadata files for gas reservoirs or gas products such as H2(g), H2O(g), CO(g), CO2(g), NH3(g), NOx species, alcohols, or SMILES-defined molecules before downstream relaxation, static-energy, or frequency handoff.
---

For MESA end-to-end use, read `SKILL/modeling/workflow.md` before applying this skill.

# Build Gas Phase Models

## Scope

Use this skill to create neutral gas-phase starting structures only. It builds a
molecule from an existing slabuilder adsorbate/gas geometry resolver, centers it
in a slightly asymmetric orthorhombic cell, writes POSCAR and metadata, and stops.

Do not use this skill for slab generation, adsorbate placement on surfaces,
calculation input generation, relaxation, static energies, or frequency calculations.
Use the calculation workflow after this skill for calculation setup under the
active project profile's calculation policy.

## Charge and Spin Boundary

This skill builds a **neutral** geometry and does not infer charge. It does,
however, provide a **spin-multiplicity reference** so downstream calculation setup can
set spin-related inputs without guessing:

- charge is never inferred (neutral cell only);
- spin multiplicity (2S+1) defaults to a closed-shell singlet (1); set
  `--spin-multiplicity` for open-shell references (e.g. `--spin-multiplicity 3`
  for an O2 triplet). The formula is not used to guess a multiplicity;
- the metadata `spin_reference` block reports `recommended_ispin`,
  `recommended_nupdown`, and `recommended_total_magmom` for downstream calculation setup to apply;
- a `dipole_hint` block flags likely-polar molecules (recommending
  a dipole correction in downstream calculation setup).

The calculation workflow owns the final calculator-specific inputs. It may read
`spin_reference`/`dipole_hint` and translate them under the active project
profile's calculation policy. This skill never writes calculator execution
inputs.

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
  --cell-size 20 20 21 \
  --outdir structures/gas/CO2
```

## Keyword Reference

| Keyword | Required | Meaning |
| --- | --- | --- |
| `--species` | yes | Label, alias, raw SMILES, `smiles:<SMILES>`, or name supported by slabuilder's molecule resolver. |
| `--label` | no | Output label. Defaults to a safe name derived from `--species`. |
| `--cell-size A B C` | no | Orthorhombic gas-cell lengths in Angstrom. Default: `20 20 21`. |
| `--box-size` | no | Backward-compatible cubic cell length in Angstrom; overrides `--cell-size` when set. |
| `--spin-multiplicity` | no | Gas-phase spin multiplicity (2S+1). Default: closed-shell singlet (`1`). |
| `--min-distance` | no | Minimum intramolecular distance sanity threshold. Default: `0.5`. |
| `--max-atoms` | no | Atom-count validation threshold. Default: `80`. |
| `--write-extxyz` | no | Also write an extxyz file. Off by default. |
| `--outdir` | no | Output directory. |

## Workflow

1. Resolve the gas molecule identity from reaction metadata or user input.
2. Build the molecule with `slabuilder.build_adsorbate_atoms`; do not implement
   a second molecule builder.
3. Put the molecule in a `20 20 21` Å orthorhombic cell by default, centered in the cell.
4. Write POSCAR and JSON metadata.
5. Validate atom count, cell size, and minimum intramolecular distance.
6. Report paths and explicitly state that charge/spin and relax/freq are
   downstream calculation-workflow responsibilities.

## Output Contract

Each metadata file records:

- `kind: gas_molecule`;
- input species and output label;
- molecular formula and atom count;
- gas-cell size (default `20 20 21` Å) and cell lengths;
- builder provenance copied from slabuilder;
- `charge_spin_policy` (charge not inferred) plus a `spin_reference` block
  (multiplicity, `recommended_ispin`/`nupdown`/`total_magmom`);
- `dipole_hint` (likely-polar flag plus downstream dipole-correction hint);
- validation checks;
- POSCAR and optional extxyz paths.

## Boundaries

- Do not build slabs; use `build-slab-models`.
- Do not place this gas molecule on a surface; use `place-adsorbates-with-adsorbdiff`.
- Do not create calculator execution inputs; use the calculation workflow.
- Do not submit calculations from this skill.
