# POSCAR And Adsorbate Frontend

Use this reference when the user starts from a POSCAR rather than an existing
OC20/OCP LMDB.

## Roles

| Layer | File | Responsibility |
| --- | --- | --- |
| Controller | `scripts/adsorbdiff_controller.py` | Decide surface tagging, placement mode, site count, augmentation count, interstitial gap, and workflow handoff from POSCAR plus adsorbate request. |
| POSCAR prep | `scripts/poscar_to_adsorbdiff_input.py` | Normalize the POSCAR, tag slab atoms, write Selective Dynamics flags, and emit tag metadata. |
| Adsorbate check | `scripts/adsorbate_checker.py` | Verify adsorbate id, SMILES, or formula against AdsorbDiff `adsorbates.pkl`. |
| Candidate placement | `scripts/adsorbdiff_place_candidates.py` | Use AdsorbDiff placement classes to generate candidate adsorbate-on-slab POSCARs and optional LMDB input. |
| Diffusion workflow | `scripts/adsorbdiff_workflow.py` | Build sampling and optional MLFF relaxation commands from a candidate LMDB. |

## POSCAR Tags

AdsorbDiff uses atom tags:

- `0`: subsurface or fixed slab atoms.
- `1`: surface slab atoms.
- `2`: adsorbate atoms.

POSCAR cannot preserve ASE tags directly, so the prep script writes:

- `adsorbdiff_slab/POSCAR`: normalized slab POSCAR with optional Selective
  Dynamics flags. Fixed atoms are `F F F`, surface atoms are `T T T`.
- `results/adsorbdiff_tags.txt`: one tag per atom.
- `results/adsorbdiff_poscar_metadata.json`: full cell, formula, tags, surface
  indices, and warnings.

## Controller Decisions

The controller must not ask the user for AdsorbDiff internals when a reasonable
agent decision can be made from the POSCAR, adsorbate, local runtime, and
available checkpoints.

Controller-owned decisions:

- Surface side: infer from top/bottom vacuum exposure. Use `top` only as the
  deterministic tie-breaker when both sides are similarly exposed.
- Surface thickness: infer from the nearest surface-layer spacing, constrained
  to a conservative `0.8-3.0 A` range. Fall back to `2.0 A` only when layers
  cannot be identified.
- Vacuum warning threshold: default to `8.0 A` unless the upstream task gives a
  stronger threshold.
- Selective Dynamics flags: write them by default so fixed/mobile atoms are
  explicit.
- Placement mode: `random_site_heuristic_placement` when the AdsorbDiff
  adsorbate DB provides binding indices; otherwise `random`.
- Candidate count: inferred automatically from the POSCAR surface atom count,
  in-plane surface area, adsorbate size, and binding atom count. Do not ask the
  user to choose an exploration level.
- Number of sites: infer from surface atom count and in-plane surface area.
- Augmentations per site: infer from adsorbate complexity. Single-atom
  adsorbates use one orientation per site; small molecules use two; larger
  molecules use three; multiple binding atoms add one orientation, capped at
  four.
- Optional hard overrides: `placement.target_candidates`,
  `placement.min_candidates`, `placement.max_candidates`,
  `placement.num_sites`, and `placement.num_augmentations_per_site`. Treat
  these as external budget constraints or deliberate scientific constraints,
  not routine user prompts.
- Interstitial gap: infer from adsorbate size and binding multiplicity.
- Diffusion checkpoint: prefer the PaiNN zero-shot checkpoint name for fast
  inference when no checkpoint is supplied.
- Diffusion config: infer from the checkpoint filename. Use
  `configs/denoising/painn_so3.yml` for `PT_zeroshot_painn.pt`.
- Seed: generate a deterministic seed from POSCAR path, adsorbate identity, and
  candidate count unless a reproducibility seed is explicitly supplied.
- Trajectory-to-LMDB conversion: enable by default using
  `scripts/adsorbdiff_traj_to_lmdb.py` so GemNet validation has a relaxation
  input.
- MLFF validation: enable pretrained GemNet-OC relaxation by default with
  `gemnet_oc_base_s2ef_2M.pt`.
- Runtime device: infer CPU/GPU from PyTorch CUDA availability and compiled GPU
  architecture support. Select CPU automatically when CUDA is unavailable or
  unsupported by the installed wheel.
- Handoff count: infer `top_k` from the square root of the generated candidate
  count, capped at eight, unless an upstream budget explicitly sets it.

Override controller-owned decisions only when the user or upstream task
provides a clear scientific, reproducibility, hardware, or budget reason.

The controller records surface, placement, sampling, runtime, GemNet
relaxation, and handoff decisions in `results/resolved_adsorbdiff_config.json`
so the agent head can audit why each formerly-human input was chosen.

## Commands

Controller dry-run:

```bash
python scripts/adsorbdiff_controller.py --input adsorbdiff_poscar.input.json
```

POSCAR prep only:

```bash
python scripts/poscar_to_adsorbdiff_input.py --input POSCAR --workdir runs/case
```

Adsorbate check only:

```bash
python scripts/adsorbate_checker.py --smiles "*CO"
```

Candidate placement after controller:

```bash
python scripts/adsorbdiff_place_candidates.py \
  --prepared-poscar runs/case/adsorbdiff_slab/POSCAR \
  --metadata runs/case/results/adsorbdiff_poscar_metadata.json \
  --adsorbate-id 12 \
  --lmdb-output runs/case/candidate_lmdb
```

The candidate placement script requires the full AdsorbDiff environment
because it imports ASE, Pymatgen, SciPy, Torch, LMDB, and AdsorbDiff modules.

## Failure Policy

- Fail if the POSCAR cannot be parsed or no adsorbate was specified.
- Fail if the adsorbate cannot be verified, unless the input explicitly sets
  `allow_unverified_adsorbate: true`.
- Warn, but do not fail, when the estimated vacuum is below the requested
  threshold; downstream relaxation may still decide whether to proceed.
- Do not silently choose a different adsorbate for id or SMILES queries.
- For formula queries, the controller may select deterministically only when
  `allow_agent_adsorbate_choice` is true; record the tie-breaker in messages.
