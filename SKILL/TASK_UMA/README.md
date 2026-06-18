# TASK_MLIP_DFT_HANDOFF

MLIP-to-DFT Structure Handoff Workflow for the MESA agent system.

This TASK receives a POSCAR path, validates the structure, prepares or submits a UMA single-point plus relaxation workflow, assesses MLIP reliability, and writes a downstream DFT handoff summary. It does not run VASP and does not generate `INCAR`, `KPOINTS`, `POTCAR`, or VASP job folders.

## Layout

```text
TASK_MLIP_DFT_HANDOFF/
  MYSKILL/
    mlip_workflow_controller.py
    mlip_workflow_controller.md
    mlip_structure_guard.md
    mlip_uncertainty_guard.md
    mlip_dft_handoff_builder.md
  EXTSKILL/
    uma_singlepoint_runner.py
    uma_singlepoint_runner.md
    uma_relaxation_runner.py
    uma_relaxation_runner.md
    scripts/run_mlip_dft_handoff.qsub.sh
  examples/
    input.example.json
    output.example.json
  tests/
    test_mlip_workflow_controller.py
```

## Main Entry Point

```bash
python SKILL/TASK_MLIP_DFT_HANDOFF/MYSKILL/mlip_workflow_controller.py \
  --input SKILL/TASK_MLIP_DFT_HANDOFF/examples/input.example.json \
  --output /tmp/mesa_mlip_output.json \
  --dry-run
```

Default behavior is dry-run. Explicit execution modes are `qsub`, `submit`, `local`, or `run`.

## Codex Agent POSCAR-Only Workflow

These Markdown files are instructions for Codex or another MESA agent. Python does not execute Markdown directly. When a user provides only a POSCAR path, Codex must read the protocol documents, decide the controller input values, write an input JSON file, and then run the Python entry point.

When only a POSCAR is provided, Codex must:

1. Create an isolated run directory outside this TASK folder.
2. Read `MYSKILL/mlip_workflow_controller.md`, `MYSKILL/mlip_structure_guard.md`, `MYSKILL/mlip_dft_handoff_builder.md`, and `MYSKILL/mlip_uncertainty_guard.md`.
3. Inspect the POSCAR and runtime environment.
4. Decide UMA and relaxation settings according to `MYSKILL/mlip_dft_handoff_builder.md`.
5. Write a controller input JSON using the canonical nested schema:

```json
{
  "poscar_path": "POSCAR",
  "execution_mode": "local",
  "mlip_settings": {
    "model": "uma-s-1p2",
    "task": "omat",
    "device": "cpu"
  },
  "relaxation_settings": {
    "relax_type": "geometry",
    "fmax": 0.05,
    "steps": 300
  }
}
```

6. Run `MYSKILL/mlip_workflow_controller.py` with `--input`, `--output`, and `--workdir`.
7. Inspect `controller_output.json`, `results/uma_singlepoint.json`, `results/uma_relaxation.json`, `results/mlip_uncertainty_report.json`, and `results/dft_handoff_summary.json`.
8. Return `optimized/POSCAR` only when the handoff summary is `ready`. Otherwise, return the failure or review reason from the JSON outputs.

## Standard Output

Every executable returns the standard MESA skill output envelope with:

- `status`
- `task_id`
- `skill`
- `data`
- `artifacts`
- `messages`
- `errors`
- `provenance`
- `next_action`

## Expected Artifacts

- `optimized/POSCAR`
- `results/uma_singlepoint.json`
- `results/uma_relaxation.json`
- `results/mlip_uncertainty_report.json`
- `results/dft_handoff_summary.json`
- `logs/*.log`
- `EXTSKILL/scripts/run_mlip_dft_handoff.qsub.sh`
