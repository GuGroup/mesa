---
name: write-title-abstract-keywords-conclusion
description: Ask an LLM to write manuscript title, abstract, keywords, and conclusion from an already assembled manuscript DOCX. Use when Codex must generate AKC-title text for a computational catalysis manuscript after Introduction, Results and Discussion, Methods, figures, and citations are already drafted, while avoiding citations, figure references, workflow language, unsupported analyses, and new claims.
---

For MESA end-to-end use, read `SKILL/manuscript/workflow.md` before applying this skill.

# Title, Abstract, Keywords, Conclusion Writer

## Scope

Use this skill after the manuscript body has been assembled enough to contain
Introduction, Results and Discussion, Methods, and figure captions.

This skill extracts compact context from the DOCX, asks an LLM to write:

- title
- abstract
- keywords
- conclusion

It does not edit DOCX files, select citations, insert citations, generate
figures, or revise the manuscript body.

Default output:

```text
project/<project>/strategy_execution/<strategy_id>_akctitle/text/
  manuscript_context.json
  manuscript_context.md
  llm_prompt.txt
  llm_response.json
  title_abstract_keywords_conclusion_text.json
  title_section_text.json
  abstract_section_text.json
  keywords_section_text.json
  conclusion_section_text.json
  title_abstract_keywords_conclusion_text.md
```

## Workflow

Run:

```bash
python SKILL/manuscript/akct/write-title-abstract-keywords-conclusion/scripts/write_abstract_keywords_conclusion.py \
  --manuscript-docx project/<project>/manuscript/<strategy_id>/<manuscript>.docx \
  --strategy-id <strategy_id>
```

Use `--no-llm` only for smoke testing. Normal use requires
`OPENAI_API_KEY`, loaded from the environment or `DEPENDENCY/.env`.

## Writing Rules

- Write a concise manuscript title that identifies the central reaction or
  property, material/catalyst family, and computational focus when those details
  are present in the manuscript context.
- Write academic manuscript prose, not strategy or procedure prose.
- Use only the DOCX-derived manuscript context as factual support.
- Do not add citations, citation placeholders, bracketed reference numbers, or
  author-year parentheticals.
- Do not mention figures in the abstract or conclusion unless the user
  explicitly asks for figure-referenced text.
- Do not mention internal workflow language, including strategy, procedure,
  workflow, source, digest, JSON, artifact, manifest, skill, prompt, writer,
  inserter, file paths, project paths, `P00x`, or `C00x`.
- Do not introduce unsupported analyses such as projected density of states,
  Bader charge analysis, charge transfer, kinetic barriers, active-site density,
  conductivity, explicit charged hydroxide solvation, or double-layer effects
  unless the manuscript context states they were performed.
- Do not write standalone limitation, missing-evidence, or future-work
  paragraphs.
- Round non-integer values in public text to at most two decimal places (for
  example, `1.184` becomes `1.18`); leave integers as integers. Preserve full
  precision in the DOCX-derived context.
- Keep the title as one line, without a trailing period.
- Keep the abstract as one paragraph.
- Keep keywords as 5-8 short phrases.
- Keep the conclusion as 2-3 paragraphs.

Read [references/output_schema.md](references/output_schema.md) when consuming
or revising the output contract.
