# General MESA Skill Workflow

Use `project/<project_name>/` as the active result directory unless the user
explicitly names a concrete project folder.

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
  provenance, diagnosis, repair, and missing-evidence records.
- `SKILL/modeling/workflow.md`: slab, gas-phase, surface, and adsorbate model
  preparation from recipe artifacts.
- `SKILL/calculation/workflow.md`: backend-specific calculation execution,
  calculation manifests, reaction bookkeeping, and raw-result checks.
- `SKILL/analysis/workflow.md`: evidence readiness, energy diagrams,
  descriptor assembly, caveats, and accepted evidence boundaries.
- `SKILL/figure/workflow.md`: standalone structure grids, energy diagrams,
  volcano plots, and Nature-style figure generation.
- `SKILL/manuscript/workflow.md`: evidence-backed manuscript assembly,
  citations, DOCX insertion, SI, polish, and feedback to strategy.

# Central Loop

After `initialize-mesa` has prepared the repository and `initialize-project` has
created or selected the active project profile, the default is to wait for an
explicit user start. Do not enter the research loop automatically from project
initialization. When the user explicitly invokes `start-research` or asks for
guided/autonomous MESA execution, use that optional start gate to confirm the
project profile, project calculation policy, and required runtime readiness.
Codex goal setup and full-access session checks are helpful for autonomous
manuscript-producing runs, but they are optional automation controls and should
only be enforced when the requested run depends on them.

This workflow is a loop. It is not a linear checklist and it is not valid to
move directly from one strategy calculation into the next strategy calculation.

If strategy generation artifacts already exist under the active
project folder, start from the Per-Strategy Execution Loop using the latest
`generated_strategies` artifact. Do not regenerate strategies unless the user
asks or the existing strategy artifact is missing, invalid, or superseded.

Before first strategy generation, if traceable literature extraction artifacts
are missing, use `delegate-literature-workflow`. The parent must spawn one fresh
literature sub-agent for each active phase. Phase 1 stops at the manual-download
queue; the parent waits for user confirmation before starting a fresh phase-2
sub-agent for local paper extraction. Continue to strategy generation only
after the returned artifact paths are validated. Read
`SKILL/literature/workflow.md`.

