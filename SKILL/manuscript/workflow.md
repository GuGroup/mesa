# Manuscript Domain Workflow

Use this manual after computational/result artifacts exist. Manuscript skills
assemble, write, cite, insert, and polish only from accepted evidence and
project-local source libraries.

Manuscript skills do not run VASP, UMA, DFT, qsub, new literature search, or
new calculations.

# Skills By Stage

- `manuscript/figure/`: `map-strategy-figures`,
  `realize-strategy-figures`, `caption-strategy-figures`,
  `insert-strategy-figures-into-docx`.
- `manuscript/methods/`: `collect-methods-evidence`,
  `classify-methods-evidence`, `write-methods-sections`.
- `manuscript/results/`: `collect-results-evidence`,
  `write-results-section`, `add-results-literature-comparisons`.
- `manuscript/intro/`: `collect-introduction-evidence`,
  `write-introduction-section`.
- `manuscript/general/`: `extract-citation-sources`,
  `select-citations`, `insert-citations`, `insert-section-into-docx`.
- `manuscript/akct/`: `write-title-abstract-keywords-conclusion`.
- `manuscript/si/`: `write-supporting-information`.
- `manuscript/polish/`: `move-methods-details-to-si`,
  `resolve-manuscript-placeholders`, `polish-manuscript-references`,
  `polish-si-references`, `polish-manuscript-notation`,
  `number-manuscript-equations`.
- `manuscript/review/`: `nature-reviewer`.

# Inputs

Required inputs for a full manuscript run:

- selected strategy:
  `project/<project_name>/strategy_execution/strategy_selection/selected_strategy.json`;
- accepted calculation and analysis artifacts under the completed strategy
  execution folders;
- recipe coverage and missing-evidence records;
- realized or realizable figure inputs;
- citation source library from local project papers;
- manuscript skeleton DOCX, usually under `RESOURCE/`;
- optional project writing profile:
  `project/<project_name>/manuscript_writing_profile.json`.

The writing profile stores project-specific narrative roles and vocabulary.
Reusable writing skills must remain general. If a study needs HER, MoS2, Ni,
ORR, CO2RR, NRR, alloy, oxide, vacancy, electrolyte, or any other domain
language, that language belongs in project evidence or the writing profile, not
inside reusable skill source code.

# Result Artifact Boundary

The manuscript or bounded result artifact must distinguish:

- what the completed work establishes;
- which original strategy procedures were satisfied;
- which procedures remain unresolved;
- whether unresolved items are blocking or nonblocking for the original target
  task;
- whether the result is a full strategy result or only a bounded/proxy result.

# 1. Figure Plan From Strategy Procedures

Use `map-strategy-figures` after strategy selection and after the
calculation/result evidence exists.

The mapper input is the selected strategy's computational block, especially:

- `models`;
- `methods`;
- `dft_details.adsorption_sites`;
- `procedures`.

The mapper asks for conventional computational-chemistry figure intents directly
supported by the planned workflow and retains every normalized intent. It
associates intents with explicit recipe roles and artifacts but does not analyze
scientific results or use execution acceptance states to refuse a figure. A
figure is blocked only when a matched calculation raises authoritative
`missing_evidence_summary.json` or nonempty
`missing_evidence_records.json`. Unmatched intents remain recorded with a
nonblocking note. The mapper must not infer unsupported experiments,
unsupported descriptors, or project-specific figure concepts absent from the
strategy procedures.

Save mapping under:

```text
project/<project_name>/strategy_execution/<strategy_id>_figure/mapping/
  figure_info.json
```

# 2. Figure Realization

Use `realize-strategy-figures` after figure mapping.

The realizer reads `figure_info.json`, checks available calculation outputs,
and creates actual figure files when source data are sufficient. It may call
specialized plotter/grid skills or create simple script-backed plots. It must
not invent missing data. Blocked figures must be recorded with reasons.

Figure exports are PNG-only for the current DOCX workflow.

Save outputs under:

```text
project/<project_name>/strategy_execution/<strategy_id>_figure/
  exported/
  realization/figure_realization.json
```

# 3. Figure Captions

Use `caption-strategy-figures` after figure realization.

The captioner writes academic figure titles and captions from realized figures,
strategy evidence, and calculation evidence. Captions must not mention internal
procedure IDs, workflow IDs, skill names, JSON files, or strategy-style prose.

Save outputs under:

```text
project/<project_name>/strategy_execution/<strategy_id>_figure/caption/
  caption_info.json
```

# 4. Insert Figures Into Skeleton DOCX

Use `insert-strategy-figures-into-docx`.

Rules:

- main figures are numbered `Fig. 1`, `Fig. 2`, ...;
- Supporting Information figures are numbered `Fig. S1`, `Fig. S2`, ...;
- figure number, separator, and figure title must be bold;
- preserve DOCX integrity and verify that the file opens without recovery;
- check both horizontal and vertical figure fit.

Save manuscript DOCX outputs under:

```text
project/<project_name>/manuscript/<strategy_id>/
```

# 5. Methods Evidence Collection

Use `collect-methods-evidence` before Methods evidence classification.

