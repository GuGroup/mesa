# Relaxation Result Analyzer Policy

Load only when editing the analyzer or interpreting a nontrivial report.

## Fixed Checks

- Force criterion: `--fmax-threshold` → parsed `|EDIFFG|` → `0.05 eV/Å`.
- `NSW`: parsed from VASP files or supplied by `--nsw`.
- Large energy change: `|E_final - E_initial| >= 15 eV` -> `warn`.
- Rough initial `fmax ~ 5 eV/Å` is acceptable.
- Post-early `fmax > 3 eV/Å` -> `warn`.
- RMSD tail drift `> 0.1 Å` over final 25% usable frames -> `warn`.

## Review Order

1. Final `fmax` vs criterion.
2. `NSW`/max-step termination.
3. Energy, late `fmax`, RMSD, and anomaly warnings.
4. Red/blue endpoint PNGs.

## Warning Triage

Do not treat all `warn` endpoints as equivalent. Aggregate warnings by class
before downstream energy tables or manuscript claims:

- `visual_review_incomplete` from pending, unavailable, invalid, or missing
  visual review: keep out of uncaveated evidence; create a review queue with
  image paths.
- bond breaking, new bonds, desorption, site migration, flipping, or slab
  reconstruction: inspect images and either fail/exclude or name the structural
  change as a caveat.
- energy/force/RMSD trend warnings: keep only with numerical caveats unless
  they indicate nonconvergence or a bad endpoint.
- max-step/nonconverged endpoints: fail or exclude; do not convert to
  accepted-with-caveat.

Batch summaries must report warning-class counts and representative endpoint
IDs, not only total `warn` counts.

## Images

Required review images:

- `initial_final_top.png`
- `initial_final_side_a.png`
- `initial_final_side_b.png`

Red is initial; blue is final. Check wrong-site migration, flipping,
dissociation, desorption, slab reconstruction, or fixed-layer failure.

## Outputs

- `analysis_summary.json`
- `metrics.csv`
- `initial_final_{top,side_a,side_b}.png`
- `visual_review_request.json`
- `visual_review.md`
- optional `visual_review.json`
- optional `selected_frames.extxyz`

## Batch Gate

- `pass` -> `accepted`
- `warn` -> triage first, then `accepted-with-caveat`, `failed`, or `excluded`
- `fail`, missing summary, or incomplete strict visual validation -> `failed`
- registry `excluded` stays `excluded`

## Limited UMA Max-Step Continuation

`scripts/decide_relaxation_revision.py` permits one automatic continuation only
when all of these are true:

- overall verdict is `fail`, force nonconvergence is confirmed, and `nsw_reached`
  is true;
- `warn_reasons` is empty;
- visual review is completed with `pass` for top and both side views;
- no connectivity change, dissociation, new bond, or desorption is flagged;
- no prior automatic continuation is recorded.

Start the continuation from the failed endpoint. Among scientific control
settings, change only `relaxation.steps`, to twice its prior value. Keep the
model, optimizer, `fmax`, constraints, and all other settings fixed. Analyze
the new trajectory from the beginning; never inherit the previous verdict.

## Log Discipline

Default analyzer stdout is compact. Full JSON belongs in `analysis_summary.json`
or per-endpoint log files. Batch runners must redirect analyzer stdout/stderr
to endpoint-local logs and print only progress counts plus paths to summaries.
