# EXTSKILL

## Purpose

Provide fixed wrappers around external UMA execution and qsub submission for `TASK_MLIP_DFT_HANDOFF`.

## Position in MESA Pipeline

These external skills are called by `MYSKILL/mlip_workflow_controller.py` after structure validation and before MLIP reliability assessment.

## Inputs

The runners accept JSON input files containing a POSCAR path, `mlip_settings`, output directories, and `relaxation_settings` where relevant. The qsub script accepts positional arguments for input POSCAR, output POSCAR, model, task, device, relax type, fmax, and steps, then writes canonical nested runner input JSON.

## Outputs

The single-point runner writes `results/uma_singlepoint.json`. The relaxation runner writes `optimized/POSCAR` and `results/uma_relaxation.json`. The qsub script also writes `logs/*.log`.

## Algorithm

1. Codex or the controller provides resolved settings using `mlip_settings` and `relaxation_settings`.
2. The qsub script creates runner input JSON files.
3. `uma_singlepoint_runner.py` runs UMA energy and force evaluation through ASE.
4. `uma_relaxation_runner.py` runs UMA relaxation through ASE and writes `optimized/POSCAR`.
5. The controller consumes the runner outputs for reliability and handoff summaries.

## Dependencies

Python, ASE, FAIRChem/UMA, and a qsub-compatible server environment are required for real execution. Dry-run and tests do not require ASE, CUDA, qsub, or UMA.

## Failure Modes

Runners return structured failures if dependencies are missing, the POSCAR cannot be read, UMA calculator creation fails, calculation fails, or output files cannot be written.

## Example

```bash
qsub EXTSKILL/scripts/run_mlip_dft_handoff.qsub.sh \
  POSCAR optimized/POSCAR uma-s-1p2 omat cuda geometry 0.05 300
```

## Validation

Run unit tests for controller command construction. In a configured UMA environment, run the qsub script or local mode on a small POSCAR and inspect `results/` plus `optimized/POSCAR`.

## Limitations

These wrappers do not infer scientific intent, choose UMA task, choose runtime device, manage cluster account names, queues, conda activation, private paths, or VASP execution.
