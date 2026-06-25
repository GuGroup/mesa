# AdsorbDiff Workflow Reference

## Upstream Repository

- Source: `https://github.com/AdeeshKolluru/AdsorbDiff`
- Vendored path: `assets/AdsorbDiff`
- Vendored commit: `8a905c7158e4973da76826e2b91bfd892ebbdcb1`
- Paper: AdsorbDiff: Adsorbate Placement via Conditional Denoising Diffusion,
  ICML 2024.

The upstream `README.md` gives the canonical install commands:

```bash
conda create -n adsorbdiff python=3.10
conda activate adsorbdiff
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
pip install pyg_lib torch_scatter torch_sparse torch_cluster torch_spline_conv -f https://data.pyg.org/whl/torch-2.2.0+cu118.html
pip install -r requirements.txt
pip install -e .
```

Use those commands as the baseline, but update CUDA/PyTorch wheels only after
checking the target machine.

## Important Paths

| Path | Purpose |
| --- | --- |
| `main.py` | AdsorbDiff entrypoint for train, predict, run-relaxations, and validate modes. |
| `run.py` | Upstream example command generator. Do not run unchanged because it contains author-local paths. |
| `configs/denoising/painn_so3.yml` | PaiNN SO3 diffusion config used with `PT_zeroshot_painn.pt`. |
| `configs/denoising/painn_conditional.yml` | Conditional PaiNN diffusion config for matching conditional checkpoints. |
| `configs/denoising/eqv2_conditional.yml` | Conditional EquiformerV2 diffusion config. |
| `configs/relaxation/gemnet_oc/gemnet_relax.yml` | GemNet-OC MLFF relaxation config. |
| `scripts/adsorbdiff_traj_to_lmdb.py` | Skill converter for sampled `.traj` files into a GemNet relaxation LMDB. |
| `scripts/create_lmdbs/pred_traj_to_lmdb.py` | Upstream converter; avoid as the default because it contains author-local assumptions. |

## Required External Inputs

Sampling requires:

- An AdsorbDiff-compatible LMDB dataset for `--task.relax_dataset.src`.
- A diffusion checkpoint passed with `--checkpoint`.
- A writable trajectory directory passed with `--task.relax_opt.traj_dir`.
- A localized runtime YAML config. `scripts/adsorbdiff_workflow.py` writes this
  automatically by default, removing upstream author-local train/val dataset
  paths before inference.

Optional MLFF relaxation requires:

- An LMDB produced from predicted trajectories or another compatible LMDB.
- A relaxation checkpoint such as an OCP/GemNet-OC checkpoint.
- A writable relaxation trajectory directory.

When starting from a POSCAR, do not invent the LMDB by hand. Run
`scripts/adsorbdiff_controller.py` first, then run the generated candidate
placement command with `--lmdb-output`. The resulting `candidate_lmdb` can be
used as `sampling.dataset_src`.

The upstream README lists checkpoint sources:

- PaiNN diffusion checkpoint: `PT_zeroshot_painn.pt`
- EquiformerV2 diffusion checkpoint: `PT_fewshot_eqv2_cond.pt`
- MLFF optimization checkpoints from FAIR-Chem/OCP pretrained models.

## Command Shape

Sampling:

```bash
python -u main.py \
  --mode run-relaxations \
  --config-yml configs/denoising/painn_so3.yml \
  --task.relax_dataset.src=/path/to/sampling_lmdb \
  --task.relax_opt.traj_dir=/path/to/samples \
  --checkpoint /path/to/PT_zeroshot_painn.pt \
  --model.sampling=True \
  --seed 0 \
  --debug
```

LMDB conversion:

```bash
python /path/to/adsorbdiff-placement/scripts/adsorbdiff_traj_to_lmdb.py \
  --input-dir /path/to/samples \
  --output-lmdb /path/to/samples/final_struct_lmdb \
  --repo /path/to/AdsorbDiff \
  --num-workers 4
```

MLFF relaxation:

```bash
python -u main.py \
  --mode run-relaxations \
  --config-yml configs/relaxation/gemnet_oc/gemnet_relax.yml \
  --checkpoint /path/to/gemnet_oc_base_s2ef_2M.pt \
  --task.relax_dataset.src=/path/to/samples/final_struct_lmdb \
  --task.relax_opt.traj_dir=/path/to/samples/relaxations \
  --debug
```

Add distributed launch only when the target runtime has multiple GPUs and the
environment is configured for PyTorch distributed execution.

## MESA Integration Notes

- Treat AdsorbDiff as candidate placement generation, not final validation.
- For POSCAR-first workflows, the controller owns surface tagging, adsorbate DB
  checking, placement mode, site count, augmentation count, and interstitial
  gap decisions, plus seed/config/checkpoint resolution, GemNet validation
  policy, runtime CPU/GPU selection, and downstream handoff count.
- Keep raw sampled trajectories and converted LMDBs under the task workdir.
- Pass selected final structures to UMA relaxation or DFT handoff after checking
  atom counts, adsorbate identity, periodic cell, and obvious overlap/anomaly
  flags.
- Preserve exact dataset/checkpoint/config paths in the MESA output envelope so
  downstream decisions can be audited.
