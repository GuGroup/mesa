---
name: uma-vib-freq-extskill
description: External fixed-execution layer for TASK_UMA_VIB_FREQ, containing the UMA finite-displacement vibration runner and the qsub wrapper that executes controller-resolved settings without making scientific decisions.
---

# uma-vib-freq-extskill

`uma-vib-freq-extskill` contains the fixed execution components for
`TASK_UMA_VIB_FREQ`. These files do not decide UMA or vibration settings. They
execute the settings already written by the controller in
`results/resolved_uma_vib_config.json`.

## Files

| File | What it does |
| --- | --- |
| `uma_vib_freq_runner.md` | Protocol for the fixed UMA/ASE vibration runner. |
| `uma_vib_freq_runner.py` | Reads the resolved config, runs finite-displacement vibrations, and writes artifacts. |
| `scripts/run_uma_vib_freq.qsub.sh` | Creates runtime directories and runs the fixed runner on the qsub server environment. |

## Runtime Contract

The external layer reads:

```text
results/resolved_uma_vib_config.json
```

The external layer writes:

```text
vib.freq
results/uma_vib_freq.json
vib_cache/
logs/uma_vib_freq.log
```

## qsub Wrapper Rules

The qsub script must:

1. Create `results/`, `logs/`, and `vib_cache/`.
2. Run `EXTSKILL/uma_vib_freq_runner.py`.
3. Save stdout and stderr to `logs/uma_vib_freq.log`.

The qsub script must not decide model, task name, device, indices, delta, nfree,
output paths, or cache paths.

## Dependency Notes

Real execution requires ASE and FAIRChem/UMA in the active Python environment.
The runner should return structured failure JSON when dependencies or runtime
execution fail.
