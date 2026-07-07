# General MESA Skill Workflow

TEST VERSION.

Use `project/mos_0629_2` as the active result directory unless the user explicitly names a different project folder.

This workflow is a loop. It is not a linear checklist and it is not valid to move directly from one strategy calculation into the next strategy calculation.

For this test, a process till Strategy Generation is finished. You can check it on strategy_generation/generate_strategies directory. Please start from Per strategy execution loop based on generated_strategies!

```text
strategy generation
-> select one strategy
-> generate explicit calculation recipes from the selected strategy
-> plan execution from those recipes
-> execute only recipe-backed calculations
-> analyze evidence readiness
-> write manuscript/result artifact
-> update strategy plan from manuscript/result
-> stop/finalize, repair, or select the next revised strategy
```

The central rule is: the selected strategy's computational procedures are the contract. They must first be translated into explicit recipes. Do not silently replace a requested calculation with an easier proxy.

# Strategy Generation

Strategy generation should follow this continuous skill flow.

1. Experimental data extraction
  - Use `TASK_EXTRACT_DATA_FROM_PDF`.
  - Experimental extraction provides benchmark constraints, material identity, measured targets, and observed trends to explain computationally.
  - Do not turn experimental data into new experimental actions.

2. Paper search
  - Use `search-papers-with-mcp`.
  - The user must specify the target task and material domain.
  - If papers must be downloaded manually, stop and wait for the user.

3. Paper extraction
  - Use `decompose-chemistry-paper-pdf` for papers under a `strategy` folder.
  - Use `extract-general-insight-pdf` for non-strategy/domain papers.
  - Preserve extracted source metadata and claims because strategy generation must inherit references from these artifacts.

4. Strategy generation
  - Use `generate-strategies`.
  - Generate multiple computational chemistry strategies based on steps 1-3.
  - Generate DFT/computational proof strategies only, not wet-lab plans.
  - Each strategy must preserve the decompose-style structure: `problem`, `axioms`, `hypothesis`, `experiment`, `results`, `conclusion`.
  - In each strategy, `experiment` means computational experiment.
  - Treat `prioritization.recommended_order` as the default execution queue.
  - Save the generated strategy artifact under the project folder.

# Per-Strategy Execution Loop

Repeat this loop for one selected strategy at a time.

## 1. Select One Strategy

Use `select-next-strategy` before any modeling, recipe generation, or calculation.

- Select exactly one strategy from the current authoritative strategy artifact.
- Use `updated_prioritization.recommended_order` from the latest `update-strategies-from-manuscript` artifact when it is the current plan.
- Otherwise use `prioritization.recommended_order` from the original generated strategy artifact.
- Select the first strategy in the current recommended order unless it is completed, retired, blocked, or explicitly superseded.
- Save the selected-strategy artifact under the project folder.
- Record what the selected strategy can prove and what it cannot prove.
- Do not select from memory, title order, local preference, or strategy ID order.
- Do not override the queue without an explicit logged reason.

## 2. Generate Explicit Calculation Recipes

Use `explicit-calculation-recipe` immediately after strategy selection and before any structure building or calculation.

Input is the selected strategy artifact. The skill reads the selected strategy's computational block:

- `selected_strategy.experiment.computational`, or
- `selected_strategy.experimental.computational`, or equivalent direct computational objects supported by the skill.

Recommended command:

```bash
python3 SKILL/explicit-calculation-recipe/scripts/generate_explicit_recipe.py \
  --strategy project/<project_name>/strategy_execution/strategy_selection/selected_strategy.json \
  --out project/<project_name>/strategy_execution/<strategy_id>_explicit_recipe
```

The output must include:

```text
recipe_index.json
recipe_index.md
source_computational_section.json
P001_<procedure_slug>/
  procedure.json
  procedure_map.md
  calculations/
    C001_<calculation_slug>/
      recipe.json
      recipe.md
```

Each `P###` folder preserves a single source procedure. Each `C###` folder is one specific calculation or analysis recipe derived from that procedure.

Rules for this stage:

