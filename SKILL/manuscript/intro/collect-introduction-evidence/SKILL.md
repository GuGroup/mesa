---
name: collect-introduction-evidence
description: Collect compact, literature-led evidence for a computational catalysis manuscript Introduction from paper extraction responses, citation-source libraries, experimental extraction notes, and light selected-strategy framing. Use before write-introduction-section when Codex must assemble background, gap, rationale, and "here we show" inputs without drafting prose.
---

For MESA end-to-end use, read `SKILL/manuscript/workflow.md` before applying this skill.

# Introduction Evidence Collector

## Scope

Use this skill before writing an Introduction section.

The collector is literature-led. It extracts compact evidence from:

- `project/<project>/references/citation_sources.json`
- `project/<project>/strategy_generation/paper_extraction/**/_response.json`
- optional experimental extraction response text
- optional selected strategy, used only for final present-work framing
- optional `project/<project>/manuscript_writing_profile.json`, used to define
  project-specific Introduction evidence roles and narrative order

It does not write Introduction prose, select final citations, edit DOCX files,
or search outside the bounded project library.

Default output:

```text
project/<project>/strategy_execution/<strategy_id>_introduction/evidence/
  introduction_evidence.json
  introduction_writer_digest.json
  introduction_evidence_summary.md
```

## Workflow

Run:

```bash
python SKILL/manuscript/intro/collect-introduction-evidence/scripts/collect_introduction_evidence.py \
  --project project/<project> \
  --strategy-id S1
```

Optional inputs can be overridden:

```bash
--citation-sources project/<project>/references/citation_sources.json
--selected-strategy project/<project>/strategy_execution/strategy_selection/selected_strategy.json
--paper-extraction-dir project/<project>/strategy_generation/paper_extraction
--experimental-extraction project/<project>/strategy_generation/experimental_extraction/openai_response.json
--writing-profile project/<project>/manuscript_writing_profile.json
--outdir project/<project>/strategy_execution/S1_introduction/evidence
```

## Rules

- Keep strategy content light. Use it only for the final present-work question,
  objective, and scope.
- Prefer extracted papers and citation sources for the core Introduction logic.
- Keep evidence compact and source-keyed; each evidence point must carry
  citation keys when available.
- Do not include procedure IDs, calculation file paths, figure references,
  execution logs, or Results-specific numeric findings.
- Do not convert evidence into manuscript prose. The output is for a later
  writer and citation selector.
- Keep project-specific narrative roles in the writing profile, not in the
  reusable skill code.

Read [references/evidence_schema.md](references/evidence_schema.md) when
consuming or revising the output contract.