The collector should keep evidence minimal and general:

- model construction evidence from selected strategy and model manifests;
- gas model metadata such as formula, cell lengths, and PBC when available;
- relaxation/calculation metadata summarized by category, not full raw logs;
- energy/free-energy reference policy and equations when available.

The collector must remain section-neutral. It preserves compact evidence and
does not choose section names, grouping, or order.

Do not include optional analysis sections such as DOS, Bader charge, charge
density difference, kinetics, or local geometry analysis unless separate
project evidence and writer support explicitly exist for those sections.

Save:

```text
project/<project_name>/strategy_execution/<strategy_id>_methods/evidence/
  methods_minimal_evidence.json
  methods_planner_digest.json
```

# 5A. Hybrid Methods Evidence Classification

Use `classify-methods-evidence` on `methods_planner_digest.json`.

The classifier assigns supported facts deterministically to DFT settings, model
construction, vibrational/free-energy corrections, and chemical-potential
domains. Only leftover evidence is sent to an LLM, which may create additional
method sections or leave evidence explicitly unassigned. Validate closed,
exactly-once evidence-ID coverage.

Save:

```text
project/<project_name>/strategy_execution/<strategy_id>_methods/classification/
  methods_evidence_classification.json
  methods_section_plan.json
  methods_section_plan.md
```

# 6. Methods Writing

Use `write-methods-sections`.

The writer reads `methods_section_plan.json`, preserves its exact section set
and order, and writes both deterministic core sections and LLM-planned sections.
DFT settings and model construction follow evidence-driven rhetorical
blueprints; all other sections are organized from their own assigned evidence.
Every assigned evidence ID must be used or explicitly omitted, while unassigned
evidence stays out of manuscript prose.

Public Methods prose must translate explicit tool roles into academic language
and must not mention skill names, recipe IDs, file paths, JSON artifacts,
project folders, evidence IDs, section decisions, or planning language.

Equations belong in equation blocks, not hidden inside paragraphs. The writer
may include chemical equations, thermochemical equations, or reference
relations only when supplied by the evidence digest.

Save:

```text
project/<project_name>/strategy_execution/<strategy_id>_methods/text/
  methods_section_text.json
  methods_section_text.md
```

# 7. Methods Insertion

Use `insert-section-into-docx` to insert `methods_section_text.json` into the
manuscript skeleton or figure-containing DOCX.

Use OMML/Pandoc equation conversion mode when equation blocks are present. Keep
equation labels out of the visible DOCX body unless explicitly requested.

# 8. Citation Source Extraction

Use `extract-citation-sources` before citation selection.

The citation library is bounded:

- first-neighbor sources are local project PDFs and extracted papers;
- second-neighbor sources are references cited by those PDFs;
- do not add web-search references during manuscript citation insertion unless
  the user explicitly requests it.

Save:

```text
project/<project_name>/references/
  citation_sources.json
  library.bib
```

# 9. Section Citation Selection

Use `select-citations` after a section writer creates section JSON.

Run it separately for Methods, Results, Introduction, and any other citation
requiring section. The selector must preserve original paragraph text and write
citation decisions into structured metadata and citation placeholders.

Rules:

- select only citation keys present in `citation_sources.json`;
- return no citation when support is weak;
- do not cite a sentence whose support is only the manuscript's own figure;
- keep decisions reviewable with confidence and human-check flags.
- honor validated comparison-layer citation requests for their exact sentences;
  reject unknown sources or unmatched requested sentences.

Save each section's citation layer under that section workspace, for example:

```text
project/<project_name>/strategy_execution/<strategy_id>_methods/citations/
  cited_section_text.json
  citation_decisions.json
```

# 10. Citation Insertion Into DOCX

Use `insert-citations`.

For section-local tests, the inserter may create a cited DOCX from one
`cited_section_text.json`. For the manuscript, use the global/skeleton-
preserving path:

- merge section citation layers in manuscript order;
- build `used_references.bib` only from selected citation sources;
- preserve the existing DOCX skeleton and figure structure;
- replace only matched manuscript paragraphs and the references placeholder.

Do not use citation insertion as a citation-selection step.

# 11. Results Evidence Collection

Use `collect-results-evidence` after figures, captions, and result artifacts
exist.

The collector builds a compact Results evidence digest from:

- selected-strategy context;
- figure mapping, realization, and captions;
- result artifact or bounded result artifact;
- computed tables such as descriptor summaries, state profiles, rankings, and
  benchmark comparisons;
- model, relaxation, and vibration summaries;
- blocked or unavailable evidence;
- optional mapper `text_only_evidence` records supplied by compatible legacy or
  project-specific mappings.

It must keep facts separate from prose. It must not hide blocked evidence or
turn unavailable analyses into claims.

Save:

```text
project/<project_name>/strategy_execution/<strategy_id>_results/evidence/
  results_evidence.json
  results_writer_digest.json
```

# 12. Results Writing And Insertion

Use `write-results-section`.

The writer uses `results_writer_digest.json` and optional DOCX context to write
figure-centered Results and Discussion subsections. It must:

