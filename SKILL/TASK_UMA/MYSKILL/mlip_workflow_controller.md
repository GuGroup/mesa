# MLIP Workflow Controller

## Purpose

Coordinate the MLIP-to-DFT handoff TASK by validating a POSCAR, resolving UMA defaults, planning or launching fixed UMA runner execution, assessing reliability, and preparing the final DFT handoff summary.

## Position in MESA Pipeline

This skill sits after structure generation or selection and before downstream VASP input generation. It prepares `optimized/POSCAR` as the only structure artifact that downstream DFT tasks should consume.

## Inputs

Input is a JSON object. Required field: `poscar_path` or `input_poscar`. Optional fields include `workdir`, `execution_mode`, `dry_run`, `mlip_settings`, and `relaxation_settings`. UMA settings must be provided under `mlip_settings`; relaxation settings must be provided under `relaxation_settings`. Top-level `model`, `task`, `device`, `relax_type`, `fmax`, and `steps` are not part of the controller input schema. Defaults are `model=uma-s-1p2`, `task=omat`, `device=cuda`, `relax_type=geometry`, `fmax=0.05`, and `steps=300`.

Canonical input schema:

```json
{
  "poscar_path": "POSCAR",
  "execution_mode": "local",
  "mlip_settings": {
    "model": "uma-s-1p2",
    "task": "omat",
    "device": "cpu"
  },
  "relaxation_settings": {
    "relax_type": "geometry",
    "fmax": 0.05,
    "steps": 300
  }
}
```

Codex must write settings only under `mlip_settings` and `relaxation_settings` when it creates controller input. The Python controller does not read Markdown files at runtime; any Codex-side decisions from the protocol documents must be serialized into this input JSON before invoking the controller.

## Outputs

The skill returns the standard MESA skill output dictionary. It writes `results/mlip_uncertainty_report.json` and `results/dft_handoff_summary.json`. When execution completes successfully, the downstream structure path is `optimized/POSCAR`.

## Algorithm

1. Resolve the working directory and input POSCAR path.
2. Create `optimized/`, `results/`, and `logs/`.
3. Validate that the POSCAR exists, is readable, non-empty, and structurally sane.
4. Resolve UMA and relaxation settings.
5. Build the qsub command using `EXTSKILL/scripts/run_mlip_dft_handoff.qsub.sh`.
6. In dry-run mode, return the plan and write unknown-status reliability and handoff summaries.
7. In qsub mode, submit the fixed qsub script and record scheduler metadata.
8. In local mode, call only `uma_singlepoint_runner.py` and `uma_relaxation_runner.py`.
9. Read available runner JSON files, assess reliability, and write the DFT handoff summary.

## Agent Runtime Contract

When Codex receives only a POSCAR path, Codex acts as the decision layer before Python execution:

1. Read this document and the relevant protocol documents.
2. Inspect the POSCAR and available runtime environment.
3. Choose `mlip_settings` and `relaxation_settings` using `mlip_dft_handoff_builder.md`.
4. Write a controller input JSON in the canonical schema.
5. Execute this controller.
6. Read generated JSON outputs and report either `optimized/POSCAR` or the blocking reason.

The controller is the execution orchestrator. It should receive already chosen settings from Codex or the upstream MESA agent.

## Failure Inspection Order

If execution fails or does not produce a ready handoff, inspect files in this order:

1. Controller output JSON.
2. `results/uma_singlepoint.json`.
3. `results/uma_relaxation.json`.
4. `results/mlip_uncertainty_report.json`.
5. `results/dft_handoff_summary.json`.
6. `logs/*.log`.

## Dependencies

The controller uses the Python standard library only. ASE is optional for POSCAR validation; if unavailable, the controller falls back to a conservative built-in POSCAR parser.

## Failure Modes

The controller returns `status: failure` when the POSCAR is missing, unreadable, empty, structurally invalid, qsub cannot be executed, or a fixed local runner fails. Diagnostics are recorded in `errors`.

## Example

```json
{
  "poscar_path": "POSCAR",
  "execution_mode": "dry-run",
  "mlip_settings": {
    "model": "uma-s-1p2",
    "task": "omat",
    "device": "cuda"
  },
  "relaxation_settings": {
    "relax_type": "geometry",
    "fmax": 0.05,
    "steps": 300
  }
}
```

## Validation

Run the unit tests from the repository root:

```bash
python -m unittest discover -s SKILL/TASK_MLIP_DFT_HANDOFF/tests -v
```

## Limitations

The controller does not run VASP, does not create VASP input sets, does not generate POTCAR content, and does not dynamically rewrite UMA execution code.
