# MANUSCRIPT DOMAIN GUIDE

## OVERVIEW

Evidence-gated manuscript assembly for accepted calculation, analysis, figure,
and local-literature artifacts. Read `workflow.md` before any leaf `SKILL.md`.
This domain writes, cites, inserts, reviews, and polishes; it does not search for
new literature, run calculations, or manufacture missing scientific support.

## WHERE TO LOOK

| Need | Subdomain | Route |
|---|---|---|
| Figure package | `figure/` | map → realize → caption → insert |
| General assembly | `general/` | extract/select/insert citations; insert section JSON |
| Introduction | `intro/` | collect literature-led evidence → write |
| Methods | `methods/` | collect minimal four-section evidence → write |
| Results | `results/` | collect figure-centered evidence → write |
| Front/back matter | `akct/` | title, abstract, keywords, conclusion after body assembly |
| Supporting Information | `si/` | derive minimal SI blocks from assembled manuscript |
| Final cleanup | `polish/` | placeholders → references → SI refs → notation → equations |
| Pre-submission critique | `review/` | bounded Nature-style reviewer assessment |

The normal handoff is evidence artifact → writer digest → section JSON →
citation selection/insertion → DOCX insertion → SI/final polish. Figure work
runs map → realization → caption before manuscript placement. Feed final claims,
caveats, blockers, and missing coverage back to strategy only after assembly.

## CONVENTIONS

- Keep reusable skills chemistry-general. Reaction, material, electrolyte, and
  narrative vocabulary belongs in project evidence or
  `manuscript_writing_profile.json`.
- Treat section JSON as the writer/inserter API: stable `section_id`, ordered
  `content_blocks`, explicit paragraph/equation block types, `missing_details`,
  `validation`, and the correct target placeholder.
- Keep equations in equation blocks. Use Pandoc-backed OMML for Word-native
  output unless plain-text equation mode was explicitly requested.
- Preserve figure contracts across `figure_info.json`, realization manifest,
  caption metadata, exported PNGs, QA notes, numbering, placement, and blockers.
- Citation choice is bounded to `citation_sources.json` and its local first-/
  second-neighbor library. Selection decides support; insertion only renders it.
- Public prose must remove internal provenance: no skill/workflow names,
  strategy or procedure IDs, JSON/file paths, manifests, prompts, or planning
  language. Keep those details in evidence and reports.
- Every DOCX mutation writes a new file plus JSON/Markdown report. Validate ZIP
  parts, `word/document.xml`, namespace integrity, unresolved placeholders, and
  figure/equation fit; use headless LibreOffice conversion when available.
- Scripts are standalone CLIs, not a shared Python package. When changing a
  copied helper or contract (`write_json`, OpenAI response parsing, DOCX ZIP/XML
  handling, schema normalization), inspect sibling implementations and keep
  behavior aligned without introducing cross-runtime imports.

## ANTI-PATTERNS

- Never turn absent, blocked, proxy, or unresolved evidence into a positive
  claim; retain the full-versus-bounded result distinction.
- Never hardcode project chemistry, bibliography entries, placeholder policy,
  notation rules, or equation text into reusable skill source.
- Never add web-search references during ordinary citation insertion, cite weak
  support, or cite a sentence supported only by the manuscript's own figure.
- Never let writer output leak internal execution vocabulary into title,
  abstract, captions, Methods, Results, Introduction, Conclusion, or SI prose.
- Never overwrite an input skeleton/DOCX, silently skip blocked figures, use
  citation insertion to revise citation choices, or declare success from an
  unvalidated Word archive.
