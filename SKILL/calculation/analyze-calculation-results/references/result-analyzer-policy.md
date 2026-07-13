# Result Analyzer Policy

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
- `warn` -> `accepted-with-caveat`
- `fail`, missing summary, or incomplete strict visual validation -> `failed`
- registry `excluded` stays `excluded`
