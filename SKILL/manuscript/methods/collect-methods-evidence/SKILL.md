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
--backend-mode uma_mlip   # optional explicit calculator branch override
```

By default the script removes older large evidence outputs from the output
directory: `methods_raw_evidence.json`, `methods_section_packets.json`,
`methods_procedure_evidence.json`, and `methods_execution_category_digest.json`.
Use `--keep-legacy` only when comparing old and new schemas.

## Extraction Rules

- Read the active `project/<project_name>/project_profile.md` calculation
  policy before interpreting calculator-specific fields.
- Resolve the active calculator branch from the explicit override,
  active project profile, explicit computational backend fields, and only then
  methods/procedures. An authoritative project profile wins over stale strategy
  prose.
- In `uma_mlip` mode, stale `dft_details` are not copied into the evidence:
  VASP, PBE, PAW, plane-wave, k-point, and DFT-D3 fields and citation anchors
  are omitted. In `dft` mode, UMA-only anchors are omitted. `hybrid` and
  modes preserve both branches. An `unknown` backend fails closed and the CLI
  stops until the project profile or explicit override resolves the branch.
- Preserve explicit calculator/backend, optimizer, force tolerance, maximum
  steps, and convergence metadata. FIRE, ASE, UMA, and FAIRChem are conditional
  facts and must not be introduced as defaults.
- For model details, extract only `records.motif_label` and `records.state`
  from `model_manifest.json`; current artifacts do not store full slab-builder
  arguments.
- For gas-model details, extract one gas metadata example, preferring H2, with
  only `formula`, `cell_lengths`, and `pbc`.
- For energy/free-energy details, include brief internal tool metadata and
  `reference_policy.json`. A later writer must translate tool names into public
  academic language and must not cite internal skill names directly.
- Preserve explicit Gibbs-correction, gas-pressure/standard-state,
  liquid-water activity, CHE/SHE/RHE, pH, potential, and equation fields when
  they are present in the source evidence.
- Do not add descriptor analysis, electronic-structure analysis, or a standalone
  limitations section in this version.

The emitted `backend_policy` is carried into `methods_writer_digest.json` and
later into the written section JSON. Downstream writers and citation selectors
must honor it as a hard branch constraint. This collector does not preselect or
require citation keys; canonical method matching is an LLM evidence decision in
`select-citations` after the Methods sentences exist.

Read [references/evidence_schema.md](references/evidence_schema.md) when
consuming or revising the JSON contract.
