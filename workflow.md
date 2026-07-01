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

Manuscript workflow starts only after computational/result artifacts exist. Manuscript skills do not run VASP, UMA, DFT, qsub, literature search, citation verification, or reference export.

1. Evidence readiness
  - Use `TASK_CALCULATION_RESULT_ANALYZER`.
  - Use `TASK_CONSTRUCT_ENERGY_DIAGRAM` only when the available data model fits.
  - Continue only with accepted result artifacts, trusted structures, tables, and figure inputs.

2. Paper workspace intake
  - Use `mesa-manuscript-loop`.
  - Create/verify canonical `paper/`.
  - Stop if the manuscript topic does not match `paper/` evidence.

3. Claim logic
  - Use `mesa-manuscript-loop`.
  - Create/update `paper/logic/claim-matrix.yaml`.
  - Decide allowed claims before any prose.

4. Plot and figure plan
  - Use `mesa-manuscript-loop`.
  - Build the figure plan from accepted calculation results and claim logic.
  - Create/update `paper/logic/figure-map.yaml`.
  - Map each planned figure to claim IDs.

5. Plot and figure production
  - Use `energy-diagram-plotter`, `sabatier-volcano-plotter`, and `adsorbate-structure-grid` when applicable.
  - Use `nature-figure` only for a new/custom manuscript figure design or multi-panel figure not covered by existing plotter/grid skills.
  - Return generated figures and QA to `figure-map.yaml`.

6. Nature review of logic/figures
  - Use `nature-reviewer` through MESA reviewer roles: `chem-claim-reviewer`, `chem-method-reviewer`, `chem-significance-reviewer`, and `chem-figure-reviewer`.
  - Output structured reviewer issues only.

7. Logic/figure revision loop
  - Use `mesa-manuscript-loop`.
  - Revise claim matrix, figure map, and story spine.
  - Repeat until no open `BLOCKER` remains.

8. Manuscript architecture
  - Use `nature-writing` through `chem-manuscript-architect`.
  - Generate story spine, figure order, outline, and section contracts.
  - Do not write final prose yet.

9. Prose lock
  - Use `mesa-manuscript-loop` validators.
  - Validate claim matrix, figure map, reviewer issues, section contracts, and notation.

10. Section drafting
  - Use `nature-writing` through `chem-section-writer`.
  - Draft evidence-first, then frame Results, Methods, Discussion, Conclusion, Introduction, Abstract/title, References, and SI.
  - A manuscript for one completed strategy may be a bounded result artifact rather than a full final paper.
  - Do not promote a strategy-specific claim into the original target claim unless the claim matrix supports it.

11. Prose polishing
  - Use `nature-polishing`.
  - Polish locked prose only.

12. Nature review of manuscript prose
  - Use `nature-reviewer`.
  - Review generated Markdown manuscript or locked sections.
  - Convert findings to MESA reviewer issues.

13. Manuscript revision loop
  - Use `mesa-manuscript-loop` plus `chem-revision-editor`.
  - Patch accepted issues only.
  - Repeat until manuscript-level blockers are resolved.

14. Final Markdown manuscript
  - Use `mesa-manuscript-loop`.
  - Finalize canonical Markdown/YAML/BibTeX/figure files under `paper/`.

15. Final typeset/export
  - Use `mesa-manuscript-typeset`.
  - Run check-only export first.
  - Then export DOCX/styled DOCX.
  - Export success is assembly/cross-reference verification, not scientific approval.

16. Manuscript-to-strategy feedback
  - Use `update-strategies-from-manuscript`.
  - Feed final claims, caveats, blockers, and excluded claims back into the next strategy.
  - This step is mandatory before the next modeling/calculation strategy begins.

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
