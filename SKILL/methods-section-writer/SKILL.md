---
name: methods-section-writer
description: Ask an LLM to write public academic Methods sections from methods-evidence-collector's minimal methods_writer_digest.json. Use after methods-evidence-collector when Codex must draft exactly the four core computational Methods sections, save methods_section_text.json and .md, and guard against internal workflow ids, file paths, JSON names, skill names, descriptor/electronic-analysis sections, or unsupported claims.
---

# Methods Section Writer

## Scope

Use this skill after `methods-evidence-collector` has produced
`methods_writer_digest.json`.

It writes manuscript-facing Methods prose with ordered paragraph/equation
content blocks for exactly four sections:

1. `model_construction`
2. `geometry_optimization`
3. `vibrational_free_energy_corrections`
4. `electrochemical_free_energy_formalism`

It does not edit DOCX files, add figures, write Results, or add descriptor,
electronic-structure, or standalone limitations sections.

Default output:

```text
project/<project>/strategy_execution/<strategy_id>_methods/text/
  methods_section_text.json
  methods_section_text.md
  llm_prompt.txt
  llm_response.json
```

## Workflow

Run:

```bash
python SKILL/methods-section-writer/scripts/write_methods_sections.py \
  --digest project/<project>/strategy_execution/<strategy_id>_methods/evidence/methods_writer_digest.json
```

Use `--no-llm` only for deterministic smoke testing. Normal use requires
`OPENAI_API_KEY`, loaded from the environment or `DEPENDENCY/.env`.

## Public Prose Rules

- Write academic Methods style, not planning or strategy language.
- Use only the digest facts.
- Do not mention internal skill names, JSON, file paths, workflow ids,
  `P00x`/`C00x`, source artifacts, prompts, or project directories.
- Translate internal tool metadata into public language, for example "UMA-based
  vibrational calculations" or "free-energy bookkeeping was applied", not skill
  names.
- Do not add descriptor analysis, electronic-structure analysis, or standalone
  limitations sections.
- If a detail is missing, write generally rather than inventing a value.
- Put equations in ordered `content_blocks` where they belong in the narrative.
  Use equation blocks for mathematical equations, chemical equations,
  electrochemical identities, and reaction-state sequences. Do not duplicate the
  same expression inside paragraph text.

Read [references/output_schema.md](references/output_schema.md) when consuming
or revising the output contract.