- The recipe skill is a translator only.
- It must not decide feasibility, engine choice, policy compliance, repair needs, or scientific sufficiency.
- It must not write `blocked`, `unsupported`, `executable`, `feasible`, `requires_repair`, or similar decision fields into recipe files.
- It must not execute calculations.
- It must preserve exact source procedure text and JSON-pointer provenance.

## 3. Plan Execution From Recipes

After recipe generation, inspect `recipe_index.md` and the `P###/C###` `recipe.json` files before executing anything.

For each recipe, identify:

- required prior artifacts;
- required inputs;
- operations;
- method intent;
- output artifacts;
- the narrowest skills or scripts needed to produce those outputs.

This planning step may determine that a recipe requires a prior structure, electronic-structure output, VASP-like artifact, vibration output, free-energy bookkeeping, or another dependency. Record that in an execution plan or coverage note, but do not alter the recipe itself.

If a required calculation cannot be executed under the current project policy or available skills, do not silently downgrade it. Either:

- stop and ask the user;
- run a future preflight/feasibility skill when available;
- update the strategy through the manuscript/update loop after documenting the gap; or
- execute only the user-approved subset and label the result as bounded.

## 4. Execute Recipe-Backed Calculations

Run modeling and calculations only for recipes generated in step 2.

Use the narrowest relevant skill for each calculation type:

- clean slabs: `TASK_BUILD_SLAB_MODELS`;
- gas references: `TASK_BUILD_GAS_PHASE_MODELS`;
- adsorbate placement: `TASK_Absorbdiff` and related adsorbate tools;
- UMA relaxation or trajectory calculations: UMA skills available in the local skill tree;
- vibrations: UMA vibration skills when present;
- result trajectory checks: `TASK_CALCULATION_RESULT_ANALYZER`;
- energy diagrams: `TASK_CONSTRUCT_ENERGY_DIAGRAM` or `energy-diagram-plotter` as appropriate for the data type;
- manuscript figures: plotter/grid/nature-figure skills as appropriate.

For this test project:

- Prepare VASP-compatible input files when useful for interoperability.
- Do not submit VASP jobs unless the project policy changes.
- If local GPU UMA execution is requested, run UMA locally on the GPU node; do not submit UMA through qsub unless explicitly required.

Save calculation artifacts under the recipe calculation that authorized them:

```text
project/<project_name>/strategy_execution/<strategy_id>_explicit_recipe/
  P###_<procedure_slug>/
    calculations/
      C###_<calculation_slug>/
        execution/
          execution_manifest.json
          ...
```

The `execution/` folder is the default home for structures, inputs, outputs,
logs, scripts, metadata, analysis tables, validation reports, figures, and
recipe-specific notes produced while executing that calculation recipe.

Each `execution_manifest.json` must record:

- source recipe path and source procedure ID;
- skill or project-local script used;
- command or controller input used, when applicable;
- input artifacts;
- output artifacts;
- validation status;
- acceptance state: `accepted`, `accepted-with-caveat`, `exploratory`, `failed`, or `excluded`;
- caveats, unsupported pieces, or policy boundaries such as "VASP input only; no VASP execution".

Shared batch artifacts may live in a strategy-level shared run directory only
when one command naturally produces outputs for multiple recipes. In that case,
every corresponding `C###/execution/execution_manifest.json` must link to the
shared artifacts and identify the exact subset used for that recipe. Do not
leave calculation outputs only in a shared folder without recipe-local
provenance.

Do not modify generated `recipe.json` or `recipe.md` files to store execution
status. Execution status belongs in `execution/` artifacts and coverage notes,
not in the translator output.

## 5. Evidence Readiness

Before manuscript intake:

- Use `TASK_CALCULATION_RESULT_ANALYZER` for relaxation/result sanity checks where trajectories or optimization outputs exist.
- Use `TASK_CONSTRUCT_ENERGY_DIAGRAM` only when its data model matches the required chemistry. If charged species, pH, potential, or solvation are outside a skill's scope, do not hide that mismatch.
- Separate accepted, exploratory, failed, excluded, and accepted-with-caveat artifacts.
- Continue only with trusted structures, tables, figures, and result artifacts.

## 6. Manuscript/Result Artifact

Use the Manuscript workflow below after evidence readiness.

Write a bounded manuscript-like result artifact for the completed strategy or completed subset. The artifact must distinguish:

