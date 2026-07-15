---
name: calculate-uma-vibrational-frequencies
description: Run a minimal MESA calculate-uma-vibrational-frequencies workflow for UMA-based finite-displacement vibrational frequencies from only a POSCAR path, with controller-owned UMA and vibration settings, qsub/local execution, vib.freq output, and structured vibration metadata.
---

For MESA end-to-end use, read `SKILL/calculation/workflow.md` before applying this skill.

# mesa-uma-vib-freq

## Runtime Environment

Run this skill in the configured UMA runtime:

```bash
mamba run -n fairchem
```

The existing machine-local `fairchem` mamba environment provides ASE and
FAIRChem/UMA. Its major package specification is recorded at
`ENVIRONMENT/fairchem/environment.yml`; do not assume a bootstrap-created
`mesa-uma` env exists.

`calculate-uma-vibrational-frequencies` is a minimal MESA skill for UMA-based
finite-displacement vibrational frequency calculation. The upstream task
provides only a POSCAR path, preferably a relaxed POSCAR. The controller decides
all UMA and vibration settings, writes the resolved configuration, and runs or
submits the fixed runner. The runner executes that configuration and produces
`vib.freq` plus structured metadata.

The user or upstream task must not provide `model`, `task_name`, `device`,
`indices`, `delta`, `nfree`, output paths, or vibration cache paths as required
input. Those values belong to `MYSKILL/uma_vib_freq_controller.py`.

## Files

| File | What it does |
| --- | --- |
| `MYSKILL/uma_vib_freq_controller.md` | Defines the POSCAR-only decision protocol, resolved settings, execution modes, artifact checks, and MESA output. |
| `MYSKILL/uma_vib_freq_controller.py` | Implements the controller. |
| `EXTSKILL/README.md` | Describes the fixed external execution layer. |
| `EXTSKILL/uma_vib_freq_runner.md` | Defines the runner protocol for reading `results/resolved_uma_vib_config.json` and executing UMA vibrations. |
| `EXTSKILL/uma_vib_freq_runner.py` | Implements the fixed UMA/ASE vibration runner. |
| `EXTSKILL/scripts/run_uma_vib_freq.qsub.sh` | Creates runtime folders and runs the fixed runner through the qsub server environment. |

## Input

The required input is only a POSCAR path:

```json
{
  "poscar_path": "relaxed/POSCAR"
}
```

The controller may accept execution context such as `workdir`, `execution_mode`,
or `dry_run`, but scientific UMA and vibration settings are controller-owned
decisions.

## Commands

| Command | What it does |
| --- | --- |
| `python MYSKILL/uma_vib_freq_controller.py --input input.json --output controller_output.json --workdir <run_dir> --dry-run` | Write `results/resolved_uma_vib_config.json` and the planned execution command without running UMA. |
| `python MYSKILL/uma_vib_freq_controller.py --input input.json --output controller_output.json --workdir <run_dir>` | Run the controller according to `execution_mode` in the input JSON. |
| `qsub EXTSKILL/scripts/run_uma_vib_freq.qsub.sh` | Run the fixed runner on the qsub server environment after the controller has written `results/resolved_uma_vib_config.json`. |

## Artifacts

| Artifact | Producer |
| --- | --- |
| `results/resolved_uma_vib_config.json` | Controller |
| `vib.freq` | Runner |
| `results/uma_vib_freq.json` | Runner |
| `vib_cache/` | Runner |
| `logs/uma_vib_freq.log` | qsub wrapper or local controller |
| `EXTSKILL/scripts/run_uma_vib_freq.qsub.sh` | Skill bundle |

## Workflow

1. Receive the POSCAR path from the upstream MESA task.
2. Check only that the POSCAR exists, is non-empty, and can be opened.
3. Inspect the POSCAR and runtime environment enough to decide UMA and vibration
   settings.
4. Write `results/resolved_uma_vib_config.json`.
5. Run locally or submit `EXTSKILL/scripts/run_uma_vib_freq.qsub.sh`.
6. The qsub script creates `results/`, `logs/`, and `vib_cache/`, then runs the
   fixed runner.
7. The runner reads the resolved config, attaches FAIRChem/UMA through ASE, runs
   finite-displacement vibrations, writes `vib.freq`, and writes
   `results/uma_vib_freq.json`.
8. The controller checks required outputs and returns the standard MESA skill
   output envelope.

## Output Envelope

Return the standard MESA skill output format with:

```json
{
  "status": "success",
  "task_id": "calculate-uma-vibrational-frequencies",
  "skill": "calculate-uma-vibrational-frequencies",
  "data": {
    "frequency_output": {
      "format": "ASE vibration summary",
      "path": "vib.freq"
    },
    "result_json": "results/uma_vib_freq.json",
    "resolved_config": "results/resolved_uma_vib_config.json",
    "vib_cache": "vib_cache/"
  },
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
    "reason": "vib.freq and results/uma_vib_freq.json are available."
  }
}
```

## Limits

- Do not ask the user for UMA or vibration settings.
- Do not expose UMA model, task name, device, indices, displacement size, finite
  difference mode, output paths, or cache paths as required user inputs.
- Do not run relaxation inside this task.
- Do not generate VASP inputs.
- Do not generate `INCAR`, `KPOINTS`, `POTCAR`, or VASP job folders.
- Do not create separate input-guard, result-checker, or qsub skills for this
  task.
- Do not create examples or tests for this minimal task.

## Common Errors

| Error | Fix |
| --- | --- |
| POSCAR path is missing | Provide only `poscar_path` in the controller input JSON. |
| POSCAR is empty or unreadable | Fix the upstream POSCAR artifact before running this task. |
| User-supplied UMA or vibration settings appear in the required input | Remove them from the required input; the controller must decide them. |
| `results/resolved_uma_vib_config.json` is missing | Run the controller before running the fixed runner or qsub wrapper. |
| Structure too large | Use a smaller relaxed structure or provide a POSCAR with Selective Dynamics flags that identify local movable atoms upstream. |
| `vib.freq` is missing after execution | Inspect `logs/uma_vib_freq.log` and `results/uma_vib_freq.json`. |
| `vib_cache/` is missing | Inspect the runner result JSON and qsub/local logs. |
| FAIRChem/UMA or ASE import fails | Run inside the configured UMA execution environment. |
