---
name: mesa-uma-traj
description: Generate a UMA relaxation trajectory for the MESA TASK_UMA_RELAX_TRAJECTORY workflow. Use when the upstream MESA task provides only a POSCAR path and the controller must decide UMA execution settings, run or submit UMA relaxation, and return relax.traj plus relaxed/POSCAR with structured result metadata.
---

# mesa-uma-traj

`mesa-uma-traj` is a minimal MESA TASK-level skill for generating a UMA/ASE
relaxation trajectory from one POSCAR file. The upstream task provides only the
POSCAR path. The controller decides all UMA execution settings, writes the
resolved configuration, and runs or submits the fixed runner. The runner executes
that configuration and produces `relax.traj` plus `relaxed/POSCAR`.

The user or upstream task must not provide `model`, `task_name`, `device`,
`relax_type`, `fmax`, `steps`, `optimizer`, or `constraints` as required input.
Those values belong to `MYSKILL/uma_relax_traj_controller.py`.

## Files

| File | What it does |
| --- | --- |
| `MYSKILL/uma_relax_traj_controller.md` | Defines the decision-layer protocol for POSCAR-only input, resolved settings, execution mode, artifact checks, and MESA output. |
| `MYSKILL/uma_relax_traj_controller.py` | Implements the controller. |
| `EXTSKILL/README.md` | Describes the external fixed-execution layer. |
| `EXTSKILL/uma_relax_traj_runner.md` | Defines the runner protocol for reading `results/resolved_uma_config.json` and executing UMA relaxation. |
| `EXTSKILL/uma_relax_traj_runner.py` | Implements the fixed UMA/ASE runner. |
| `EXTSKILL/scripts/run_uma_relax_traj.qsub.sh` | Creates runtime folders and runs the fixed runner through the qsub server environment. |

## Input

The required input is only a POSCAR path:

```json
{
  "poscar_path": "POSCAR"
}
```

The controller may accept execution context such as `workdir`, `execution_mode`,
or `dry_run`, but scientific UMA settings are controller-owned decisions.

## Commands

| Command | What it does |
| --- | --- |
| `python MYSKILL/uma_relax_traj_controller.py --input input.json --output controller_output.json --workdir <run_dir> --dry-run` | Write `results/resolved_uma_config.json` and the planned execution command without running UMA. |
| `python MYSKILL/uma_relax_traj_controller.py --input input.json --output controller_output.json --workdir <run_dir>` | Run the controller according to `execution_mode` in the input JSON. |
| `qsub EXTSKILL/scripts/run_uma_relax_traj.qsub.sh` | Run the fixed runner on the qsub server environment after the controller has written `results/resolved_uma_config.json`. |

## Artifacts

| Artifact | Producer |
| --- | --- |
| `results/resolved_uma_config.json` | Controller |
| `relax.traj` | Runner |
| `relaxed/POSCAR` | Runner |
| `results/uma_relax_traj.json` | Runner |
| `logs/uma_relax_traj.log` | qsub wrapper / ASE optimizer |
| `EXTSKILL/scripts/run_uma_relax_traj.qsub.sh` | Skill bundle |

## Workflow

1. Receive the POSCAR path from the upstream MESA task.
2. Check only that the POSCAR exists, is non-empty, and can be opened.
3. Inspect the POSCAR and runtime environment enough to decide UMA settings.
4. Write `results/resolved_uma_config.json`.
5. Run locally or submit `EXTSKILL/scripts/run_uma_relax_traj.qsub.sh`.
6. The qsub script creates `relaxed/`, `results/`, and `logs/`, then runs the
   fixed runner.
7. The runner reads the resolved config, attaches FAIRChem/UMA through ASE, runs
   relaxation, writes `relax.traj`, writes `relaxed/POSCAR`, and writes
   `results/uma_relax_traj.json`.
8. The controller checks required outputs and returns the standard MESA skill
   output envelope.

## Output Envelope

Return the standard MESA skill output format with:

```json
{
  "status": "success",
  "task_id": "TASK_UMA_RELAX_TRAJECTORY",
  "skill": "uma_relax_traj_controller",
  "data": {},
  "artifacts": [],
  "messages": [],
  "errors": [],
  "provenance": {
    "inputs": [],
    "external_calls": [],
    "generated_files": []
  },
  "next_action": {
    "recommendation": "continue",
    "reason": "relax.traj and relaxed/POSCAR are available."
  }
}
```

## Limits

- Do not ask the user for UMA settings.
- Do not expose UMA model, task, device, force threshold, step count, optimizer,
  constraints, or relaxation type as required user inputs.
- Do not generate VASP inputs.
- Do not generate `INCAR`, `KPOINTS`, `POTCAR`, or VASP job folders.
- Do not generate or store POTCAR contents.
- Do not compute vibrational frequencies.
- Do not create examples or tests for this minimal task.

## Common Errors

| Error | Fix |
| --- | --- |
| POSCAR path is missing | Provide only `poscar_path` in the controller input JSON. |
| POSCAR is empty or unreadable | Fix the upstream POSCAR artifact before running this task. |
| User-supplied UMA settings appear in the required input | Remove them from the required input; the controller must decide them. |
| `results/resolved_uma_config.json` is missing | Run the controller before running the fixed runner or qsub wrapper. |
| `relax.traj` is missing after execution | Inspect `logs/uma_relax_traj.log` and `results/uma_relax_traj.json`. |
| `relaxed/POSCAR` is missing after execution | Treat the task as failed and surface the runner error JSON. |
| FAIRChem/UMA or ASE import fails | Run inside the configured UMA execution environment. |