- what the completed work establishes;
- which original strategy procedures were satisfied;
- which procedures remain unresolved;
- whether unresolved items are blocking or nonblocking for the original target task;
- whether the result is a full strategy result or only a bounded/proxy result.

## 7. Strategy Update Decision

Use `update-strategies-from-manuscript` after the completed strategy is written as a manuscript or result artifact.

- If the manuscript is enough for submission or resolves the original target task, stop the loop immediately.
- Compare the result against the original strategy and the explicit recipe coverage.
- Decide whether to stop/finalize, maintain sequence, revise, reprioritize, repair/repeat, or add a computational direction.
- Keep updated strategies computational chemistry focused.
- Preserve inherited references from the original strategy plan and manuscript artifact.
- Treat `updated_prioritization.recommended_order` as the next execution queue.
- Only after this decision may the workflow proceed to the next strategy.

# Atomistic Modeling and UMA Calculation

Model required structures based on explicit recipe artifacts, not from memory or from a loose reading of the strategy.

Maintain the skill-first rule and choose the narrowest task-specific skill. Never run modeling or calculation for a later strategy until the current strategy has passed through result writing and the update-strategy decision.

# Manuscript

Manuscript generation starts only after computational/result artifacts exist.
Manuscript skills do not run VASP, UMA, DFT, qsub, new literature search, or
new calculations. They assemble, write, cite, insert, and polish only from
accepted evidence and project-local source libraries.

The current manuscript workflow is evidence-first and section-based. It does
not depend on the old `TASK_MANUSCRIPT_LOOP` path.

## Manuscript Inputs

Required inputs for a full manuscript run:

- selected strategy:
  `project/<project_name>/strategy_execution/strategy_selection/selected_strategy.json`;
- accepted calculation and analysis artifacts under the completed strategy
  execution folders;
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

## 1. Figure Plan From Strategy Procedures

Use `strategy-figure-mapper` after strategy selection and after the
calculation/result evidence exists.

The mapper input is the selected strategy's computational block, especially:

- `models`;
- `methods`;
- `dft_details.adsorption_sites`;
- `procedures`.

The mapper asks for conventional computational-chemistry figure types directly
supported by the planned workflow. It must not infer unsupported experiments,
unsupported descriptors, or project-specific figure concepts absent from the
strategy procedures.

Save mapping under:

```text
project/<project_name>/strategy_execution/<strategy_id>_figure/mapping/
  figure_info.json
```

## 2. Figure Realization

Use `strategy-figure-realizer` after figure mapping.

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

## 3. Figure Captions

Use `strategy-figure-captioner` after figure realization.

The captioner writes academic figure titles and captions from realized figures,
strategy evidence, and calculation evidence. Captions must not mention internal
procedure IDs, workflow IDs, skill names, JSON files, or strategy-style prose.

Save outputs under:

```text
project/<project_name>/strategy_execution/<strategy_id>_figure/caption/
  caption_info.json
```

## 4. Insert Figures Into Skeleton DOCX

Use `strategy-figure-docx-inserter`.

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

## 5. Methods Evidence Collection

Use `methods-evidence-collector` before writing Methods.

The collector should keep evidence minimal and general:

- model construction evidence from selected strategy and model manifests;
- gas model metadata such as formula, cell lengths, and PBC when available;
- relaxation/calculation metadata summarized by category, not full raw logs;
- energy/free-energy reference policy and equations when available;
- evidence for the four core computational Methods sections only.

The four core Methods sections are:

1. `model_construction`;
2. `geometry_optimization`;
3. `vibrational_free_energy_corrections`;
4. `electrochemical_free_energy_formalism`.

Do not include optional analysis sections such as DOS, Bader charge, charge
density difference, kinetics, or local geometry analysis unless separate
project evidence and writer support explicitly exist for those sections.

Save:

```text
project/<project_name>/strategy_execution/<strategy_id>_methods/evidence/
  methods_minimal_evidence.json
  methods_writer_digest.json
```

## 6. Methods Writing

Use `methods-section-writer`.

