# UMA Singlepoint Runner

## Purpose

Run a fixed UMA single-point calculation through ASE and write structured energy, force, and stress metadata.

## Position in MESA Pipeline

This external skill runs after POSCAR validation and before UMA relaxation and reliability assessment.

## Inputs

Input JSON fields include `poscar_path`, `mlip_settings`, `results_dir`, and `dry_run`. `mlip_settings` contains `model`, `task`, and `device`. Defaults are `model=uma-s-1p2`, `task=omat`, and `device=cuda`.

This runner does not decide `model`, `task`, or `device`. Codex or the workflow controller must provide those choices under `mlip_settings`.

## Outputs

The runner writes `results/uma_singlepoint.json` and returns the standard MESA skill output dictionary. The JSON includes status, model, task, device, energy in eV, forces, max force, stress when available, atom count, and timestamp.

## Algorithm

1. Resolve the POSCAR and results directory.
2. In dry-run mode, write skipped metadata and do not import or call UMA.
3. Import ASE and read the POSCAR.
4. Import FAIRChem/UMA and attach the UMA calculator to the ASE atoms object.
5. Compute potential energy, forces, max force, and stress when available.
6. Write `results/uma_singlepoint.json`.

## Dependencies

Real execution requires ASE and FAIRChem/UMA. CUDA may be required when `device=cuda`. Dry-run uses only the Python standard library.

## Failure Modes

The runner returns structured failure when the POSCAR path is missing, the POSCAR file is not found, ASE is missing, FAIRChem/UMA is missing, calculator creation fails, or the calculation raises an exception.

## Example

```json
{
  "poscar_path": "POSCAR",
  "mlip_settings": {
    "model": "uma-s-1p2",
    "task": "omat",
    "device": "cuda"
  },
  "results_dir": "results",
  "dry_run": false
}
```

## Validation

Use dry-run to validate CLI wiring without dependencies. In a UMA environment, run on a small POSCAR and verify finite `energy_eV` and `max_force_eV_per_A`.

## Limitations

The runner does not choose models dynamically, infer UMA task, select runtime device, submit scheduler jobs, or perform relaxation.
