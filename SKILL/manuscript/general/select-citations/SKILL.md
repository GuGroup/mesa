---
name: select-citations
description: Select manuscript sentence-level citations from extract-citation-sources outputs. Use after section writing and extract-citation-sources when Codex must create cited_section_text.json, citation_decisions.json, and a review summary without editing DOCX files or searching outside the bounded citation source library.
---

For MESA end-to-end use, read `SKILL/manuscript/workflow.md` before applying this skill.

# Citation Selector

## Scope

Use this skill after manuscript section text exists and
`extract-citation-sources` has produced `citation_sources.json`.

The selector reads a manuscript section JSON, retrieves a small candidate set
from the bounded citation source library for each sentence, and writes
reviewable citation annotations. It does not edit DOCX files, call Zotero,
download papers, perform web search, or alter the original manuscript sentence
text.

`cited_section_text.json` includes only compact metadata for sources actually
used in citations, not the full citation library.

Default output:

```text
project/<project>/strategy_execution/<strategy_id>_methods/citations/
  cited_section_text.json
  citation_decisions.json
  citation_selection_summary.md
  llm_prompt.json        # only when LLM mode is used
  llm_response.json      # only when LLM mode is used
```

## Workflow

Run:

```bash
python SKILL/manuscript/general/select-citations/scripts/select_citations.py \
  --section-json project/<project>/strategy_execution/<strategy_id>_methods/text/methods_section_text.json \
  --citation-sources project/<project>/references/citation_sources.json
```

Normal use uses the OpenAI API when `OPENAI_API_KEY` is available from the
environment or `DEPENDENCY/.env`. Use `--no-llm` only for retrieval-only
fallback. That fallback deliberately leaves canonical Methods citations
unselected and marks them for human review rather than guessing from keywords.

Useful options:

```bash
--outdir project/.../citations
--max-candidates 8
--model gpt-5.5
--save-prompt project/.../llm_prompt.json
--save-response project/.../llm_response.json
--backend-policy project/.../methods_writer_digest.json  # optional; section metadata is the default
```

## Selection Rules

- Never cite sources outside `citation_sources.json`.
- For a Methods sentence, supply every backend-compatible
  `canonical_method_reference` to the LLM with its full title, authors, year,
  DOI, URL, `method_tags`, `backend_family`, and `citation_guidance`.
- Let the LLM decide whether the sentence reports actual use of PBE, VASP, PAW,
  Monkhorst-Pack, ASE, UMA, pMuTT, CHE, or another registered method. Do not
  force a citation from lexical overlap. Generic `cutoff` or `plane wave` text
  alone does not establish use of VASP.
- Honor `backend_policy` from the section JSON (or `--backend-policy`). In
  UMA-only mode, remove DFT canonical references from the candidate index and
  never select them. If stale DFT terms appear in a sentence, select no
  citation and mark the sentence for human correction.
- Retrieve and score only ordinary project/second-neighbor literature to bound
  its candidate set. Do not score canonical method references, and do not expose
  internal retrieval scores to the LLM.
- Bound every LLM decision to the citation keys supplied in its sentence packet.
- Preserve the original paragraph `text`; write citations into
  `citation_annotations` and `text_with_citation_placeholders`.
- Include `citation_sources_used` so downstream renderers can resolve selected
  citation keys without loading the full source library.
- Cite paragraph sentences only. Leave equation blocks unchanged.
- Prefer primary project papers for literature/background statements about the
  catalyst system.
- Use second-neighbor sources mainly for standard methods, software,
  exchange-correlation functionals, PAW, k-point sampling, computational
  hydrogen electrode references, and other public formalisms.
- Do not cite second-neighbor sources for new results generated in the current
  project.
- Do not cite sentences whose support is the manuscript's own figure, such as
  sentences centered on `Fig. 1`, `Fig. 3`, or `Fig. S1`, unless the sentence
  makes an explicit literature or experimental comparison.
- Leave project-specific calculation counts, convergence outcomes, and negative
  scope statements uncited unless a supplied candidate directly supports the
  method convention being described.
- If no candidate clearly supports a sentence, return no citation and record a
  warning or low confidence.

Read [references/output_schema.md](references/output_schema.md) when consuming
or revising the JSON contract.
