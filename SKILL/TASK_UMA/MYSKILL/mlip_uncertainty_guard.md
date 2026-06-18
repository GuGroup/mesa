# MLIP Uncertainty Guard

## Purpose

Assess whether UMA single-point and relaxation outputs are reliable enough to hand an optimized structure to downstream DFT input generation.

## Position in MESA Pipeline

This protocol runs after fixed UMA runner execution and before the final DFT handoff summary.

## Inputs

Inputs are `results/uma_singlepoint.json`, `results/uma_relaxation.json`, the structure guard result, and the configured force threshold `fmax`.

## Outputs

The protocol writes `results/mlip_uncertainty_report.json` with `status` equal to `pass`, `warning`, `fail`, or `unknown`, plus checks, warnings, errors, and a short summary.

## Algorithm

1. Fail immediately if the structure guard failed.
2. Return `unknown` if runner outputs are not available yet.
3. Confirm that single-point execution succeeded and produced finite energy and force values.
4. Confirm that relaxation execution succeeded.
5. Confirm that final max force is finite and below `fmax`.
6. Confirm relaxation convergence, atom count preservation, and no obvious structure collapse.
7. Return `pass` with no warnings or errors, `warning` with non-fatal issues, or `fail` with blocking issues.

## Dependencies

This protocol uses controller-side JSON metadata and the Python standard library. It does not call UMA, ASE, qsub, or VASP.

## Failure Modes

The guard returns `fail` for invalid runner status, non-finite energy or force values, atom count changes, collapsed structures, or failed structure validation. It returns `warning` for missing convergence or force threshold warnings when no blocking failures are present.

## Example

```json
{
  "status": "pass",
  "summary": "MLIP reliability checks passed.",
  "checks": [
    {"name": "singlepoint_completed", "status": "success"},
    {"name": "relaxation_completed", "status": "success"}
  ],
  "warnings": [],
  "errors": []
}
```

## Validation

Unit tests can provide synthetic runner JSON data to the controller and confirm the generated reliability status and next action.

## Limitations

This is a protocol-level reliability screen, not a calibrated uncertainty model. It checks metadata consistency and physical sanity rather than model ensemble uncertainty.
