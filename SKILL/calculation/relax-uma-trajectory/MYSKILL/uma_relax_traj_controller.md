---
name: uma-relax-traj-controller
description: Decide UMA relaxation trajectory settings for TASK_UMA_RELAX_TRAJECTORY from only a POSCAR path, write results/resolved_uma_config.json, run or submit the fixed runner, verify relax.traj and relaxed/POSCAR, and return the standard MESA skill output envelope.
---

# uma-relax-traj-controller

`uma-relax-traj-controller` is the MESA decision layer for
`TASK_UMA_RELAX_TRAJECTORY`. It receives only a POSCAR path as required input,
decides all UMA execution settings, writes the resolved settings, invokes the
fixed runner, and checks whether the trajectory and final relaxed POSCAR were
created.

The controller owns scientific and runtime decisions. The runner only executes
the resolved config.

## Required Input

The only required user or upstream-task input is:

```json
{
  "poscar_path": "POSCAR"
}
```

The controller may also receive runtime context such as `workdir`,
`execution_mode`, or `dry_run`. These are execution controls, not UMA scientific
settings.

## Controller-Owned Settings

The controller must decide and write these fields to
`results/resolved_uma_config.json`:

| Field | Decision owner |
| --- | --- |
| `model` | Controller |
| `task_name` | Controller |
| `device` | Controller |
| `relax_type` | Controller |
| `fmax` | Controller |
| `steps` | Controller |
| `optimizer` | Controller |
| `constraints` | Controller, only when needed |

Do not require the user or upstream task to provide these fields.

## Minimal POSCAR Checks

Perform only minimal file checks:

1. Confirm the POSCAR path exists.
2. Confirm it is non-empty.
3. Confirm it can be opened.

Do not repeat full structural validation if an earlier UMA/MESA task already
validated the structure.

## Resolved Config

Write `results/resolved_uma_config.json` before execution. Include paths,
settings, decision reasons, and controller metadata.

```json
{
  "task_id": "TASK_UMA_RELAX_TRAJECTORY",
  "input_poscar": "POSCAR",
  "outputs": {
    "trajectory": "relax.traj",
    "relaxed_poscar": "relaxed/POSCAR",
    "result_json": "results/uma_relax_traj.json",
    "log": "logs/uma_relax_traj.log"
  },
  "uma": {
    "model": "uma-s-1p2",
    "task_name": "omat",
    "device": "cuda"
  },
  "relaxation": {
    "relax_type": "geometry",
    "fmax": 0.05,
    "steps": 300,
    "optimizer": "FIRE",
    "constraints": []
  },
  "decision_reasons": []
}
```

Use executable fallback settings when no stronger POSCAR or runtime reason is
available: `model=uma-s-1p2`, `task_name=omat`, `device=cuda` when available
otherwise `cpu`, `relax_type=geometry`, `fmax=0.05`, `steps=300`, and
`optimizer=FIRE`.

## Execution

| Mode | What it does |
| --- | --- |
| `dry-run` | Write resolved config and planned command, then stop before UMA execution. |
| `local` / `run` | Run `EXTSKILL/uma_relax_traj_runner.py` directly in the workdir. |
| `qsub` / `submit` | Submit `EXTSKILL/scripts/run_uma_relax_traj.qsub.sh` in the qsub environment. |

For qsub execution, use only the qsub wrapper script. The qsub script must not
decide model, task, device, force threshold, step count, optimizer, constraints,
or relaxation type.

## Required Output Checks

After execution, check for:

| Artifact | Required |
| --- | --- |
| `relax.traj` | Yes |
| `relaxed/POSCAR` | Yes |
| `results/resolved_uma_config.json` | Yes |
| `results/uma_relax_traj.json` | Yes |
| `logs/uma_relax_traj.log` | Yes |

Return success only when the required runner outputs exist and
`results/uma_relax_traj.json` reports success.

## Failure Handling

Return a structured MESA failure when:

- POSCAR is missing, empty, or unreadable.
- Resolved config cannot be written.
- qsub submission fails.
- The fixed runner returns a non-zero exit code.
- Required outputs are missing after execution.
- `results/uma_relax_traj.json` reports failure.

Preserve the runner error payload under the controller output `errors` list when
available.

## Limits

- Do not ask the user for UMA settings.
- Do not generate VASP inputs.
- Do not create `INCAR`, `KPOINTS`, `POTCAR`, or VASP job folders.
- Do not compute vibrational frequencies.
- Do not create separate input-guard or qsub skills for this task.
