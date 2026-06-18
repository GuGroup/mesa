# UMA Relaxation Runner

## Purpose

Run a fixed UMA-based ASE relaxation and write the optimized POSCAR plus structured relaxation metadata.

## Position in MESA Pipeline

This external skill runs after POSCAR validation and usually after UMA single-point evaluation. Its `optimized/POSCAR` output is the final downstream structure artifact for DFT input generation.

## Inputs

Input JSON fields include `poscar_path`, `output_poscar`, `mlip_settings`, `relaxation_settings`, `results_dir`, `logs_dir`, `dry_run`, and optional `fixed_atom_indices` for surface mode. `mlip_settings` contains `model`, `task`, and `device`; `relaxation_settings` contains `relax_type`, `fmax`, and `steps`.

This runner does not decide `model`, `task`, `device`, or relaxation policy. Codex or the workflow controller must provide those choices under `mlip_settings` and `relaxation_settings`.

## Outputs

The runner writes `optimized/POSCAR`, `results/uma_relaxation.json`, and ASE optimizer logs under `logs/`. The metadata includes final energy, final max force, convergence, atom counts, volumes, and collapse checks.

## Algorithm

1. Resolve paths and create output directories.
2. In dry-run mode, write skipped metadata and do not import or call UMA.
3. Import ASE and read the POSCAR.
4. Attach the FAIRChem/UMA calculator.
5. For `geometry`, relax atomic positions with fixed cell.
6. For `cell`, relax a cell filter through ASE.
7. For `surface`, relax positions and optionally fix provided atom indices.
8. Write `optimized/POSCAR` and `results/uma_relaxation.json`.

## Dependencies

Real execution requires ASE and FAIRChem/UMA. CUDA may be required when `device=cuda`. Dry-run uses only the Python standard library.

## Failure Modes

The runner returns structured failure when relaxation type is invalid, the POSCAR path is missing, the POSCAR file is not found, dependencies are missing, calculator creation fails, ASE optimization fails, or output writing fails.

## Example

```json
{
  "poscar_path": "POSCAR",
  "output_poscar": "optimized/POSCAR",
  "mlip_settings": {
    "model": "uma-s-1p2",
    "task": "omat",
    "device": "cuda"
  },
  "relaxation_settings": {
    "relax_type": "geometry",
    "fmax": 0.05,
    "steps": 300
  },
  "dry_run": false
}
```

## Validation

Use dry-run to validate CLI wiring without dependencies. In a UMA environment, run on a small POSCAR and verify `optimized/POSCAR`, `converged`, and `final_max_force_eV_per_A`.

## Limitations

Surface mode only applies fixed indices when explicitly provided. The runner does not infer UMA task, select runtime device, choose relaxation policy, generate VASP inputs, or run VASP.