```text
literature preparation when source evidence is missing
-> strategy generation
-> select one strategy
-> generate explicit calculation recipes from the selected strategy
-> plan execution from those recipes
-> delegate recipe-backed E/C/P execution
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
`TASK_*` names except when reading archived material.

- `literature/`: `delegate-literature-workflow`,
  `extract-data-from-experiment`, `search-papers-with-mcp`,
  `extract-strategy-paper`,
  `extract-general-insights-paper`.
- `strategy/`: `generate-strategies`, `select-next-strategy`,
  `classify-strategy-outcome`, `update-strategies-from-manuscript`.
- `orchestration/`: `generate-explicit-calculation-recipe`,
  `plan-recipe-execution`, `delegate-strategy-execution`,
  `manage-execution-unit`,
  `manage-calculation`, `manage-procedure`,
  `record-missing-evidence`.
- `modeling/`: `import-bulk-structure`, `build-slab-models`,
  `build-gas-phase-models`,
  `place-adsorbates-with-adsorbdiff`,
  `propose-surface-models-from-literature`.
- `calculation/`: `relax-uma-trajectory`,
  `calculate-uma-vibrational-frequencies`, `analyze-relaxation-results`,
  `manage-vasp-jobs`, `run-vasp-local-node`, `balance-reaction-pathway`.
- `analysis/`: `evaluate-energy-diagram`, `construct-energy-diagram`,
  `assemble-alkaline-her-descriptors`, `analyze-dband-center`,
  `charge-flow-analyzer`.
- `figure/`: `render-adsorbate-structure-grid`, `plot-energy-diagram`,
  `plot-sabatier-volcano`, `plot-dos`, `create-nature-figure`.
- `manuscript/`: grouped by stage under `akct/`, `figure/`, `general/`,
  `intro/`, `methods/`, `results/`, `review/`, `si/`, and `polish/`.

# Global Rules

- Use the skill-first operating rule: inspect available skills, select the
  narrowest relevant skill, read that skill's `SKILL.md`, and follow it.
- Save project outputs under `project/<project_name>/`.
- User-facing conversation and QA may be multilingual, but all saved MESA
  research artifacts under `project/<project_name>/` must be written in
  English only.
- Append every MESA skill call and project-local script to
  `project/<project_name>/skill_call_log.md` without reading or rewriting the
  existing log unless the user asks for a log audit.
- Keep strategy work computational chemistry focused. In strategy artifacts,
  `experiment` means computational experiment unless the user explicitly asks
  for a wet-lab plan.
- Preserve inherited references and source metadata from literature and
  strategy artifacts.
- Never treat a bounded proxy as a full proof unless the target was explicitly
  narrowed to that proxy.

# Project Calculation Policy

This root workflow is reusable and must not hard-code an active calculation
backend, project name, test mode, or scheduler policy. The active
`project/<project_name>/project_profile.md` is the single source of truth for
project-specific calculation policy.

Before any calculation-domain step, read the active project profile's backend
and submission policy. If the profile is missing or ambiguous, stop and return
to `initialize-project` or `start-research` instead of assuming UMA, VASP, or a
test policy.

# Per-Strategy Execution Loop

Repeat this loop for one selected strategy at a time.

1. Select exactly one strategy with `select-next-strategy`.
   Read `SKILL/strategy/workflow.md`.

2. Generate explicit calculation recipes with
   `generate-explicit-calculation-recipe`.
   Read `SKILL/orchestration/workflow.md`.

3. Create `execution_plan.json` with `plan-recipe-execution`.
   The plan defines execution units, dependencies, consumers, and paths without
   selecting skills, commands, backends, feasibility, or status.

4. Delegate the planned strategy execution with
   `delegate-strategy-execution`. The parent must spawn one fresh sub-agent for
   the active execution attempt and must not execute the delegated work itself.
   The worker:
   - builds models only from recipe artifacts;
   - executes only recipe-backed E units in plan-assigned paths;
   - loads modeling, calculation, or analysis workflows only when required by
     the current E unit;
   - uses `manage-execution-unit`, `record-missing-evidence`,
     `manage-calculation`, and `manage-procedure` in order;
   - stops before S-level evaluation and returns the skill's compact handoff.
   The parent validates returned paths. For `resume_required`, start a fresh
   sequential worker from existing artifacts; never run concurrent workers for
   the same strategy.

5. Validate evidence readiness, carry terminal missing-evidence records
   forward, and separate accepted, caveated, exploratory, failed, and excluded
   artifacts.
   Read `SKILL/analysis/workflow.md` and
   `SKILL/orchestration/workflow.md`.

6. Write a manuscript-like result artifact or full manuscript from accepted
   evidence only.
   Read `SKILL/manuscript/workflow.md`.

7. Update the strategy plan with `update-strategies-from-manuscript`.
   Only after this update may the workflow proceed to the next strategy.

# Recipe And Execution Contract

The explicit recipe output is the bridge between strategy and execution:

```text
project/<project_name>/strategy_execution/<strategy_id>_explicit_recipe/
  recipe_index.json
  execution_plan.json
  shared_execution/
    E###/
      execution_manifest.json
  P###/
    procedure.json
    mapping.json
    procedure_diagnosis.json
    repair_decision.json
    procedure_diagnosis-R1.json
    repair_outcome-R1.json
    repair_decision-R1.json
    procedure_diagnosis-R2.json
    repair_outcome-R2.json
    repair_decision-R2.json
    calculations/
      C###/
        recipe.json
        execution/
          execution_manifest.json
          units/
            E###/
              execution_manifest.json
```

Each `P###` folder preserves a single source procedure. Each `C###` folder is
one specific calculation or analysis recipe derived from that procedure.

Each E attempt must keep its own `execution_manifest.json` inside `E###/`,
`E###-R1/`, or `E###-R2/`. Keep the existing
`C###/execution/execution_manifest.json` as the recipe-level link to the exact
artifacts used by that calculation.

Each E-level execution manifest must record:

- schema version and execution-unit ID;
- source recipe path;
- skill or project-local script used;
- command or controller invocation used;
- exact input artifacts used;
- exact output artifacts produced;
- factual execution status: `completed` or `failed`.

Each C-level execution manifest must record its calculation ID, source recipe,
source execution plan, terminal E execution sources, optional assembly
invocation, exact input and output artifacts, and factual execution status.

Each P-level procedure diagnosis must report C coverage, outputs available for
strategy diagnosis, remaining execution gaps, and a grouped-execution verdict
of `pass`, `warn`, `fail`, or `unknown`. It must not judge scientific claims.

P-level repair records must stay directly under `P###/`, use `-R1` and `-R2`
filename suffixes, preserve all scientific content, and escalate after an
unresolved second repair.

Do not duplicate `requires`, `produces`, dependencies, consumers, or recipe
settings in either manifest. Keep diagnosis, evidence acceptance, scientific
caveats, exclusions, and repair decisions in separate artifacts.

Single-consumer execution units must use their plan-assigned
`P###/calculations/C###/execution/units/E###/` directory. Multi-consumer units
must use their plan-assigned `<strategy_id>_explicit_recipe/shared_execution/E###/`
directory. The E directory must contain its attempt manifest. Every
corresponding `C###/execution/execution_manifest.json` must link the exact
artifacts used for that recipe. Legacy sibling shared roots remain valid only
when recipe-local manifests preserve exact provenance.

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
