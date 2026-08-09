# Minimal Methods Evidence Schema

## Output Files

`methods_minimal_evidence.json` is the deterministic evidence source.

`methods_writer_digest.json` is the direct input for a later Methods prose
writer. It contains the same four sections plus writer rules and a compact
thermodynamic formalism record.

`methods_evidence_summary.md` is a human-readable run summary.

The top-level `backend_policy` records the resolved calculator branch. It is
authoritative for downstream prose and citation selection. UMA-only evidence
must not expose stale VASP/PBE/PAW settings or their canonical citations.

## Section Contract

The collector always emits exactly four sections:

- `model_construction`
- `geometry_optimization`
- `vibrational_free_energy_corrections`
- `electrochemical_free_energy_formalism`

Each section contains:

- `section_id`
- `title`
- `strategy_inputs`
- `project_details`
- `procedure_inputs`

## Minimal Field Rules

Model construction:

- Include strategy `models`, `dft_details.slab_model`, and
  `dft_details.adsorption_sites`.
- Include only `motif_label` and `state` values from `model_manifest.records`.
- Include one gas metadata example with only `formula`, `cell_lengths`, and
  `pbc`.

Geometry optimization:

- Include strategy `methods`, DFT setting fields only when
  `backend_policy.allows_dft` is true, and relaxation summary counts.
- Include the calculation execution boundary as a data field; the resolved
  backend policy decides which calculator-specific fields are exposed.
- Preserve explicit calculator/backend, optimizer, force tolerance, maximum
  step, convergence, and relaxation-record fields when present. Do not infer
  FIRE, ASE, UMA, or any default convergence value.

Vibrational/free-energy corrections:

- Include `dft_details.thermodynamic_corrections`.
- Include compact UMA vibration summary fields and surface thermal policy.
- Include brief energy-bookkeeping tool metadata.
- Include gas pressure/standard-state, water activity/reference, Gibbs
  correction, and electrochemical formalism fields only when present in the
  source evidence.

Electrochemical formalism:

- Include relevant strategy free-energy/reference method lines.
- Include compact `reference_policy.json` fields.
- Include brief energy-bookkeeping tool metadata.
- Preserve CHE/SHE/RHE, pH, potential, water, gas, and equation fields when
  explicitly supplied by the reference policy or strategy methods.

Do not include descriptor-analysis, electronic-structure-analysis, or standalone
limitations sections in this version.
