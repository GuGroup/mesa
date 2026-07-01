---
name: calculation-result-analyzer
description: Analyze UMA/MLIP and VASP calculation result trajectories for optimization divergence, non-monotonic energy behavior, multi-minima relaxation, RMSD jumps, force spikes, and visual-review frame selection; aggregate many analyzer outputs into project-level evidence readiness gates. Use when Codex needs to inspect relax.traj, ASE traj/extxyz/xyz, VASP vasprun.xml, OUTCAR, XDATCAR, or OSZICAR outputs, produce JSON/CSV diagnostics plus sampled aseview overlay artifacts, or classify many endpoints as accepted, accepted-with-caveat, failed, or excluded before downstream energetics/manuscript claims.
---

# Calculation Result Analyzer

## Scope

Use this skill after a UMA/MLIP or VASP calculation has produced result files.
The single-run analyzer reads trajectories and logs, computes convergence
diagnostics, selects frames that need visual inspection, and writes analysis
artifacts. The batch evidence gate reads many `analysis_summary.json` files and
turns them into project-level endpoint acceptance records.

Do not use this skill to run UMA, run VASP, optimize structures, or repair a bad
trajectory. It is a read-only analyzer, visual-review preparer, and evidence
gate over existing analyzer outputs.

## Automated verdict (for unattended gating)

`analysis_summary.json` reports a top-level `verdict` (`pass`/`warn`/`fail`) that
is the **severity max of two gates**: a numeric `deterministic_verdict` and the
`visual_validation` gate (below). The process exit code is `3` on a `fail`
overall verdict and `0` otherwise, so an unattended workflow can gate on it.

The deterministic gate:

- **fail** — not converged, or a hard problem. Triggers: final fmax above the
  force criterion; reached `NSW` step limit without convergence.
- **warn** — converged but something needs attention. Triggers: convergence
  could not be confirmed (no forces/criterion), non-monotonic energy, multiple
  significant minima, or an anomaly flag (bond broken/formed, possible
  desorption). The workflow decides whether the change was intended.
- **pass** — converged with no anomalies under the thresholds.

Convergence criterion (`fmax_threshold`) resolution order: `--fmax-threshold`
→ `|EDIFFG|` parsed from `vasprun.xml`/`INCAR`/`OUTCAR` → `0.05` eV/Å fallback.
`NSW` is read from the same VASP files (or `--nsw`). For MLIP/ASE `relax.traj`
with no VASP inputs, pass `--fmax-threshold` to match the optimizer's `fmax`.

The `anomalies` block detects "moved to a weird place": initial-vs-final
connectivity diff (`dissociation_suspected`/`new_bond_suspected` via covalent
radii) and, on slabs, upward lift-off along the surface normal
(`desorption_suspected`). RMSD/displacement use the minimum-image convention so
an atom crossing a periodic boundary is not a false jump.

## Visual validation (aseview PNG overlays + multimodal gate)

