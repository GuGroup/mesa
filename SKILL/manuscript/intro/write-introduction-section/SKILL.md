---
name: write-introduction-section
description: Ask an LLM to write a citation-free, literature-led Introduction section from introduction-evidence-collector's introduction_writer_digest.json plus optional DOCX context. Use after introduction-evidence-collector when Codex must draft introduction_section_text.json and .md for computational catalysis manuscripts while avoiding internal workflow language, figure/result claims, citation placeholders, and strategy-style prose.
---

# Introduction Section Writer

## Scope

Use this skill after `introduction-evidence-collector` has produced
`introduction_writer_digest.json`.

It optionally preprocesses a manuscript DOCX for light continuity context, then
asks an LLM to write a manuscript-ready Introduction grounded in the evidence
digest.

It does not select citations, insert citation placeholders, edit DOCX files,
write Results, or describe figures.

Default output:

```text
project/<project>/strategy_execution/<strategy_id>_introduction/text/
  manuscript_context.json
  manuscript_context.md
  introduction_section_text.json
  introduction_section_text.md
  llm_prompt.txt
  llm_response.json
```

## Workflow

Run:

```bash
python SKILL/introduction-section-writer/scripts/write_introduction_section.py \
  --digest project/<project>/strategy_execution/<strategy_id>_introduction/evidence/introduction_writer_digest.json \
  --manuscript-docx project/<project>/manuscript/S1/S1_manuscript_with_global_citations.docx
```

Use `--no-llm` only for deterministic smoke testing. Normal use requires
`OPENAI_API_KEY`, loaded from the environment or `DEPENDENCY/.env`.

## Writing Rules

- Write academic Introduction style, not strategy, procedure, or review-note
  prose.
- Build a literature-led narrative following the `narrative_order` and
  `writing_profile` fields in the digest. Do not impose a reaction, material,
  dopant, electrolyte, or mechanism absent from the digest.
- Use selected-strategy content only for the final present-work framing.
- Do not mention internal workflow language, including strategy, procedure,
  workflow, source, digest, JSON, artifact, manifest, skill, prompt, file paths,
  project paths, `P00x`, or `C00x`.
- Do not mention figures, tables, Results values, calculation counts, or
  execution outcomes.
- Do not add citations, citation placeholders, bracketed reference numbers, or
  author-year parentheticals. Citation selection is a later layer.
- Do not use overclaiming language such as "prove" or "fully explain".
- Output one section with 4-6 paragraph content blocks. Set `title` and
  `small_title` to empty strings so a DOCX inserter can preserve the existing
  Introduction heading without adding a duplicate local title.

Read [references/output_schema.md](references/output_schema.md) when consuming
or revising the output contract.
