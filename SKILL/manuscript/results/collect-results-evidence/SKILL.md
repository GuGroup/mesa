---
name: collect-results-evidence
description: Deterministically collect compact, figure-centered evidence for Results and Discussion drafting in computational catalyst manuscript workflows. Use after figures and result artifacts exist, before a Results writer skill, when Codex needs results_evidence.json and results_writer_digest.json from selected_strategy, S*_result_artifact, figure mapping/captions/realization, free-energy tables, model manifest, relaxation, and vibration summaries without writing manuscript prose.
---

For MESA end-to-end use, read `SKILL/manuscript/workflow.md` before applying this skill.

# Results Evidence Collector

## Scope

Use this skill before writing Results and Discussion text. It creates a compact
evidence packet organized around figures and directly supported result facts.

It does not write manuscript prose, polish text, select citations, edit DOCX
files, or infer unsupported mechanisms. It preserves limitations and blocked
evidence so the writer can avoid overclaiming.

Default output:

```text
project/<project>/strategy_execution/<strategy_id>_results/evidence/
  results_evidence.json
  results_writer_digest.json
  results_evidence_summary.md
```

## Workflow

Run:

```bash
python SKILL/manuscript/results/collect-results-evidence/scripts/collect_results_evidence.py \
  --project project/<project> \
  --strategy-id <strategy_id>
```

Defaults:

```text
strategy:        project/<project>/strategy_execution/strategy_selection/selected_strategy.json
result artifact: project/<project>/strategy_execution/<strategy_id>_result_artifact/<strategy_id>_bounded_result_artifact.json
figure root:     project/<project>/strategy_execution/<strategy_id>_figure
execution root:  project/<project>/strategy_execution/<strategy_id>_execution
outdir:          project/<project>/strategy_execution/<strategy_id>_results/evidence
```

Override paths when needed:

```bash
--strategy path/to/selected_strategy.json
--result-artifact path/to/S1_bounded_result_artifact.json
--figure-root path/to/S1_figure
--execution-root path/to/S1_execution
--outdir path/to/evidence
```

## Extraction Rules

- Use the selected strategy only for scientific question, hypothesis, and claim
  context. Do not expose procedure ids as manuscript language.
- Use figure mapping, realization, and caption files as the Results backbone.
- Include only realized main/useful figures as main Results figures. Keep
  supplementary figures separate and record blocked figures as unavailable
  evidence.
- Use result artifact and free-energy tables for numerical claims. Do not read
  raw calculation folders recursively.
- Include limitations from result artifacts and unresolved summaries verbatim or
  compactly; do not hide unsupported electronic descriptors.
- Keep output facts and normalized evidence only. Leave prose construction to a
  Results writer.

Read [references/evidence_schema.md](references/evidence_schema.md) when
consuming or revising the JSON contract.
