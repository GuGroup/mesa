---
name: uma-vib-freq-runner
description: Fixed UMA/ASE finite-displacement vibrational frequency runner for TASK_UMA_VIB_FREQ. Use to read results/resolved_uma_vib_config.json, attach FAIRChem/UMA through ASE, run ASE Vibrations, write vib.freq, populate vib_cache, and save results/uma_vib_freq.json without deciding scientific settings.
---

# uma-vib-freq-runner

`uma-vib-freq-runner` is the fixed execution runner for
`TASK_UMA_VIB_FREQ`. It reads `results/resolved_uma_vib_config.json`, reads the
input POSCAR, attaches the FAIRChem/UMA calculator through ASE, runs ASE
finite-displacement vibrations, and writes frequency artifacts.

The runner must not decide UMA or vibration settings. It only executes the
controller-resolved configuration.

## Inputs

Read all required execution settings from:

```text
results/resolved_uma_vib_config.json
```

Required config contents:

| Field | Meaning |
| --- | --- |
| `input_poscar` | POSCAR path to read. |
| `output_freq` | Usually `vib.freq`. |
| `result_json` | Usually `results/uma_vib_freq.json`. |
| `log_file` | Usually `logs/uma_vib_freq.log`. |
| `vib_cache` | ASE Vibrations cache prefix, usually `vib_cache/vib`. |
| `uma.model` | Controller-selected UMA model. |
| `uma.task_name` | Controller-selected UMA task name. |
| `uma.device` | Controller-selected runtime device. |
| `vibration.indices` | Controller-selected atom indices or `null` for all atoms. |
| `vibration.delta` | Controller-selected displacement size. |
| `vibration.nfree` | Controller-selected finite-difference mode. |

## Outputs

| Artifact | Contents |
| --- | --- |
| `vib.freq` | Human-readable ASE vibration summary. |
| `results/uma_vib_freq.json` | Structured runner status and frequency metadata. |
| `vib_cache/` | ASE finite-displacement vibration cache files. |
| `logs/uma_vib_freq.log` | Wrapper or local execution log output. |

## Execution Pattern

Use the official FAIRChem/UMA plus ASE workflow:

```python
from ase.io import read
from ase.vibrations import Vibrations
from fairchem.core import FAIRChemCalculator, pretrained_mlip

atoms = read(input_poscar, format="vasp")
if task_name == "omol":
    atoms.pbc = False
    atoms.info.setdefault("charge", 0)
    atoms.info.setdefault("spin", 1)

predictor = pretrained_mlip.get_predict_unit(model, device=device)
atoms.calc = FAIRChemCalculator(predictor, task_name=task_name)

vib = Vibrations(
    atoms,
    indices=indices,
    name=vib_cache,
    delta=delta,
    nfree=nfree,
)

vib.run()
frequencies = vib.get_frequencies()
vib.summary(log=output_freq)
```

## Result JSON

On success, write at least:

```json
{
  "status": "success",
  "runner": "uma_vib_freq_runner",
  "input": "relaxed/POSCAR",
  "output": "vib.freq",
  "config": "results/resolved_uma_vib_config.json",
  "vib_cache": "vib_cache/",
  "results": {
    "n_atoms": null,
    "n_displaced_atoms": null,
    "n_modes": null,
    "frequencies_cm_minus_1": [],
    "n_imaginary_modes": null,
    "has_imaginary_frequency": null,
    "zero_point_energy_ev": null
  },
  "errors": []
}
```

On failure, still write structured JSON:

```json
{
  "status": "failure",
  "runner": "uma_vib_freq_runner",
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

- `results/resolved_uma_vib_config.json` is missing or invalid.
- The input POSCAR cannot be read.
- ASE is unavailable.
- FAIRChem/UMA is unavailable.
- Calculator creation fails.
- No atom indices are selected for a selected-atom calculation.
- ASE vibration execution fails.
- `vib.freq` or result JSON writing fails.

## Limits

- Do not decide model, task name, device, indices, delta, nfree, output paths, or
  cache paths.
- Do not generate VASP inputs.
- Do not run relaxation.
