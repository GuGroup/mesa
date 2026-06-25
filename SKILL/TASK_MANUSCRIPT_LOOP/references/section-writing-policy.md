# Section Writing Policy

Section writing expands locked logic into prose. It is not a discovery stage.

## Preconditions

Before writing any prose chunk:

- `paper/logic/claim-matrix.yaml` has no unsupported main claim for the chunk.
- `paper/logic/figure-map.yaml` has no blocked required figure for the chunk.
- `paper/state/reviewer-issues.yaml` has no open `BLOCKER` or unresolved major
  issue for the chunk.
- `paper/manuscript/section-contracts.yaml` marks the section
  `ready-to-draft`.
- Required source files exist under `paper/inputs/`, `paper/logic/`, or
  `paper/figures/`.

## Manuscript Order

Final manuscript/export order is:

1. Abstract
2. Introduction
3. Results and Discussion, organized by topic
4. Computational Methods or Methods, compact in the main text when appropriate
5. Conclusion
6. Supplementary Information

Drafting may still begin from Results/Discussion chunks because they are closest
to the evidence contract. Do not confuse that working order with final document
order. Before drafting a section, load `references/skill-routing.md` and use
`SKILL/nature-writing` with target journal set to `nature` for Nature-family
argument structure. After accepted reviewer issues are resolved and the section
content is claim-locked, use `SKILL/nature-polishing` for concision, flow,
terminology, and journal-style refinement.

## Chunk Policy

Write in flow-sized chunks, such as one Results subsection or one Methods block.
Do not send the whole manuscript as context unless the named issue requires it.
When revising, patch only the chunk named by an accepted issue and read adjacent
chunks only for transition context.

## Word-Ready Markdown

Write canonical section text so the Word/DOCX exporter can convert it cleanly:

- Do not start a section file with a duplicate top-level self-heading such as
  `# Results`; section headings are inserted from `section-contracts.yaml`.
- Use real subsection headings only when the contract or outline calls for
  them.
- Results and Discussion topic blocks must use a bold lead paragraph followed
  by a blank line, not a pipe: `**Bold topic title**`, blank line, then the
  body paragraph. Apply the same pattern to figure-led discussion blocks and
  table-led discussion blocks.
- Supplementary Information blocks may keep the compact inline form:
  `**Section name** | sentence continues here.`
- Use Pandoc subscript and superscript syntax for inline chemistry:
  `H~2~O`, `CO~2~`, `NO~3~^-^`, `NH~4~^+^`, `e^-^`, `cm^-2^`, and `10^-3^`.
- Use `$...$` math spans for variables, Greek symbols, and formal expressions:
  `$E_{\\mathrm{ads}}$`, `$\\Delta G$`, `$\\Delta\\Delta G$`, `$\\delta$`.
  Do not leave raw `\delta`, `\Delta`, or `_ads` outside math spans.
  Never wrap `$...$` math in backticks; code spans are exported verbatim and
  will break Word equation conversion.
- In manuscript body text, use math spans for italic variables and Markdown
  italics for accepted Latin terms such as `*ab initio*`, `*in situ*`,
  `*ex situ*`, and `*operando*`.
  Do not italicize chemical formulas, surface labels, caption labels, or
  stylistic emphasis.
- Figure and table captions must be real caption paragraphs, not bullet
  inventories: `**Figure 1 |** Caption sentence...` and
  `**Table 1 |** Caption sentence...`. The label and pipe are bold only, never
  italic. The caption paragraph must not be styled as all-italic. Caption body
  text may still italicize accepted Latin terms or variables where scientifically
  appropriate. The DOCX exporter assigns these paragraphs 11 pt, single-spaced
  caption styling.
- Every new symbol or abbreviation must already exist in
  `paper/logic/notation.yaml`.

For revision work, load `references/revision-audit-trail.md` first. The
revision editor must update `author-response.yaml`, `change-plan.yaml`,
`changed-files.md`, `verification.md`, and one or more unified diffs under
`patches/` before a round is considered closed.

## Non-Invention Rules

Do not introduce new claims, numbers, calculations, citations, methods, or
figures in prose. If prose needs a new claim, return to the claim matrix and
gate review.

Imported writing/polishing skills are style and structure guides only. They may
not override the claim matrix, figure map, section contract, reviewer issue
state, or the v1 exclusion on literature search and citation work.
