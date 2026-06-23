---
name: surface-reaction-modeling-workflow
description: Autonomous router for catalyst surface reaction modeling. Use to drive end-to-end or multi-step setup — reaction species, gas references, bulk acquisition, slab generation with termination screening, adsorption-site/adsorbate placement, low-level-DFT screening then DFT refinement, and convergence/anomaly-gated result analysis — for CO2RR, NOxRR, HER, HOR, OER, ORR, AOR, NRR and related surface reactions. Proceeds with deterministic decision rules and no human stops except true escalation.
---

# Surface Reaction Modeling Workflow

## Purpose

Router skill for surface reaction modeling. It does not replace the lower-level
skills; it forces the right order, makes the branch decisions **automatically**,
and gates expensive calculations on verifiable evidence so the pipeline runs
**unattended**.

## Operating principles

1. **Autonomous progress.** Every branch is a deterministic decision rule with an
   explicit tie-break. Do not stop to ask the user except for the few escalation
   conditions at the end. "Ambiguous" is resolved by the rules below, not by a
   prompt.
2. **Screening first, refine few.** Use low-level DFT (vasp-job screening
   profile) as the first filter for terminations and sites; promote only a small
   selected set to refinement DFT.
3. **UMA is opt-in.** Do not use UMA/MLIP unless the user explicitly asks.
   Geometry is cleaned by build → low-level DFT relax, not by UMA preopt.
4. **Gate on evidence.** After any relaxation, run
   `calculation-result-analyzer` and branch on its `verdict`
   (pass/warn/fail) — never trust an endpoint by eye in unattended mode.
5. **Reuse, don't re-type.** Use vasp-job `extends` (common_refinement.yml /
   common_screening.yml) so jobs differ only by structure + a few overrides.
6. **One folder convention.** All artifacts follow the layout in
   "Folder & naming convention"; pass explicit `--outdir`/`project`/`job_name`.

## Two-phase order

Decide the surface before doing anything on it.

- **Phase 1 — determine the surface.** Generate every termination and screen them
  **all** with low-level DFT (the termination DFT screening loop). Rank by surface
  energy and pick the single most promising termination. No adsorbates or
  refinement happen in Phase 1.
- **Phase 2 — model on the chosen surface.** Take that one most-promising surface
  and proceed: site inspection → adsorbate placement → low-level DFT screening of
  candidates → refinement DFT of the best few, each analyzer-gated.

Do not start Phase 2 on multiple terminations in parallel and do not refine
adsorbates before the surface is fixed.

## Skill chain

1. `reaction-pathway-balancing` — resolve the reaction family / elementary steps
   into balanced species and named intermediates.
2. `build-gas-phase-models` — neutral gas references; carries `spin_reference`
   and `dipole_hint` for vasp-job to apply.
3. **Bulk acquisition** — fetch from Materials Project (`build-slab-models
   --formula`) or start from a local/code-generated bulk
   (`build-slab-models --bulk-file`) when the system is multicomponent and absent
   from MP.
4. `build-slab-models` — clean slab from the bulk, with the termination decision
   below.
5. `inspect-surface-sites` — read-only site landscape when the surface exposes
   multiple species/site types.
6. `place-surface-adsorbates` — bounded automatic placement.
7. `vasp-job` — low-level DFT screening first, then refinement on the selected
   set; unattended polling + restart per its SKILL.
8. `calculation-result-analyzer` — convergence + anomaly verdict after every
   relaxation; drives accept / restart / drop.

## Decision rules

These replace human-gated "stops". Apply them in order; act on the result.

### D1: Reaction species
Proceed once the family/steps are named and intermediates resolve to
labels/formulas/SMILES. Never claim energies from structure generation alone.

### D2: Gas references
Build a neutral POSCAR for each needed gas reservoir/product. Apply
`spin_reference` (ispin/nupdown) and `dipole_hint` (ldipol/idipol) downstream in
vasp-job. No charge inference.

### D3: Bulk
- If an MP id is given, use it. Else if `--bulk-file` is provided/needed
  (multicomponent not in MP), start from it. Else fetch by formula and select the
  lowest energy-above-hull candidate.
- Record `bulk_source` (mp/local). One bulk per material proceeds automatically.

### D4: Termination — fix the surface FIRST by screening every termination
The surface must be decided before any site/adsorbate/refinement work (see
"Two-phase order"). Decide it by screening, not by the heuristic alone.
1. Enumerate **all** terminations with `--all-terminations`; read
   `termination_summary.json`.
2. **Single termination** → use it.
3. **Multiple** → run the **termination DFT screening loop** (below) over **every
   generated termination** at the lowest practical DFT level and auto-select the
   single most promising surface by surface energy γ. Do not pre-trim to a few;
   screen them all (the heuristic `score` only sets the evaluation order, not the
   shortlist). The only exception is an impractically large termination count —
   then keep the cheapest level and the heuristically-best subset, and record the
   cap as an escalation note (not a silent shortcut).
4. **Polar**: prefer a non-polar candidate. If none exists, pick the
   least-polar/symmetric candidate and enable dipole correction
   (`ldipol: true`, `idipol: 3`) for its calculations; record the caveat.

Tie-break order when several remain equal on γ: non-polar → symmetric top/bottom
→ stoichiometric → closest to `target_n_atoms` → lowest termination index.

