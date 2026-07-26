---
name: assemble-oer-energy-corrections
description: Assemble and audit OER DFT free-energy corrections for the four-step adsorbate-evolution mechanism using *OH, *O, *OOH, H2/H2O references, an explicit O2 thermodynamic cycle, CHE potential/pH bookkeeping, closure checks, limiting potential, and thermodynamic overpotential. Use for OER energy diagrams, O2 correction, 4.92 eV water-splitting closure, catalyst/motif rankings, or review of duplicated/mis-signed OER corrections. Do not use for lattice-oxygen pathways, barriers, current density, Tafel slopes, or universal *OH/*OOH solvation offsets.
---

For MESA end-to-end use, read `SKILL/analysis/workflow.md` first when that file exists.

# OER Energy-Correction Bookkeeper

## Scope

Use this skill after relaxation, vibration/thermal correction, and evidence gating have produced endpoint energies for:

- `clean` (`*`)
- `OH` (`*OH`)
- `O` (`*O`)
- `OOH` (`*OOH`)

The default mechanism is the four-step adsorbate-evolution mechanism (AEM):

1. `* + H2O -> *OH + (H+ + e-)`
2. `*OH -> *O + (H+ + e-)`
3. `*O + H2O -> *OOH + (H+ + e-)`
4. `*OOH -> * + O2 + (H+ + e-)`

This is a bounded thermodynamic workflow. It does not establish a kinetic rate, measured overpotential, active-site population, or lattice-oxygen mechanism.

## Mandatory correction policy

1. Prefer an explicitly documented `H2O/H2` thermodynamic cycle for `O2` when direct semilocal-DFT `O2` is not trusted.
2. Never apply both a cycle-derived `O2` and an additional `O2 overbinding correction`.
3. Treat `4.92 eV` as a conditional 298.15 K standard-state cycle value, not a universal electronic-energy shift.
4. Keep `H2O(g) -> H2O(l)` correction separate and documented.
5. Do not add universal solvation constants to `*OH` or `*OOH`; require motif/model-specific evidence.
6. Reject records that provide both complete `free_energy_ev` and additive electronic/correction components.
7. Verify that the four step energies sum to the selected overall water-splitting free energy.
8. Rank only by AEM/CHE thermodynamic overpotential after closure passes.

Read `references/oer-correction-policy.md` before interpreting results. Read
`references/literature-and-provenance.md` before assigning a cycle constant,
direct-O2 correction, or evidence label.

## Quick start

```bash
python scripts/compute_oer_corrections.py \
  --input path/to/oer_endpoints.json \
  --outdir path/to/oer_outputs \
  --strict
```

The script accepts either MESA `free_energy_records` or a standalone `motifs + references` object. Read `references/input-schema.md`.

## Calculated quantities

At the selected electrode scale, the script calculates all four step free energies at `U = 0` and at the requested potential. On the RHE scale each OER PCET step shifts by `-eU`. On the SHE scale it additionally includes the explicit pH term.

For a cycle reference:

```text
G(O2) = 2 G(H2O) - 2 G(H2) + DeltaG_cycle
```

The thermodynamic limiting potential and overpotential are:

```text
U_L = max(DeltaG_1, DeltaG_2, DeltaG_3, DeltaG_4) / e
eta_OER = U_L - U_eq
U_eq = DeltaG_cycle / 4e    (RHE convention)
```

## Required outputs

The helper writes:

- `oer_bookkeeping.json`
- `oer_descriptor_summary.csv/.json`
- `oer_step_summary.csv`
- `oer_profile_table.csv`
- `oer_activity_ranking.csv/.json`
- `oer_warnings.csv`

## Claim policy

Allowed:

- “Motif A has the lowest four-step AEM thermodynamic overpotential among the tested, closure-passing models.”
- “Step 3 is the potential-determining step within the stated CHE/AEM convention.”
- “The direct O2 reference differs from the selected H2O/H2 closure by X eV.”

Not allowed without separate evidence:

- “Motif A predicts the experimental current density or Tafel slope.”
- “The AEM is the true mechanism rather than a lattice-oxygen pathway.”
- “A single fixed *OOH solvation correction is transferable to all surfaces.”
