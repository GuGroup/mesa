---
name: write-results-section
description: Ask an LLM to write manuscript-ready Results and Discussion prose from results-evidence-collector's results_writer_digest.json plus a compact DOCX-derived manuscript context. Use after results-evidence-collector when Codex must draft results_section_text.json and .md for catalyst computational manuscripts while guarding against internal workflow language, unsupported electronic descriptors, raw file paths, procedure ids, and overclaimed experimental prediction.
---

# Results Section Writer

## Scope

Use this skill after `results-evidence-collector` has produced
`results_writer_digest.json`.

It preprocesses an optional manuscript DOCX into compact context, then asks an
LLM to write figure-centered Results and Discussion subsections grounded only in
the evidence digest.

It does not edit DOCX files, select citations, generate figures, or revise
Methods. It does not convert blocked PDOS/Bader/charge evidence into manuscript
claims.

Default output:

```text
project/<project>/strategy_execution/<strategy_id>_results/text/
  manuscript_context.json
  manuscript_context.md
  results_section_text.json
  results_section_text.md
  llm_prompt.txt
  llm_response.json
```

## Workflow

Run:

```bash
python SKILL/results-section-writer/scripts/write_results_section.py \
  --digest project/<project>/strategy_execution/<strategy_id>_results/evidence/results_writer_digest.json \
  --manuscript-docx project/<project>/manuscript/S1/S1_manuscript_with_citations.docx
```

Use `--no-llm` only for deterministic smoke testing. Normal use requires
`OPENAI_API_KEY`, loaded from the environment or `DEPENDENCY/.env`.

## Writing Rules

- Write academic Results and Discussion style, not strategy or procedure prose.
- Organize around the figure backbone and key findings.
- Use figure references such as `Fig. 1`, `Fig. 3`, and `Fig. S1` only when the
  digest provides those figure numbers.
- Mention every main-text figure provided by the digest at least once so the
  DOCX inserter can place each existing figure block near the relevant paragraph.
- Do not mention internal workflow language, including strategy, procedure,
  workflow, source, digest, JSON, artifact, manifest, skill, prompt, writer,
  mapper, realizer, file paths, project paths, `P00x`, or `C00x`.
- Do not claim PDOS, Bader charge analysis, charge transfer, kinetic barriers,
  active-site density, explicit charged OH- solvation, or double-layer effects
  as completed when the digest marks them unavailable.
- Do not claim quantitative overpotential or Tafel-slope prediction from the
  thermodynamic descriptors. Directional consistency is allowed only if the
  digest provides it.
- Treat unavailable or limited evidence as a silent guardrail for claim
  strength. Do not write standalone limitation, scope, missing-evidence, or
  future-work paragraphs, and do not enumerate analyses that were not performed.
- State thermodynamic descriptor conclusions directly. Do not add
  meta-commentary telling readers that the agreement, result, finding, or trend
  "should be interpreted" or "should be understood" at a particular level.
- Do not add citations. Citation selection is a later layer.
- Divide Results into 2-4 focused local subsections with concise `small_title`
  values. Avoid one generic small title spanning the whole Results section.
- Keep the output as plain paragraph blocks. Do not include equations or bullet
  lists in this version.

Read [references/output_schema.md](references/output_schema.md) when consuming
or revising the output contract.