The writer reads `methods_writer_digest.json` and writes structured section
JSON with paragraph and equation blocks. Public Methods prose must translate
internal tools into academic language and must not mention skill names, recipe
IDs, file paths, JSON artifacts, project folders, or planning language.

Equations belong in equation blocks, not hidden inside paragraphs. The writer
may include chemical equations, thermochemical equations, or reference
relations only when supplied by the evidence digest.

Save:

```text
project/<project_name>/strategy_execution/<strategy_id>_methods/text/
  methods_section_text.json
  methods_section_text.md
```

## 7. Methods Insertion

Use `manuscript-section-docx-inserter` to insert
`methods_section_text.json` into the manuscript skeleton or figure-containing
DOCX.

Use OMML/Pandoc equation conversion mode when equation blocks are present.
Keep equation labels out of the visible DOCX body unless explicitly requested.

## 8. Citation Source Extraction

Use `citation-source-extractor` before citation selection.

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

## 9. Section Citation Selection

Use `citation-selector` after a section writer creates section JSON.

Run it separately for Methods, Results, Introduction, and any other citation
requiring section. The selector must preserve original paragraph text and write
citation decisions into structured metadata and citation placeholders.

Rules:

- select only citation keys present in `citation_sources.json`;
- return no citation when support is weak;
- do not cite a sentence whose support is only the manuscript's own figure;
- keep decisions reviewable with confidence and human-check flags.

Save each section's citation layer under that section workspace, for example:

```text
project/<project_name>/strategy_execution/<strategy_id>_methods/citations/
  cited_section_text.json
  citation_decisions.json
```

## 10. Citation Insertion Into DOCX

Use `citation-inserter`.

For section-local tests, the inserter may create a cited DOCX from one
`cited_section_text.json`. For the manuscript, use the global/skeleton-
preserving path:

- merge section citation layers in manuscript order;
- build `used_references.bib` only from selected citation sources;
- preserve the existing DOCX skeleton and figure structure;
- replace only matched manuscript paragraphs and the references placeholder.

Do not use citation insertion as a citation-selection step.

## 11. Results Evidence Collection

Use `results-evidence-collector` after figures, captions, and result artifacts
exist.

The collector builds a compact Results evidence digest from:

- selected-strategy context;
- figure mapping, realization, and captions;
- result artifact or bounded result artifact;
- computed tables such as descriptor summaries, state profiles, rankings, and
  benchmark comparisons;
- model, relaxation, and vibration summaries;
- blocked or unavailable evidence.

It must keep facts separate from prose. It must not hide blocked evidence or
turn unavailable analyses into claims.

Save:

```text
project/<project_name>/strategy_execution/<strategy_id>_results/evidence/
  results_evidence.json
  results_writer_digest.json
```

## 12. Results Writing And Insertion

Use `results-section-writer`.

The writer uses `results_writer_digest.json` and optional DOCX context to write
figure-centered Results and Discussion subsections. It must:

- mention every main-text figure supplied by the digest at least once;
- use only figures and values present in the digest;
- avoid internal workflow language;
- avoid unsupported electronic, kinetic, solvation, or experimental claims;
- avoid standalone limitation or future-work paragraphs.

Insert Results with `manuscript-section-docx-inserter`. Use
`--distribute-figures` when the DOCX already contains figure blocks and Results
paragraphs mention those figure numbers.

Run citation selection and citation insertion for Results after the section is
written.

## 13. Introduction Evidence, Writing, And Insertion

Use `introduction-evidence-collector`.

The collector is literature-led. It uses:

- `citation_sources.json`;
- local paper extraction responses;
- optional experimental extraction notes;
- optional selected strategy only for final present-work framing;
- optional `manuscript_writing_profile.json` for project-specific narrative
  roles and order.

Use `introduction-section-writer` after the evidence collector.

The Introduction writer must:

- follow the digest `narrative_order` and writing profile;
- not impose a reaction, material, dopant, electrolyte, or mechanism absent from
  the evidence;
- not cite inline;
- not mention figures, tables, Results values, calculation counts, or execution
  outcomes;
- use selected-strategy content only for the final present-work objective.

Insert Introduction with `manuscript-section-docx-inserter`. Then run
`citation-selector` and `citation-inserter` for Introduction.

## 14. Title, Abstract, Keywords, And Conclusion

