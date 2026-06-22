---
name: uma-relax-traj-runner
description: Fixed UMA/ASE relaxation trajectory runner for TASK_UMA_RELAX_TRAJECTORY. Use to read results/resolved_uma_config.json, attach FAIRChem/UMA through ASE, run relaxation, write relax.traj and relaxed/POSCAR, and save results/uma_relax_traj.json without deciding scientific settings.
---

# uma-relax-traj-runner

`uma-relax-traj-runner` is the fixed execution runner for
`TASK_UMA_RELAX_TRAJECTORY`. It reads `results/resolved_uma_config.json`, reads
the input POSCAR, attaches the FAIRChem/UMA calculator through ASE, runs
relaxation, and writes the trajectory plus final relaxed POSCAR.

The runner must not decide UMA scientific settings. It only executes the
controller-resolved configuration.

## Inputs

Read all required execution settings from:

```text
results/resolved_uma_config.json
```

Required config contents:

| Field | Meaning |
| --- | --- |
| `input_poscar` | POSCAR path to read. |
| `outputs.trajectory` | Usually `relax.traj`. |
| `outputs.relaxed_poscar` | Usually `relaxed/POSCAR`. |
| `outputs.result_json` | Usually `results/uma_relax_traj.json`. |
| `outputs.log` | Usually `logs/uma_relax_traj.log`. |
| `uma.model` | Controller-selected UMA model. |
| `uma.task_name` | Controller-selected UMA task name. |
| `uma.device` | Controller-selected runtime device. |
| `relaxation.relax_type` | Controller-selected relaxation type. |
| `relaxation.fmax` | Controller-selected force threshold. |
| `relaxation.steps` | Controller-selected max optimizer steps. |
| `relaxation.optimizer` | Controller-selected ASE optimizer, default `FIRE`. |
| `relaxation.constraints` | Controller-selected constraints, if any. |

## Outputs

| Artifact | Contents |
| --- | --- |
| `relax.traj` | Full ASE relaxation trajectory. |
| `relaxed/POSCAR` | Final relaxed POSCAR. |
| `results/uma_relax_traj.json` | Structured runner status and metrics. |
| `logs/uma_relax_traj.log` | ASE optimizer and wrapper log output. |

## Execution Pattern

Use the official FAIRChem/UMA plus ASE workflow:

```python
from ase.io import read, write
from ase.optimize import FIRE
from fairchem.core import FAIRChemCalculator, pretrained_mlip

atoms = read("POSCAR", format="vasp")

predictor = pretrained_mlip.get_predict_unit(model, device=device)
atoms.calc = FAIRChemCalculator(predictor, task_name=task_name)

opt = FIRE(
    atoms,
    trajectory="relax.traj",
    logfile="logs/uma_relax_traj.log",
)

converged = opt.run(fmax=fmax, steps=steps)

write("relaxed/POSCAR", atoms, format="vasp", direct=True, sort=False, vasp5=True)
```

If the resolved config requests cell relaxation, use an ASE cell filter such as
`FrechetCellFilter` when available.

## Result JSON

On success, write at least:

```json
{
  "status": "success",
  "runner": "uma_relax_traj_runner",
  "input": "POSCAR",
  "output": "relaxed/POSCAR",
  "trajectory": "relax.traj",
  "config": "results/resolved_uma_config.json",
  "results": {
    "converged": null,
    "n_steps": null,
    "initial_energy_ev": null,
    "final_energy_ev": null,
    "initial_max_force_ev_per_a": null,
    "final_max_force_ev_per_a": null,
    "n_atoms_initial": null,
    "n_atoms_final": null
  },
  "errors": []
}
```

On failure, still write structured JSON:

```json
{
  "status": "failure",
  "runner": "uma_relax_traj_runner",
  "errors": [
    {
      "type": "RuntimeError",
      "message": "explain the failure"
    }
  ]
}
```

## Failure Handling

Write failure JSON when:

- `results/resolved_uma_config.json` is missing or invalid.
- The input POSCAR cannot be read.
- ASE is unavailable.
- FAIRChem/UMA is unavailable.
- Calculator creation fails.
- Relaxation fails.
- Output writing fails.

## Limits

- Do not decide model, task name, device, relaxation type, force threshold, step
  count, optimizer, or constraints.
- Do not generate VASP inputs.
- Do not generate or store POTCAR contents.
- Do not compute vibrational frequencies.
