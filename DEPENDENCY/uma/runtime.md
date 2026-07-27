# mesa-uma Runtime Contract

Use this runtime for:

- `relax-uma-trajectory`
- `calculate-uma-vibrational-frequencies`

This runtime is intentionally manual because FAIRChem/UMA, PyTorch, CUDA, GPU
driver compatibility, and cluster queues are machine-specific.

Required runtime capabilities:

- Mamba environment `fairchem` on this machine.
- Python environment with `ase`.
- FAIRChem/UMA import path providing:
  `from fairchem.core import FAIRChemCalculator, pretrained_mlip`
- Local or cluster execution with `qsub` when using submit mode
- GPU-capable PyTorch when running on CUDA, or CPU support for small/debug runs

Configured local command prefix:

```bash
mamba run -n fairchem
```

Environment specification:

```text
ENVIRONMENT/fairchem/environment.yml
```

The YAML records the major packages observed in the existing machine-local
`fairchem` runtime. Treat this environment as external/manual unless the user
explicitly asks to recreate or update it.

Optional environment variables:

- `MESA_UMA_DEVICE`: force `cpu` or `cuda`
- `CUDA_VISIBLE_DEVICES`: selects visible GPU devices for CUDA execution
- `PYTHON_BIN`: qsub wrappers use this when set; otherwise they call `python`

Smoke test:

```bash
mamba run -n fairchem python -c "import ase; from fairchem.core import FAIRChemCalculator, pretrained_mlip; print('mesa-uma ok')"
```

Do not install this runtime automatically from a generic bootstrap step unless
the target machine, CUDA version, and cluster policy are known.
