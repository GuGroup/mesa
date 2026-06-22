---
name: surface-reaction-modeling-workflow
description: Coordinate existing surface-modeling skills for catalyst reaction setup. Use when Codex needs an end-to-end or multi-step workflow involving reaction pathway species, gas-phase reference structures, slab generation, termination screening, adsorption-site inspection, adsorbate placement, structure validation, or cost-aware VASP dry-runs/submission for CO2RR, NOxRR, HER, HOR, OER, ORR, AOR, NRR, or related surface reaction modeling.
---

# Surface Reaction Modeling Workflow

## Purpose

Use this as the router skill for surface reaction modeling. It does not replace
the lower-level skills; it forces the right order and gate checks before any
expensive calculation.

## Skill Chain

1. `reaction-pathway-balancing`
   - Use first when the user gives a reaction family, net reaction, elementary
     step, or adsorbed intermediates.
   - Stop with balanced species and named intermediates; do not build structures
     before the species list is clear.
2. `build-gas-phase-models`
   - Use for gas reservoirs, gas products, and isolated molecular references.
   - Build neutral molecule POSCAR files only; charge, spin, relax, static, and
     frequency settings belong downstream in `vasp-job`.
3. `build-slab-models`
   - Use for clean slabs.
   - For multicomponent surfaces, oxides, nitrides, oxynitrides, carbides,
     sulfides, perovskites, polar directions, or ambiguous terminations, run
     termination screening before selecting a slab.
4. `inspect-surface-sites`
   - Use read-only before broad placement when the site landscape matters.
   - Inspect exposed species and candidate site types on the selected
     termination.
5. `place-surface-adsorbates`
   - Use only after a clean slab and intended site policy exist.
   - Use single-adsorbate scans or multi-adsorbate placement depending on the
     user's intent.
6. `vasp-job`
   - Use last. For actual VASP calculations, default to refinement settings on
     a small selected candidate set. Use screening settings only when the user
     explicitly asks for quick comparison, rough triage, or geometry sanity
     checks. Always run `prepare` before submit.

## Required Gates

Do not skip these gates unless the user explicitly chooses a shortcut.

### Gate 1: Reaction species

Pass when:

- reaction family or elementary steps are named;
- adsorbates/intermediates are resolved to labels, formulas, or SMILES;
- no DFT energies are claimed from structure generation alone.

### Gate 2: Gas-phase references

Pass when pathway metadata contains gas reservoirs/products and those references
are needed for downstream VASP jobs:

- gas species are resolved to labels or SMILES;
- neutral molecule POSCAR and metadata exist for each selected gas reference;
- metadata records `charge_spin_policy: unsupported`;
- relax/static/frequency calculations are deferred to `vasp-job`.

### Gate 3: Bulk and slab termination

Pass when:

- Materials Project id or selected bulk candidate is known;
- Miller index is explicit;
- `termination_summary.json` exists for ambiguous surfaces;
- `recommended_termination_candidates` has exactly one safe candidate, or the
  user explicitly chose a `--termination N`;
- `selection_warnings` have been reported if present.

If multiple candidates remain, stop and ask for a termination choice instead of
placing adsorbates.

### Gate 4: Surface site policy

Pass when:

- the selected clean slab has validation passing;
- exposed top-layer species are known;
- site types to enumerate are known, or the user accepted a bounded default;
- the number of candidates is bounded.

### Gate 5: Adsorbate placement

Pass when:

- each generated structure has POSCAR and metadata;
- placement site metadata is present;
- minimum-distance validation passes;
- the output set is summarized before any calculation handoff.

### Gate 6: Calculation handoff

Pass when:

- the candidate set is small;
- the user has selected which structures to calculate;
- VASP intent is explicit: actual calculation defaults to refinement, while
  screening is allowed only when explicitly requested for quick comparison or
  rough triage;
- `vasp-job prepare` is run before `vasp-job submit`;
- `freq` is not run unless explicitly requested for selected relaxed endpoints.

## Default Policies

- Prefer structure-generation and metadata validation before VASP.
- Once entering actual VASP calculation, prefer refinement defaults.
- Use VASP screening only when the user explicitly asks for quick comparison,
  rough triage, or low-cost geometry sanity checks; report it as non-final.
- Prefer explicit termination selection over term0 defaults.
- Prefer bounded site/adsorbate enumeration over full combinatorial expansion.
- Prefer metadata-backed decisions over visual guesses.
- Prefer dry-runs/spec generation before queue submission.
- Never submit a large VASP matrix just because many POSCAR files exist.

## Output Contract

For an end-to-end setup, report:

- reaction family and intermediates;
- gas reference POSCAR/metadata paths when gas species are present;
- bulk MP id, Miller index, backend, and termination choice;
- termination warnings and unique surface signatures;
- selected site types and adsorbate placement count;
- generated POSCAR/metadata paths;
- validation status;
- VASP calculation intent: refinement default for actual jobs, or explicit
  screening with a stated quick-comparison/triage reason;
- whether calculation output is only a dry-run/spec or an actual submitted job.

## Stop Conditions

Stop and request a user decision when:

- multiple safe termination candidates remain;
- only non-stoichiometric or asymmetric candidates are available;
- exposed surface chemistry conflicts with the intended reaction/site;
- many adsorbate/site combinations are possible and the user has not bounded
  the enumeration;
- the next step would submit VASP jobs for more than a small selected set.