### D5: Sites
Enumerate the intended site types on the selected termination with a bounded
count. If the exposed top-layer chemistry conflicts with the intended
reaction/site, prefer the matching site type automatically; only escalate if no
compatible site exists.

### D6: Adsorbate placement
Generate bounded placement candidates with valid POSCAR + metadata and passing
minimum-distance. Cap the candidate count (see escalation E3).

### D7: Calculation handoff
Screen the candidate set with low-level DFT (screening profile), gate each with
the analyzer, then promote the best small subset to refinement DFT. Do not
submit a refinement job for every generated structure.

## Termination DFT screening loop (Phase 1 — decide the surface)

Goal: pick the single most promising termination without a human by screening
**all** of them cheaply, then hand only that surface to Phase 2.

1. Save **every** generated termination (`--all-terminations`) as separate slabs.
2. Compute a bulk per-atom energy once: a screening bulk relax (`task: bulk`,
   `common_screening.yml`).
3. For **each** termination: screening slab relax (`task: slab`, lowest practical
   level), then `calculation-result-analyzer`. Discard `fail` candidates.
4. Surface energy `γ = (E_slab − n_slab · E_bulk_per_atom) / (2A)` where `A` is the
   in-plane cell area. Compare all surviving terminations on γ.
5. Auto-select the single lowest-γ termination that is
   non-polar/symmetric/stoichiometric (D4 tie-break otherwise). Record γ for every
   termination. **This one surface is the input to Phase 2.**

Screen all by default — this is the cheap, exhaustive pass that determines the
surface. Only fall back to a heuristically-best subset if the count is
computationally impractical, and record that as an escalation note. UMA preopt
may replace step 3's geometry cleanup **only if the user explicitly enabled UMA**.

## Calculation policy

- **Default = refinement** for the final selected set; **screening** is the
  first-pass filter for terminations/sites and for broad triage. Both use
  `kspacing 0.30`.
- Reuse params with vasp-job `extends`: `common_screening.yml` for screening,
  `common_refinement.yml` for refinement; the job spec adds only `task` params,
  system overrides (ismear/sigma, ispin/magmom from gas `spin_reference`), and
  structure.
- `freq` only on selected relaxed endpoints and only when explicitly requested.
- After each relaxation: run `calculation-result-analyzer`. It renders the
  overlay PNGs and writes `visual_review_request.json`; **open the PNGs, judge
  whether the structure stayed physically sane, and write `visual_review.json`**,
  then re-run/ingest so the overall verdict includes the visual gate. Without
  this step the visual gate stays `pending` and holds the verdict at `warn`.
- Branch on the overall verdict → `pass` accept; `warn` accept with caveat (treat
  convergence-`warn` as `fail` when fully unattended); `fail` →
  `diagnose_vasp_failure.py` → bounded auto-restart (continue from CONTCAR, ALGO
  switch, POTIM reduce) up to the retry cap, else drop the candidate.

## Folder & naming convention (enforced)

Pass explicit output paths so artifacts are traceable. Use lowercase with
`_`/`-` only.

`<project>` defaults to `./<system-or-reaction-label>` under the current working
directory (e.g. `./co2rr_cu`), unless the user gives an explicit root. This is the
fixed default — do not invent ad-hoc folder names like `dft/`, `screening/`, or
`opt/` outside this layout.

```
<project>/
  bulk/<formula>_<mpid|local>/
  slab/<formula>_<mpid|local>_<hkl>_term<N>/
  gas/<species>/
  calc/<stage>/<system>__<task>__<level>/    # stage: screening | refinement
  analysis/<job_uid>/
```

- `<level>` = `dft-screen` | `dft-refine` | `uma` (`uma` only when explicitly
  enabled). `<task>` = `bulk|slab|gas|freq|static`. `<system>` encodes
  material+facet+adsorbate, e.g. `co_pt111_fcc`.
- Map to tools: `build-slab-models --outdir <project>/slab/...`,
  `build-gas-phase-models --outdir <project>/gas/<species>`,
  `calculation-result-analyzer --outdir <project>/analysis/<job_uid>`.
- vasp-job: `project: <stage>`, `job_name: <system>__<task>__<level>__NNN`
  (NNN zero-padded). This binds structure provenance to the job directory 1:1.

## Escalation conditions (the only stops)

Stop and ask only when automatic progress is physically impossible:

- no termination candidate survives screening (all `fail`);
- bulk acquisition fails (no MP match and no `--bulk-file`);
- no adsorption site is compatible with the intended reaction;
- the retry budget is exhausted for every candidate at a required step;
- an external resource is unavailable (MP/API key, queue, vasp-job CLI).

Multiple viable terminations/sites/adsorbates are NOT a stop — resolve them with
the decision rules and tie-breaks above.

## Output contract

Report:
- reaction family and intermediates;
- gas reference POSCAR/metadata paths (+ applied spin/dipole);
- bulk source (mp id or local file), Miller index, backend;
- termination decision: candidates considered, γ per screened candidate, the
  auto-selected termination, and any polar/asymmetry caveat;
- selected site types and adsorbate placement count;
- generated POSCAR/metadata paths under the folder convention;
- per-job analyzer `verdict` and any restart/drop actions taken;
- which results are screening (non-final) vs refinement.
