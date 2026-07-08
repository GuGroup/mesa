---
name: place-adsorbates-with-adsorbdiff
description: Plan, set up, run, and validate AdsorbDiff adsorbate placement workflows from AdeeshKolluru/AdsorbDiff for surface-adsorbate systems. Use when Codex receives a POSCAR slab plus an adsorbate request, must check AdsorbDiff adsorbate identities, tag/prepare slab atoms, decide placement and sampling settings that were formerly human choices, prepare OC20/OCP-style LMDB sampling inputs, generate diffusion sampling and MLFF relaxation commands, manage AdsorbDiff checkpoints, or integrate candidate adsorption geometries with MESA/MLIP relaxation and DFT handoff workflows.
---

# AdsorbDiff Placement

## Overview

Use this skill to turn the vendored AdsorbDiff research repository into a
repeatable agent workflow for adsorbate placement. Prefer the POSCAR-first
controller when the user provides a slab POSCAR. Use the LMDB workflow builder
directly only when an AdsorbDiff-compatible sampling LMDB already exists.

The vendored upstream repository is in `assets/AdsorbDiff` at commit
`8a905c7158e4973da76826e2b91bfd892ebbdcb1`.

## Workflow

1. If the user provides a POSCAR, read
   `references/poscar_adsorbate_frontend.md` and run
   `scripts/adsorbdiff_controller.py` first.
2. The controller must prepare the POSCAR, check the adsorbate, decide placement
   settings, and write `results/resolved_adsorbdiff_config.json`.
3. If candidate placement is requested, run the controller-generated
   `scripts/adsorbdiff_place_candidates.py` command inside a prepared
   AdsorbDiff environment.
4. If diffusion sampling is requested, read `references/adsorbdiff_workflow.md`
   and use `scripts/adsorbdiff_workflow.py` on the candidate LMDB or another
   explicit LMDB.
5. Treat AdsorbDiff outputs as candidate adsorption geometries. Pass selected
   candidates into UMA relaxation or the MESA DFT handoff skill for final
   relaxation/validation.

## POSCAR-First Controller

Create an input JSON like:

```json
{
  "poscar_path": "POSCAR",
  "workdir": "runs/adsorbdiff_poscar_case",
  "adsorbate": {
    "smiles": "*CO"
  },
  "surface": {},
  "placement": {},
  "sampling": {},
  "handoff": {}
}
```

Generate resolved settings and commands:

```bash
python scripts/adsorbdiff_controller.py --input adsorbdiff_poscar.input.json
```

The controller writes:

| Artifact | Purpose |
| --- | --- |
| `adsorbdiff_slab/POSCAR` | Normalized slab POSCAR with optional Selective Dynamics flags. |
| `results/adsorbdiff_tags.txt` | AdsorbDiff slab tags, one per POSCAR atom. |
| `results/adsorbdiff_poscar_metadata.json` | Parsed cell, formula, surface atom indices, tags, and warnings. |
| `results/adsorbate_check.json` | Adsorbate DB verification result. |
| `results/resolved_adsorbdiff_config.json` | Controller-owned decisions and next commands. |
| `results/adsorbdiff_workflow.input.json` | Input for the diffusion workflow builder. |

## LMDB Command Builder

Create an input JSON like:

```json
{
  "workdir": "runs/adsorbdiff_job",
  "ngpus": 1,
  "localize_configs": true,
  "sampling": {
    "dataset_src": "/path/to/sampling_lmdb",
    "checkpoint": "/path/to/PT_zeroshot_painn.pt",
    "config_yml": "configs/denoising/painn_so3.yml",
    "traj_dir": "samples/site0",
    "seed": 0
  },
  "conversion": {
    "enabled": true,
    "converter": "skill",
    "out_path": "samples/site0/final_struct_lmdb",
    "num_workers": 4
  },
  "relaxation": {
    "enabled": true,
    "dataset_src": "samples/site0/final_struct_lmdb",
    "checkpoint": "/path/to/gemnet_oc_base_s2ef_2M.pt",
    "config_yml": "configs/relaxation/gemnet_oc/gemnet_relax.yml",
    "traj_dir": "samples/site0/relaxations"
  }
}
```

Generate the dry-run plan:

```bash
python scripts/adsorbdiff_workflow.py --input adsorbdiff.input.json --workdir runs/adsorbdiff_job --output runs/adsorbdiff_job/results/adsorbdiff_plan.json
```

Execute only after the plan has no missing external inputs:

```bash
python scripts/adsorbdiff_workflow.py --input adsorbdiff.input.json --workdir runs/adsorbdiff_job --execute
```

## Guardrails

- Do not run `assets/AdsorbDiff/run.py` unchanged; it contains upstream
  author-local absolute paths.
- Do not skip adsorbate checking when the user gives only a formula unless the
  controller records the deterministic tie-breaker it used.
- Do not assume POSCAR atom tags exist. POSCAR prep must write sidecar tag
  metadata because POSCAR cannot preserve ASE tags directly.
- Do not train or download large datasets/checkpoints unless the user asks for
  that explicitly.
- Prefer PaiNN diffusion checkpoints for faster inference unless the user needs
  EquiformerV2.
- Keep dataset/checkpoint paths explicit. Do not silently substitute a different
  OC20/OCP split.
- Let `scripts/adsorbdiff_workflow.py` localize upstream YAML configs by default
  so author-local `/home/jovyan/...` train/val dataset paths are removed before
  inference.
- For POSCAR-first workflows, let the controller infer surface side/thickness,
  candidate count, seed, diffusion config, GemNet validation, and handoff count
  unless the user gives a hard scientific or budget constraint.
- Do not generate `POTCAR` contents or VASP production inputs from this skill.
  Use downstream MESA DFT handoff skills for VASP preparation.
- Preserve AdsorbDiff and dependency license notices from `assets/AdsorbDiff`
  when copying or packaging outputs.

## Outputs

The command builder writes:

| Artifact | Purpose |
| --- | --- |
| `results/adsorbdiff_plan.json` | Structured MESA-style plan/status envelope. |
| `submit_adsorbdiff.sh` | Bash script containing sampling, LMDB conversion, and optional MLFF relaxation commands. |
| AdsorbDiff trajectory directory | Candidate sampled structures from diffusion. |
| `final_struct_lmdb` | Optional LMDB converted from predicted trajectories for relaxation. |
| relaxation trajectory directory | Optional MLFF-relaxed candidate structures. |
