---
name: collect-methods-evidence
description: Deterministically collect a minimal four-section Methods evidence source for computational chemistry catalyst projects. Use before Methods prose writing when Codex needs methods_minimal_evidence.json and methods_writer_digest.json from selected_strategy experiment.computational models/methods/dft_details/procedures, model_manifest motif_label/state values, one gas metadata example, UMA relaxation/vibration summaries, reference_policy, and brief energy-bookkeeping tool information without descriptor, electronic-structure, or standalone limitations sections.
---

For MESA end-to-end use, read `SKILL/manuscript/workflow.md` before applying this skill.

# Methods Evidence Collector

## Scope

Use this skill before Methods prose writing. It creates a minimal deterministic
source for only the four core Methods sections:

1. `model_construction`
2. `geometry_optimization`
3. `vibrational_free_energy_corrections`
4. `electrochemical_free_energy_formalism`

It does not write manuscript prose, polish text, validate claims, or include
descriptor-analysis, electronic-structure-analysis, or standalone limitations
sections.

Default output:

```text
project/<project>/strategy_execution/<strategy_id>_methods/evidence/
  methods_minimal_evidence.json
  methods_writer_digest.json
  methods_evidence_summary.md
```

## Workflow

Run:

```bash
python SKILL/manuscript/methods/collect-methods-evidence/scripts/collect_methods_evidence.py \
  --project project/<project> \
  --strategy-id <strategy_id>
```

Defaults:

```text
strategy:       project/<project>/strategy_execution/strategy_selection/selected_strategy.json
execution root: project/<project>/strategy_execution/<strategy_id>_execution
outdir:         project/<project>/strategy_execution/<strategy_id>_methods/evidence
```

Override paths when needed:

```bash
--strategy path/to/selected_strategy.json
--execution-root path/to/S1_execution
--outdir path/to/evidence
```

By default the script removes older large evidence outputs from the output
directory: `methods_raw_evidence.json`, `methods_section_packets.json`,
`methods_procedure_evidence.json`, and `methods_execution_category_digest.json`.
Use `--keep-legacy` only when comparing old and new schemas.

## Extraction Rules

- Read the active `project/<project_name>/project_profile.md` calculation
  policy before interpreting calculator-specific fields.
- Always include the strategy computational block:
  `models`, `methods`, `dft_details`, and `procedures`.
- Collect available `dft_details`, but let the active profile decide whether
  those fields imply VASP input preparation or are merely retained context.
- For model details, extract only `records.motif_label` and `records.state`
  from `model_manifest.json`; current artifacts do not store full slab-builder
  arguments.
- For gas-model details, extract one gas metadata example, preferring H2, with
  only `formula`, `cell_lengths`, and `pbc`.
- For energy/free-energy details, include brief internal tool metadata and
  `reference_policy.json`. A later writer must translate tool names into public
  academic language and must not cite internal skill names directly.
- Do not add descriptor analysis, electronic-structure analysis, or a standalone
  limitations section in this version.

Read [references/evidence_schema.md](references/evidence_schema.md) when
consuming or revising the JSON contract.
