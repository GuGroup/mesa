---
name: uma-vib-freq-controller
description: Decide UMA vibrational frequency settings for calculate-uma-vibrational-frequencies from only a POSCAR path, write results/resolved_uma_vib_config.json, run or submit the fixed UMA vibration runner, verify vib.freq and results/uma_vib_freq.json, and return the standard MESA skill output envelope.
---

# uma-vib-freq-controller

`uma-vib-freq-controller` is the MESA decision layer for
`calculate-uma-vibrational-frequencies`. It receives only a POSCAR path as required input, decides
all UMA and finite-displacement vibration settings, writes the resolved
settings, invokes the fixed runner, and checks whether frequency artifacts were
created.

The controller owns scientific and runtime decisions. The runner only executes
the resolved config.

## Required Input

The only required user or upstream-task input is:

```json
{
  "poscar_path": "relaxed/POSCAR"
}
```

The controller may also receive runtime context such as `workdir`,
`execution_mode`, or `dry_run`. These are execution controls, not UMA or
vibration settings.

## Controller-Owned Settings

The controller must decide and write these fields to
`results/resolved_uma_vib_config.json`:

| Field | Decision owner |
| --- | --- |
| `uma.model` | Controller |
| `uma.task_name` | Controller |
| `uma.device` | Controller |
| `vibration.indices` | Controller |
| `vibration.delta` | Controller |
| `vibration.nfree` | Controller |
| `vib_cache` | Controller |
| `output_freq` | Controller |
| `result_json` | Controller |
| `log_file` | Controller |

Do not require the user or upstream task to provide these fields.

## Minimal POSCAR Checks

Perform only minimal file checks:

1. Confirm the POSCAR path exists.
2. Confirm it is non-empty.
3. Confirm it can be opened.

Do not repeat full structural validation if an earlier UMA/MESA task already
validated or relaxed the structure.

## Resolved Config

Write `results/resolved_uma_vib_config.json` before execution. Include real
controller-selected values, not placeholders.

```json
{
  "task_id": "calculate-uma-vibrational-frequencies",
  "input_poscar": "relaxed/POSCAR",
  "output_freq": "vib.freq",
  "result_json": "results/uma_vib_freq.json",
  "log_file": "logs/uma_vib_freq.log",
  "vib_cache": "vib_cache/vib",
  "uma": {
    "model": "uma-s-1p2",
    "task_name": "omat",
    "device": "cuda"
  },
  "vibration": {
    "indices": null,
    "delta": 0.01,
    "nfree": 2
  },
  "decision_basis": {
    "n_atoms": null,
    "elements": [],
    "structure_type": "unknown",
    "reason": "Controller decided settings from POSCAR and runtime environment."
  }
}
```

Use executable fallback settings when no stronger POSCAR or runtime reason is
available: `model=uma-s-1p2`, `task_name=omat`, `device=cuda` when available
otherwise `cpu`, `delta=0.01`, and `nfree=2`.

## Structure-Size Logic

Finite-displacement vibration scales with the number of displaced atoms. The
controller must avoid launching impractical full-frequency calculations.

Use this minimal policy:

| Structure hint | Decision |
| --- | --- |
| Small structure | Displace all atoms with `indices: null`. |
| POSCAR has Selective Dynamics and a manageable movable subset | Displace only movable atom indices. |
| Large structure without identifiable local atoms | Write the resolved config but stop before launch with `needs_human_review`. |

Do not run relaxation in this task. If relaxation provenance is not obvious from
the POSCAR path, record a warning but continue when the structure is small enough
or has a manageable selected subset.

## Execution

| Mode | What it does |
| --- | --- |
| `dry-run` | Write resolved config and planned command, then stop before UMA execution. |
| `local` / `run` | Run `EXTSKILL/uma_vib_freq_runner.py` directly in the workdir. |
| `qsub` / `submit` | Submit `EXTSKILL/scripts/run_uma_vib_freq.qsub.sh` in the qsub environment. |

For qsub execution, use only the qsub wrapper script. The qsub script must not
decide model, task name, device, indices, delta, nfree, output paths, or cache
paths.

## Required Output Checks

After execution, check for:

| Artifact | Required |
| --- | --- |
| `vib.freq` | Yes |
| `results/resolved_uma_vib_config.json` | Yes |
| `results/uma_vib_freq.json` | Yes |
| `vib_cache/` | Yes |
| `logs/uma_vib_freq.log` | Expected |

Return success only when `vib.freq` exists and `results/uma_vib_freq.json`
reports success. Set `next_action.recommendation` to `continue` only after those
outputs are available.

## Failure Handling

Return a structured MESA failure when:

- POSCAR is missing, empty, or unreadable.
- Controller-owned settings are provided by the user or upstream task.
- The structure is too large and no local indices can be identified.
- Resolved config cannot be written.
- qsub submission fails.
- The fixed runner returns a non-zero exit code.
- Required outputs are missing after execution.
- `results/uma_vib_freq.json` reports failure.

Preserve the runner error payload under the controller output `errors` list when
available.

## Limits

- Do not ask the user for UMA or vibration settings.
- Do not generate VASP inputs.
- Do not run relaxation.
- Do not create separate input-guard, result-checker, or qsub skills for this
  task.