Use `abstract-keywords-conclusion-writer` after Introduction, Results, Methods,
figures, and citations are assembled enough to provide manuscript context.

The writer reads the DOCX and creates:

- title;
- abstract;
- keywords;
- conclusion.

It must not add new claims, citations, figure references, unsupported analyses,
or workflow language. Title insertion should use 14 pt bold formatting when the
section JSON requests it.

Insert title, abstract, keywords, and conclusion with
`manuscript-section-docx-inserter`.

If the skeleton contains `{{SI_TITLE}}`, insert the same title there unless the
user requests a distinct SI title.

## 15. Supporting Information Text

Use `supporting-information-writer` after main text and SI figure placeholders
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

Use `methods-to-si-mover` after SI insertion when detailed Methods text should
be compressed in the main manuscript and preserved in SI. The mover is
configurable and should replace only the configured detail block with a concise
bridge paragraph.

## 16. Final Manuscript Polishing

Run final DOCX polishers as separate, general, config-driven steps.

Recommended order:

1. `manuscript-placeholder-polisher`
  - Remove or replace unresolved placeholders according to a project config.
  - Example config location:
    `project/<project_name>/manuscript/<strategy_id>/final_polish_configs/placeholder_config.json`.

2. `manuscript-reference-polisher`
  - Normalize main manuscript reference paragraphs from a project reference
    config.
  - Do not renumber in-text citations unless the citation layer explicitly
    requires it.

3. `manuscript-si-reference-polisher`
  - Create independent SI references when SI-local citation markers are used.
  - Use configured SI citation mappings and SI reference entries.

4. `manuscript-notation-polisher`
  - Apply configured scientific notation formatting such as subscripts and
    superscripts.
  - Preserve run-level styling so bold small titles do not make whole
    paragraphs bold.

5. `manuscript-equation-number-polisher`
  - Automatically find displayed Word equations and number them sequentially.
  - Consecutive displayed equations are one equation group.
  - Use the borderless three-column table layout by default:
    empty side cell, centered equation group, right-aligned equation number.

Each polisher must write a JSON report and preserve DOCX integrity. Validate
with ZIP/XML checks and, when possible, headless LibreOffice conversion.

## 17. Manuscript Outputs

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

## 18. Manuscript-To-Strategy Feedback

Use `update-strategies-from-manuscript` after the manuscript or bounded result
artifact is complete.

Feed final claims, caveats, blockers, missing procedure coverage, unsupported
claims, and excluded claims back into the strategy plan. This step is mandatory
before selecting or calculating the next strategy.

# Decision Rules

- If the completed manuscript resolves the original target task and has no blocking computational gaps, stop or finalize.
- If the manuscript resolves only a subclaim, continue the loop with a revised next strategy.
- If completed calculations do not match the selected strategy procedures, repair or repeat the completed strategy before moving on.
- If the explicit recipe contains required outputs that were not produced, the result artifact must state the missing procedure coverage.
- If the completed strategy reveals a more important gap than the original next strategy, revise or reprioritize the sequence.
- Follow `prioritization.recommended_order` or `updated_prioritization.recommended_order` as the default queue. Do not skip ahead without a recorded blocker, retirement, supersession, or explicit user instruction.
- If the target task is alkaline HER, `Delta G_H` evidence alone is descriptor-level support, not a complete alkaline mechanism, unless the target was explicitly narrowed to H adsorption only.

# Forbidden Shortcuts

- Do not start modeling immediately after strategy selection. Generate explicit calculation recipes first.
- Do not interpret strategy procedures ad hoc when a recipe artifact exists.
- Do not silently replace full free energies with electronic energies, kinetics with thermodynamics, DOS/charge with geometry descriptors, or charged electrochemical states with neutral gas references.
- Do not mark a strategy complete merely because a bounded proxy produced a positive trend.
- Do not proceed to the next strategy before manuscript/result artifact creation and strategy update.

# Logging

For every skill call and every project-local script, update the project skill log under `project/<project_name>/skill_call_log.md` with:

- skill or script name;
- reason for use;
- input artifacts;
- output artifacts;
- validation result;
- boundary notes such as "translation only" or "no calculations executed".
