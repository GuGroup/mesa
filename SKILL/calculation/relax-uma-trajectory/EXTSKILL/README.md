---
name: uma-relax-traj-extskill
description: External fixed-execution layer for relax-uma-trajectory, containing the UMA relaxation trajectory runner and the qsub wrapper that executes controller-resolved settings without making scientific decisions.
---

# uma-relax-traj-extskill

`uma-relax-traj-extskill` contains the fixed execution components for
`relax-uma-trajectory`. These files do not decide UMA scientific settings.
They execute the settings already written by the controller in
`results/resolved_uma_config.json`.

## Files

| File | What it does |
| --- | --- |
| `uma_relax_traj_runner.md` | Protocol for the fixed UMA/ASE runner. |
| `uma_relax_traj_runner.py` | Reads the resolved config, runs relaxation, and writes artifacts. |
| `scripts/run_uma_relax_traj.qsub.sh` | Creates runtime directories and runs the fixed runner on the qsub server environment. |

## Runtime Contract

The external layer reads:

```text
results/resolved_uma_config.json
```

The external layer writes:

```text
relax.traj
relaxed/POSCAR
results/uma_relax_traj.json
logs/uma_relax_traj.log
```

## qsub Wrapper Rules

The qsub script must:

1. Create `relaxed/`, `results/`, and `logs/`.
2. Run `EXTSKILL/uma_relax_traj_runner.py`.
3. Save stdout and stderr to `logs/uma_relax_traj.log`.

The qsub script must not decide model, task name, device, relaxation type, force
threshold, step count, optimizer, or constraints.

## Dependency Notes

Real execution requires ASE and FAIRChem/UMA in the active Python environment.
The runner should return structured failure JSON when dependencies or runtime
execution fail.
