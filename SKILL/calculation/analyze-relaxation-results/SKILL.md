---
name: analyze-relaxation-results
description: >-
  Analyze existing UMA/MLIP or VASP relaxation outputs for endpoint acceptance,
  including force convergence, NSW/max-step termination, abnormal
  energy/force/RMSD behavior, and red/blue initial-final image review. Use before
  accepting catalyst relaxation endpoints for energetics or claims, or when
  deciding whether a clean max-step failure permits one steps-only continuation.
---

For MESA end-to-end work, read `SKILL/calculation/workflow.md` first.

# Relaxation Result Analyzer

Use the analyzer only on existing outputs; do not repair structures. Keep its
diagnosis logic separate from the optional revision helper below.

## Run

```bash
mamba run -n modeling python scripts/analyze_relaxation_result.py \
  --input path/to/result_or_trajectory \
  --outdir analysis/relaxation_result
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

## Limited UMA relaxation revision

For a clean max-step failure, run `scripts/decide_relaxation_revision.py` to
prepare one continuation with `2 × relaxation.steps`. Preserve the model,
optimizer, `fmax`, constraints, and other calculation settings. Add `--run` to
invoke the fixed UMA runner; otherwise, only write the retry config.

```bash
python3 scripts/decide_relaxation_revision.py \
  --summary analysis_summary.json \
  --config resolved_uma_config.json \
  --restart-poscar relaxed/POSCAR \
  --retry-dir retry_01 [--run]
```

Refuse warnings, structural anomalies, incomplete/non-passing three-view
review, and a second continuation. Re-analyze the retry normally. Read
`references/result-analyzer-policy.md` for the exact gate.

Batch runs must keep analyzer stdout/stderr in log files and report only compact
counts, warning classes, failed IDs, and review queues in user-facing updates.
