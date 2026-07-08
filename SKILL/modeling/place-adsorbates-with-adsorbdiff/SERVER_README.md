# AdsorbDiff Agent Skill Server Bundle

This is the clean server-ready AdsorbDiff agent skill. It excludes local test
runs, virtual environments, LMDB outputs, trajectories, and caches.

## Layout

```text
adsorbdiff-placement-agent-skill/
  SKILL.md
  bin/
    run_full_workflow.py
    patch_e3nn_torch_load.py
  scripts/
  references/
  agents/
  assets/
    AdsorbDiff/
    checkpoints/
      PT_zeroshot_painn.pt
      gemnet_oc_base_s2ef_2M.pt
  templates/
    controller.input.template.json
```

## Install On Server

```bash
cd /path/to/adsorbdiff-placement-agent-skill/assets/AdsorbDiff
python -m venv ../../.venv
source ../../.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
python -m pip install pyg_lib torch_scatter torch_sparse torch_cluster torch_spline_conv -f https://data.pyg.org/whl/torch-2.7.0+cu128.html
python -m pip install -r requirements.txt
python -m pip install -e .
python ../../bin/patch_e3nn_torch_load.py
```

Adjust the CUDA wheel URLs to match the server driver/runtime if needed.

## Run A POSCAR Case

Create a case directory with a POSCAR and input JSON:

```bash
mkdir -p /path/to/case
cp /path/to/POSCAR /path/to/case/POSCAR
cp /path/to/adsorbdiff-placement-agent-skill/templates/controller.input.template.json /path/to/case/controller.input.json
```

Edit `controller.input.json` only for the POSCAR filename, workdir, and
adsorbate identity. The controller decides surface tagging, candidate count,
placement settings, seed, checkpoint/config choice, GemNet validation, and
handoff policy.

Then run:

```bash
cd /path/to/adsorbdiff-placement-agent-skill
source .venv/bin/activate
python bin/run_full_workflow.py --input /path/to/case/controller.input.json
```

Use `--plan-only` to generate controller and workflow plans without running
AdsorbDiff/GemNet.

## Main Outputs

For `workdir = runs/adsorbdiff_case`, inspect:

```text
runs/adsorbdiff_case/results/resolved_adsorbdiff_config.json
runs/adsorbdiff_case/results/adsorbdiff_candidates.json
runs/adsorbdiff_case/results/best_relaxed_summary.json
runs/adsorbdiff_case/best_relaxed_POSCAR.vasp
runs/adsorbdiff_case/final_poscars/
runs/adsorbdiff_case/adsorbdiff_candidates/
runs/adsorbdiff_case/adsorbdiff_sampling/results/adsorbdiff_plan.json
runs/adsorbdiff_case/adsorbdiff_sampling/samples/site0/
```

After a full run, `bin/run_full_workflow.py` prints `BEST_RELAXED_POSCAR`,
`BEST_ENERGY_EV`, and `BEST_FMAX_EV_PER_A`. The selected structure is the
lowest final GemNet-relaxed energy among the relaxed trajectories, with fmax
used as a tie-breaker/reporting quality check.

Do not commit generated `runs/`, LMDBs, trajectories, SO3 caches, or checkpoint
files to normal Git. Use Git LFS or release assets for checkpoints.