- mention every main-text figure supplied by the digest at least once;
- write every text-only evidence record and report exact ID coverage in metadata;
- use only figures and values present in the digest;
- avoid internal workflow language;
- avoid unsupported electronic, kinetic, solvation, or experimental claims;
- avoid standalone limitation or future-work paragraphs.

Text-only evidence may be discussed with its covering superset figure, but the
writer must not imply that the deleted underset visualization exists.

After the internal Results draft is stable, use
`add-results-literature-comparisons` with the original Results digest and bounded
`citation_sources.json`. The skill inserts only validated prior-study comparison
sentences and emits exact citation requests. Then run `select-citations` on
`results_section_with_literature.json`; requested comparison sources are
validated and applied before normal citation retrieval for other sentences.

Insert Results with `insert-section-into-docx`. Use `--distribute-figures` when
the DOCX already contains figure blocks and Results paragraphs mention those
figure numbers.

Run citation selection and citation insertion for Results after the section is
written.

# 13. Introduction Evidence, Writing, And Insertion

Use `collect-introduction-evidence`.

The collector is literature-led. It uses:

- `citation_sources.json`;
- local paper extraction responses;
- optional experimental extraction notes;
- optional selected strategy only for final present-work framing;
- optional `manuscript_writing_profile.json` for project-specific narrative
  roles and order.

Use `write-introduction-section` after the evidence collector.

The Introduction writer must:

- follow the digest `narrative_order` and writing profile;
- not impose a reaction, material, dopant, electrolyte, or mechanism absent from
  the evidence;
- not cite inline;
- not mention figures, tables, Results values, calculation counts, or execution
  outcomes;
- use selected-strategy content only for the final present-work objective.

Insert Introduction with `insert-section-into-docx`. Then run
`select-citations` and `insert-citations` for Introduction.

# 14. Title, Abstract, Keywords, And Conclusion

Use `write-title-abstract-keywords-conclusion` after Introduction, Results,
Methods, figures, and citations are assembled enough to provide manuscript
context.

The writer reads the DOCX and creates:

- title;
- abstract;
- keywords;
- conclusion.

It must not add new claims, citations, figure references, unsupported analyses,
or workflow language. Title insertion should use 14 pt bold formatting when the
section JSON requests it.

Insert title, abstract, keywords, and conclusion with
`insert-section-into-docx`.

If the skeleton contains `{{SI_TITLE}}`, insert the same title there unless the
user requests a distinct SI title.

# 15. Supporting Information Text

Use `write-supporting-information` after main text and SI figure placeholders
exist.

The SI writer creates minimal inserter-ready JSON for:

- SI large-content title;
- SI large-content text;
- SI small-content title;
- SI small-content text;
- DFT/calculation details text.

Rules:

- write supplementary figure text only for existing SI figures;
- write compact no-content text if no SI figure exists;
- move detected detailed calculation or geometry-optimization details into the
  DFT calculation details placeholder;
- do not invent new parameters, calculations, or claims.

Use `move-methods-details-to-si` after SI insertion when detailed Methods text
should be compressed in the main manuscript and preserved in SI. The mover is
configurable and should replace only the configured detail block with a concise
bridge paragraph.

# 16. Final Manuscript Polishing

Run final DOCX polishers as separate, general, config-driven steps.

Recommended order:

1. `resolve-manuscript-placeholders`
   Remove or replace unresolved placeholders according to a project config.
   Example config location:
   `project/<project_name>/manuscript/<strategy_id>/final_polish_configs/placeholder_config.json`.

2. `polish-manuscript-references`
   Normalize main manuscript reference paragraphs from a project reference
   config. Do not renumber in-text citations unless the citation layer
   explicitly requires it.

3. `polish-si-references`
   Create independent SI references when SI-local citation markers are used.
   Use configured SI citation mappings and SI reference entries.

4. `polish-manuscript-notation`
   Apply configured scientific notation formatting such as subscripts and
   superscripts. Preserve run-level styling so bold small titles do not make
   whole paragraphs bold.

5. `number-manuscript-equations`
   Automatically find displayed Word equations and number them sequentially.
   Consecutive displayed equations are one equation group. Use the borderless
   three-column table layout by default: empty side cell, centered equation
   group, right-aligned equation number.

Each polisher must write a JSON report and preserve DOCX integrity. Validate
with ZIP/XML checks and, when possible, headless LibreOffice conversion.

# 17. Manuscript Outputs

Final manuscript artifacts should remain under:

```text
project/<project_name>/manuscript/<strategy_id>/
```

Recommended files:

- a latest assembled DOCX before final polishing;
- a final polished DOCX;
- all insertion, citation, SI, reference, notation, equation-numbering, and
  placeholder reports;
- project-specific polish configs under `final_polish_configs/`.

A final manuscript is an assembled evidence-backed artifact. It is not
scientific approval by itself.

# 18. Manuscript-To-Strategy Feedback

Use `update-strategies-from-manuscript` after the manuscript or bounded result
artifact is complete.

Feed final claims, caveats, blockers, missing procedure coverage, unsupported
claims, and excluded claims back into the strategy plan. This step is mandatory
before selecting or calculating the next strategy.
