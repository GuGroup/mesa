---
name: write-methods-sections
description: Ask an LLM to write public academic Methods sections from collect-methods-evidence's minimal methods_writer_digest.json. Use after collect-methods-evidence when Codex must draft exactly the four core computational Methods sections, save methods_section_text.json and .md, and guard against internal workflow ids, file paths, JSON names, skill names, descriptor/electronic-analysis sections, or unsupported claims.
---

For MESA end-to-end use, read `SKILL/manuscript/workflow.md` before applying this skill.

# Methods Section Writer

## Scope

Use this skill after `collect-methods-evidence` has produced
`methods_writer_digest.json`.

It writes manuscript-facing Methods prose with ordered paragraph/equation
content blocks for exactly four sections:

1. `model_construction`
2. `geometry_optimization`
3. `vibrational_free_energy_corrections`
4. `electrochemical_free_energy_formalism`

It does not edit DOCX files, add figures, write Results, or add descriptor,
electronic-structure, or standalone limitations sections.

Before writing, read [references/methods_formalism_guide.md](references/methods_formalism_guide.md)
as a conditional reference. The guide supplies examples for DFT, UMA/ASE,
vibrational/Gibbs corrections, gas pressure, and HER CHE writing; the evidence
digest remains authoritative and unsupported branches must be omitted.

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
python SKILL/manuscript/methods/write-methods-sections/scripts/write_methods_sections.py \
  --digest project/<project>/strategy_execution/<strategy_id>_methods/evidence/methods_writer_digest.json
```

Use `--no-llm` only for deterministic smoke testing. Normal use requires
`OPENAI_API_KEY`, loaded from the environment or `DEPENDENCY/.env`.

## Public Prose Rules

- Write academic Methods style, not planning or strategy language.
- Use only the digest facts.
- Treat `backend_policy` as authoritative. In UMA-only mode, omit DFT/VASP/PBE/
  PAW/plane-wave/k-point/DFT-D3 prose even if stale input fields are present,
  and report any violating generated text as invalid.
- Do not mention internal skill names, JSON, file paths, workflow ids,
  `P00x`/`C00x`, source artifacts, prompts, or project directories.
- Translate internal tool metadata into public language, for example "UMA-based
  vibrational calculations" or "free-energy bookkeeping was applied", not skill
  names.
- Do not add descriptor analysis, electronic-structure analysis, or standalone
  limitations sections.
- If a detail is missing, write generally rather than inventing a value.
- Do not write FIRE, ASE, UMA, FAIRChem, pMuTT, CHE, SHE, or RHE unless the
  corresponding evidence field identifies its use.
- Use the CHE example only for HER or hydrogen-adsorption text supported by the
  evidence. Do not extend it to OH-, water autoionization, or another reaction.
- Resolve all example tokens before output. No `[VALUE]` or `{{VALUE}}`
  placeholder may remain in `methods_section_text.json`.
- Round non-integer values in public text and equations to at most two decimal
  places (for example, `1.184` becomes `1.18`); leave integers as integers.
  Preserve full precision in the evidence digest.
- Put equations in ordered `content_blocks` where they belong in the narrative.
  Use equation blocks for mathematical equations, chemical equations,
  electrochemical identities, and reaction-state sequences. Do not duplicate the
  same expression inside paragraph text.

Read [references/output_schema.md](references/output_schema.md) when consuming
or revising the output contract.
