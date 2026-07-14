# General MESA Skill Workflow

TEST VERSION.

Use `project/mos_0629_2` as the active result directory unless the user
explicitly names a different project folder.

This root workflow is the authoritative end-to-end contract. Domain manuals
under `SKILL/<domain>/workflow.md` hold the detailed instructions for each
stage. Read this file first, then read the relevant domain manual before using
domain skills.

If a domain manual appears to conflict with this file, this file wins. If an
individual skill's `SKILL.md` gives narrower operational instructions, follow
that skill unless it would violate this root workflow.

# Domain Manuals

- `SKILL/literature/workflow.md`: experimental-data extraction, paper search,
  strategy-paper extraction, general-insight extraction.
- `SKILL/strategy/workflow.md`: strategy generation, one-strategy selection,
  and strategy updates from manuscript/result artifacts.
- `SKILL/orchestration/workflow.md`: explicit calculation recipes, execution
  planning, recipe validation, and missing-evidence records.
- `SKILL/modeling/workflow.md`: slab, gas-phase, surface, and adsorbate model
  preparation from recipe artifacts.
- `SKILL/calculation/workflow.md`: UMA relaxation, UMA vibration, VASP input
  preparation policy, calculation manifests, and raw-result checks.
- `SKILL/analysis/workflow.md`: evidence readiness, energy diagrams,
  descriptor assembly, caveats, and accepted evidence boundaries.
- `SKILL/figure/workflow.md`: standalone structure grids, energy diagrams,
  volcano plots, and Nature-style figure generation.
- `SKILL/manuscript/workflow.md`: evidence-backed manuscript assembly,
  citations, DOCX insertion, SI, polish, and feedback to strategy.

# Central Loop

This workflow is a loop. It is not a linear checklist and it is not valid to
move directly from one strategy calculation into the next strategy calculation.

For this test project, if strategy generation artifacts already exist under the
project folder, start from the Per-Strategy Execution Loop using the latest
`generated_strategies` artifact. Do not regenerate strategies unless the user
asks or the existing strategy artifact is missing, invalid, or superseded.

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

The central rule is: the selected strategy's computational procedures are the
contract. They must first be translated into explicit recipes. Do not silently
replace a requested calculation with an easier proxy.

# Active Skill Organization

Use active skill names from the current `SKILL/` tree. Do not use retired
`TASK_*` names except when reading archived `legacy/` material.

- `literature/`: `extract-data-from-experiment`,
  `search-papers-with-mcp`, `extract-strategy-paper`,
  `extract-general-insights-paper`.
- `strategy/`: `generate-strategies`, `select-next-strategy`,
  `update-strategies-from-manuscript`.
- `orchestration/`: `generate-explicit-calculation-recipe`,
  `validate-recipe-execution`, `record-missing-evidence`.
- `modeling/`: `import-bulk-structure`, `build-slab-models`,
  `build-gas-phase-models`,
  `place-adsorbates-with-adsorbdiff`,
  `propose-surface-models-from-literature`.
- `calculation/`: `relax-uma-trajectory`,
  `calculate-uma-vibrational-frequencies`, `analyze-calculation-results`,
  `manage-vasp-jobs`, `balance-reaction-pathway`.
- `analysis/`: `evaluate-energy-diagram`, `construct-energy-diagram`,
  `assemble-alkaline-her-descriptors`.
- `figure/`: `render-adsorbate-structure-grid`, `plot-energy-diagram`,
  `plot-sabatier-volcano`, `create-nature-figure`.
- `manuscript/`: grouped by stage under `akct/`, `figure/`, `general/`,
  `intro/`, `methods/`, `results/`, `review/`, `si/`, and `polish/`.

# Global Rules

- Use the skill-first operating rule: inspect available skills, select the
  narrowest relevant skill, read that skill's `SKILL.md`, and follow it.
- Save project outputs under `project/<project_name>/`.
- Log every skill call and project-local script in
  `project/<project_name>/skill_call_log.md`.
- Keep strategy work computational chemistry focused. In strategy artifacts,
  `experiment` means computational experiment unless the user explicitly asks
  for a wet-lab plan.
- Preserve inherited references and source metadata from literature and
  strategy artifacts.
- Never treat a bounded proxy as a full proof unless the target was explicitly
  narrowed to that proxy.

# Test Calculation Policy

The active calculation execution backend for this test project is UMA only.
Treat UMA outputs as the authoritative calculation results for this test.

For this test project:

- Prepare VASP-compatible input files when useful for interoperability.
- Do not execute or submit VASP jobs unless the project policy changes.
- Do not use `manage-vasp-jobs` to submit calculations in this test. Use it
  only for preparation, dry-run, status inspection, or future policy-enabled
  VASP work.
