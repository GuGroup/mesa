# Minimal Methods Evidence Schema

## Output Files

`methods_minimal_evidence.json` is the deterministic evidence source.

`methods_writer_digest.json` is the direct input for a later Methods prose
writer. It contains the same four sections plus writer rules.

`methods_evidence_summary.md` is a human-readable run summary.

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

- Include strategy `methods`, `dft_details.code`, core DFT setting fields, and
  relaxation summary counts.
- Include the VASP execution boundary as a data field.

Vibrational/free-energy corrections:

- Include `dft_details.thermodynamic_corrections`.
- Include compact UMA vibration summary fields and surface thermal policy.
- Include brief energy-bookkeeping tool metadata.

Electrochemical formalism:

- Include relevant strategy free-energy/reference method lines.
- Include compact `reference_policy.json` fields.
- Include brief energy-bookkeeping tool metadata.

Do not include descriptor-analysis, electronic-structure-analysis, or standalone
limitations sections in this version.
