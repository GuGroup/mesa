---
name: analyze-calculation-results
description: >-
  Analyze existing UMA/MLIP or VASP relaxation outputs for endpoint acceptance,
  including force convergence, NSW/max-step termination, abnormal
  energy/force/RMSD behavior, and red/blue initial-final image review. Use before
  accepting catalyst relaxation endpoints for energetics or claims.
---

For MESA end-to-end work, read `SKILL/calculation/workflow.md` first.

# Calculation Result Analyzer

Use only on existing outputs. Do not run calculations or repair structures.

## Run

```bash
mamba run -n modeling python scripts/analyze_calculation_result.py \
  --input path/to/result_or_trajectory \
  --outdir analysis/calculation_result
```

For MLIP trajectories with a non-default optimizer target, pass
`--fmax-threshold`. VASP runs use parsed `|EDIFFG|` and `NSW` when available.

## Check

1. Final `fmax` reached the criterion?
2. Did the run stop by `NSW`/max ionic steps?
3. Any energy, late-`fmax`, RMSD, bond-change, or desorption warning?
4. Open `initial_final_{top,side_a,side_b}.png`: red = initial, blue = final.
5. For every `warn`, record the warning class and decision: keep with caveat,
   require visual/manual review, fail, or exclude. Do not collapse many warns
   into one generic "accepted-with-caveat" statement.

Verdict:

- `fail`: not force-converged, or max steps reached without convergence.
- `warn`: converged but suspicious numerics or endpoint geometry.
- `pass`: converged with no warnings.

For thresholds, output fields, and batch-gate policy, read
`references/result-analyzer-policy.md`.

Batch runs must keep analyzer stdout/stderr in log files and report only compact
counts, warning classes, failed IDs, and review queues in user-facing updates.