- Use `relax-uma-trajectory` for structure relaxations, including bulk and
  clean-slab optimization.
- Use `calculate-uma-vibrational-frequencies` for vibrational calculations.
- If local GPU UMA execution is requested, run UMA locally on the GPU node; do
  not submit UMA through qsub unless explicitly required.

# Per-Strategy Execution Loop

Repeat this loop for one selected strategy at a time.

1. Select exactly one strategy with `select-next-strategy`.
   Read `SKILL/strategy/workflow.md`.

2. Generate explicit calculation recipes with
   `generate-explicit-calculation-recipe`.
   Read `SKILL/orchestration/workflow.md`.

3. Plan execution from `recipe_index.md` and each recipe's `recipe.json`.
   Do not alter generated recipes to record execution status.

4. Build models only from recipe artifacts.
   Read `SKILL/modeling/workflow.md`.

5. Execute only recipe-backed calculations and save outputs under the recipe
   calculation's `execution/` directory.
   Read `SKILL/calculation/workflow.md`.

6. Validate evidence readiness, record missing evidence, and separate accepted,
   caveated, exploratory, failed, and excluded artifacts.
   Read `SKILL/analysis/workflow.md` and
   `SKILL/orchestration/workflow.md`.

7. Write a manuscript-like result artifact or full manuscript from accepted
   evidence only.
   Read `SKILL/manuscript/workflow.md`.

8. Update the strategy plan with `update-strategies-from-manuscript`.
   Only after this update may the workflow proceed to the next strategy.

# Recipe And Execution Contract

The explicit recipe output is the bridge between strategy and execution:

```text
project/<project_name>/strategy_execution/<strategy_id>_explicit_recipe/
  recipe_index.json
  recipe_index.md
  source_computational_section.json
  P###_<procedure_slug>/
    procedure.json
    procedure_map.md
    calculations/
      C###_<calculation_slug>/
        recipe.json
        recipe.md
        execution/
          execution_manifest.json
          ...
```

Each `P###` folder preserves a single source procedure. Each `C###` folder is
one specific calculation or analysis recipe derived from that procedure.

Each `execution_manifest.json` must record:

- source recipe path and source procedure ID;
- skill or project-local script used;
- command or controller input used, when applicable;
- input artifacts;
- output artifacts;
- validation status;
- acceptance state: `accepted`, `accepted-with-caveat`, `exploratory`,
  `failed`, or `excluded`;
- caveats, unsupported pieces, or policy boundaries such as "VASP input only;
  no VASP execution".

Shared batch artifacts may live in a strategy-level shared run directory only
when one command naturally produces outputs for multiple recipes. In that case,
every corresponding `C###/execution/execution_manifest.json` must link to the
shared artifacts and identify the exact subset used for that recipe. Do not
leave calculation outputs only in a shared folder without recipe-local
provenance.

# Decision Rules

- If the completed manuscript resolves the original target task and has no
  blocking computational gaps, stop or finalize.
- If the manuscript resolves only a subclaim, continue the loop with a revised
  next strategy.
- If completed calculations do not match the selected strategy procedures,
  repair or repeat the completed strategy before moving on.
- If the explicit recipe contains required outputs that were not produced, the
  result artifact must state the missing procedure coverage.
- If the completed strategy reveals a more important gap than the original next
  strategy, revise or reprioritize the sequence.
- Follow `prioritization.recommended_order` or
  `updated_prioritization.recommended_order` as the default queue. Do not skip
  ahead without a recorded blocker, retirement, supersession, or explicit user
  instruction.
- If the target task is alkaline HER, `Delta G_H` evidence alone is
  descriptor-level support, not a complete alkaline mechanism, unless the
  target was explicitly narrowed to H adsorption only.

# Forbidden Shortcuts

- Do not start modeling immediately after strategy selection. Generate explicit
  calculation recipes first.
- Do not interpret strategy procedures ad hoc when a recipe artifact exists.
- Do not silently replace full free energies with electronic energies,
  kinetics with thermodynamics, DOS/charge with geometry descriptors, or
  charged electrochemical states with neutral gas references.
- Do not mark a strategy complete merely because a bounded proxy produced a
  positive trend.
- Do not proceed to the next strategy before manuscript/result artifact
  creation and strategy update.

# Logging

For every skill call and every project-local script, update the project skill
log under `project/<project_name>/skill_call_log.md` with:

- skill or script name;
- reason for use;
- input artifacts;
- output artifacts;
- validation result;
- boundary notes such as "translation only" or "no calculations executed".
