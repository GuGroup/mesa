# Results Evidence Schema

The collector writes two JSON files.

## `results_evidence.json`

Full audit-oriented evidence packet:

```json
{
  "schema_version": 1,
  "collector": "results-evidence-collector",
  "strategy_id": "S1",
  "input_paths": {
    "strategy": "project/.../selected_strategy.json",
    "result_artifact": "project/.../S1_bounded_result_artifact.json",
    "figure_mapping": "project/.../figure_info.json",
    "figure_captions": "project/.../caption_info.json",
    "figure_realization": "project/.../figure_realization.json",
    "descriptor_summary": "project/.../descriptor_summary.json",
    "activity_ranking": "project/.../activity_ranking.json",
    "relative_free_energies": "project/.../pH14_U0_relative_free_energies.json",
    "benchmark_comparison": "project/.../benchmark_constraint_comparison.json",
    "model_manifest": "project/.../model_manifest.json",
    "relaxation_registry": "project/.../final_relaxation_registry.json",
    "vibration_summary": "project/.../uma_vib_batch_summary.json"
  },
  "strategy_context": {},
  "figure_backbone": [],
  "key_findings": [],
  "computed_tables": {},
  "quality_summary": {},
  "limitations": [],
  "blocked_or_unavailable_evidence": []
}
```

## `results_writer_digest.json`

Compact LLM-facing evidence. It intentionally omits large provenance lists and
raw execution records:

```json
{
  "schema_version": 1,
  "collector": "results-evidence-collector",
  "strategy_id": "S1",
  "writing_task": "Draft Results and Discussion from evidence only.",
  "writer_rules": [],
  "strategy_context": {},
  "figure_backbone": [],
  "key_findings": [],
  "quality_summary": {},
  "limitations": [],
  "blocked_or_unavailable_evidence": []
}
```

## Writer Constraints

- Do not mention internal file paths, JSON names, recipe ids, or procedure ids in
  manuscript prose.
- Do not describe blocked PDOS, Bader, charge-transfer, or electronic-structure
  evidence as completed.
- Do not claim quantitative overpotential or Tafel prediction unless a separate
  output explicitly supports it.
- Use figure numbers from `figure_backbone.figure_number`.