The analyzer renders **PNG overlays** the agent can actually look at, then folds
a multimodal review into the verdict. `aseview.save_png` is used directly
(headless), so this needs the `modeling` env's `aseview[export]` + a browser
(playwright's bundled chromium; declared in `ENVIRONMENT/build_tools/environment.yml`).

Default rendering:

- Uniformly sample up to `--overlay-max-frames` (default **50**) frames across the
  whole trajectory (always keeping first and last).
- Overlay **all** sampled frames (every frame visible, not just the first three)
  with MIC-unwrapped, non-rotated coordinates so an adsorbate walking across a
  periodic boundary stays continuous.
- Render three orthographic views — `overlay_top.png`, `overlay_side_a.png`,
  `overlay_side_b.png` — in the fixed style: Rowan, bonds on, atom size 0.7,
  `showCell` on.
- `--zoom-frames "0,12,30"` additionally renders `zoom_*.png` for just those
  indices (use after the full overlay to inspect a suspect region closely).
- `--no-visual` skips PNG rendering; `--chrome-path` overrides the browser.

Two-pass review (provider-neutral):

1. The analyzer writes `visual_review_request.json` listing the PNGs and the
   result schema, and sets `visual_validation.status = "pending"`.
2. The agent opens the PNGs, judges whether the relaxation stayed physically sane
   (no unintended desorption/dissociation/atoms-through-each-other/wrong site),
   and writes `visual_review.json` (`{"verdict": "pass|warn|fail", "reason": ...,
   "views_reviewed": [...]}`) into the outdir.
3. Re-run (or pass `--visual-review <file>`) to ingest it; `status` becomes
   `completed`.

Gate aggregation (overall = severity max, **downgrade-only**):

- `completed` → overall = max(deterministic, review). A review may keep or worsen
  the deterministic verdict, never upgrade it.
- `pending` / `unavailable` / `invalid` → floor at `warn` (missing coordinates or
  a failed render is a problem, not a free pass).
- `--skip-visual-validation` → overall = deterministic (PNGs still rendered;
  `status = "skipped"`).

## Quick Start

Script paths are relative to this skill directory. Run in the `modeling` env
(the script needs slabuilder/ASE/aseview; bare `python` is not on PATH).

```bash
mamba run -n modeling python scripts/analyze_calculation_result.py \
  --input path/to/run_directory_or_trajectory \
  --outdir analysis/calculation_result
```

Common inputs:

```bash
mamba run -n modeling python scripts/analyze_calculation_result.py --input relax.traj --outdir analysis/uma_relax
mamba run -n modeling python scripts/analyze_calculation_result.py --input vasprun.xml --outdir analysis/vasp_relax
mamba run -n modeling python scripts/analyze_calculation_result.py --input OSZICAR --outdir analysis/oszicar_only
```

Optional smoke/demo run:

```bash
mamba run -n modeling python scripts/make_demo_surface_jump.py --output /tmp/demo_surface_jump.extxyz
mamba run -n modeling python scripts/analyze_calculation_result.py --input /tmp/demo_surface_jump.extxyz --outdir /tmp/demo_surface_jump_analysis
```

After all per-endpoint `analysis_summary.json` files exist and visual reviews
are completed, aggregate them into downstream evidence readiness:

```bash
python scripts/gate_calculation_evidence.py \
  --analysis-root analysis/final_relaxations \
  --batch-summary analysis/final_relaxations/analysis_batch_summary.json \
  --registry path/to/final_relaxation_registry.json \
  --outdir analysis/final_relaxations/evidence_gate \
  --project-root /path/to/project-root
```

Use `--allow-incomplete-visual` only for exploratory bookkeeping. For manuscript
or downstream free-energy work, keep the default strict visual gate so endpoints
with `pending`, `unavailable`, or `invalid` visual validation do not pass
silently.

## Outputs

The single-run analyzer writes:

| Artifact | Purpose |
| --- | --- |
| `analysis_summary.json` | Machine-readable overall `verdict`, `deterministic_verdict`, `visual_validation` (status/paths/review), `convergence` (criterion, converged, NSW), `run_parameters` (EDIFFG/NSW), `anomalies` (dissociation/desorption), diagnosis, warnings, selected frames, and output paths. |
| `overlay_{top,side_a,side_b}.png` | Uniform≤50-frame overlay orthographic views (Rowan style, bonds on, atom size 0.7) for multimodal review. |
| `zoom_{top,side_a,side_b}.png` | Zoomed overlay of the `--zoom-frames` indices, when requested. |
| `visual_review_request.json` | What the agent must inspect + the result schema for `visual_review.json`. |
| `visual_review.json` | (agent-written) The multimodal verdict ingested into the overall verdict. |
| `metrics.csv` | Per-step energy, max force, RMSD, and jump metrics. |
| `selected_frames.extxyz` | Event/uniform sampled frames for overlay review when structures are available. Includes per-atom `analysis_disp_to_initial` and `analysis_disp_step` arrays for displacement coloring when the viewer supports scalar properties. |
| `visual_review.md` | Human-readable interpretation and aseview commands. |
| `aseview_trajectory.html` / `aseview_overlay.html` | Optional HTML viewers (`--no-html` to skip). |

The batch evidence gate writes:

| Artifact | Purpose |
| --- | --- |
| `evidence_readiness_summary.json` | Project-level counts and records for accepted, accepted-with-caveat, failed, and excluded endpoints. |
| `endpoint_triage.csv` / `endpoint_triage.json` | Flat endpoint table with verdicts, visual status, final energy/fmax, caveats, and source paths. |
| `visual_review_queue.md` | Human-readable queue of endpoints still needing visual/evidence review or marked failed. |

Acceptance policy:

- `pass` with completed/skipped visual validation -> `accepted`.
- `warn` with completed/skipped visual validation -> `accepted-with-caveat`.
- `fail`, missing summaries, or incomplete visual validation under the default
  strict gate -> `failed`.
- Registry records already marked `excluded` remain `excluded`; do not replace
  missing evidence with a geometry-only proxy.

## Diagnostic Policy

Check these signals before trusting the endpoint:

1. **Energy monotonicity**
   - Flag if energy increases above tolerance.
   - Mark local minima and significant multi-minima candidates when energy
     basins are separated by both energy rise and structural RMSD.
2. **Force behavior**
   - Track `fmax` when forces are present.
   - Flag large step-to-step `fmax` jumps and non-decreasing high-force tails.
3. **RMSD behavior**
   - Align structures to a stable anchor before comparing.
   - For slabs, prefer fixed atoms when present; otherwise use bottom-layer
     atoms as the alignment anchor.
   - Flag large adjacent-frame RMSD jumps and large max-atom displacement
     jumps.
4. **Visual sampling**
   - Always include first and last frames.
   - Add uniform samples across the trajectory.
   - Add frames around energy increases, RMSD jumps, force spikes, and local
     minima.

## Anchor Policy

Use `--anchor auto` by default:

- if `FixAtoms` constraints exist, align on fixed atoms;
- otherwise, if the structure is slab-like, align on the bottom z-fraction;
- otherwise, align on all atoms.

Use `--anchor none` only when raw coordinate drift is itself the signal being
investigated.

## aseview Review

Open selected frames with:

```bash
mamba run -n modeling aseview selected_frames.extxyz -v overlay --cmap viridis -o aseview_overlay.html
```

Interpretation:

- overlay frames should be slab-aligned, not center-of-mass aligned, for surface
  calculations;
- use `analysis_disp_to_initial` or `analysis_disp_step` as the scalar field
  when a viewer supports per-atom property coloring;
- use the aseview viewer's built-in Export PNG/GIF controls when a static image
  is required; do not generate separate matplotlib previews for structure
  review;
- frames with high RMSD or force jumps should be checked for adsorbate flipping,
  diffusion, dissociation, slab reconstruction, atom crossing periodic
  boundaries, or loss of fixed-layer behavior;
- multiple local minima are not automatically wrong, but they mean the final
  endpoint may depend on starting geometry or optimizer path.

## Boundaries

- The `verdict` is a convergence/anomaly gate, not a claim of physical
  correctness. A `warn` still merits the overlay review before trusting the
  endpoint; only `pass` should auto-proceed unattended.
- Do not claim final DFT validity from this analyzer alone.
- Do not use OSZICAR-only analysis for structural conclusions; OSZICAR has no
  trajectory coordinates.
- Do not discard a calculation solely because one metric flags; inspect the
  sampled overlay frames first.
- Do not let the batch evidence gate upgrade a per-endpoint analyzer verdict;
  it can only preserve or downgrade endpoint usability.
- Do not overwrite calculation outputs.
