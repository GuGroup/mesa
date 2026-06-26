# mesa-adsorbdiff Runtime Contract

Use this runtime for `TASK_Absorbdiff`.

This runtime is intentionally manual because AdsorbDiff depends on a research ML
stack: PyTorch, PyG extensions, LMDB, checkpoint files, and CUDA wheel matching.

Baseline setup from the skill reference:

```bash
conda create -n adsorbdiff python=3.10
conda activate adsorbdiff
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
pip install pyg_lib torch_scatter torch_sparse torch_cluster torch_spline_conv -f https://data.pyg.org/whl/torch-2.2.0+cu118.html
```

Adjust CUDA and PyTorch versions to the target machine. Do not download large
datasets or checkpoints from bootstrap by default.

Required runtime capabilities:

- Python environment with `ase`, `numpy`, `pyyaml`, `lmdb`, and `torch`
- Vendored AdsorbDiff importability from `SKILL/TASK_Absorbdiff/assets/AdsorbDiff`
- Local checkpoint paths for diffusion and optional GemNet/OCP relaxation

Common checkpoint names expected by the controller:

- `PT_zeroshot_painn.pt`
- `PT_fewshot_eqv2_cond.pt`
- `gemnet_oc_base_s2ef_2M.pt`

Optional environment variables:

- `CUDA_VISIBLE_DEVICES`: selects visible GPU devices for CUDA execution

Smoke test:

```bash
python -c "import ase, lmdb, torch, yaml; print('mesa-adsorbdiff ok')"
```

Do not install this runtime automatically from a generic bootstrap step unless
the target machine, CUDA version, and checkpoint policy are known.
