# Orchestration Domain Workflow

Use this manual for turning selected-strategy computational procedures into
explicit recipes, planning execution from recipes, recording execution
provenance, diagnosing and repairing recipe-local execution, and recording
missing evidence.

Orchestration does not define scientific calculations or decide scientific
sufficiency. Domain skills execute the plan-assigned work.

# Skills

- `generate-explicit-calculation-recipe`
- `plan-recipe-execution`
- `delegate-strategy-execution`
- `manage-execution-unit`
- `manage-calculation`
- `manage-procedure`
- `record-missing-evidence`

# Generate Explicit Calculation Recipes

Use `generate-explicit-calculation-recipe` immediately after strategy selection
and before any structure building or calculation.

Input is the selected strategy artifact. The skill reads the selected strategy's
computational block:

- `selected_strategy.experiment.computational`, or
- `selected_strategy.experimental.computational`, or
- equivalent direct computational objects supported by the skill.

Recommended command:

```bash
python3 SKILL/orchestration/generate-explicit-calculation-recipe/scripts/generate_explicit_recipe.py \
  --strategy project/<project_name>/strategy_execution/strategy_selection/<run_id>.json \
  --out project/<project_name>/strategy_execution/<run_id>_explicit_recipe
```

Required output shape:

```text
recipe_index.json
P###/
  procedure.json
  mapping.json
  calculations/
    C###/
      recipe.json
```

Each `P###` folder preserves a single source procedure. Each `C###` folder is
one specific calculation or analysis recipe derived from that procedure.

Recipe-generation rules:

- The recipe skill is a translator only.
- It must not decide feasibility, engine choice, policy compliance, repair
  needs, or scientific sufficiency.
- It must not write `blocked`, `unsupported`, `executable`, `feasible`,
  `requires_repair`, or similar decision fields into recipe files.
- It must not execute calculations.
- It must preserve exact source procedure text and JSON-pointer provenance.

# Plan Execution From Recipes

After recipe generation and realization, run:

```bash
python3 SKILL/orchestration/plan-recipe-execution/scripts/plan_recipe_execution.py \
  --recipe-root project/<project_name>/strategy_execution/<run_id>_explicit_recipe
```

The skill writes `execution_plan.json` without modifying recipes. It uses one
LLM call to define execution units, consumers, dependencies, required
artifacts, and produced artifacts. Deterministic code validates full C-recipe
coverage, rejects cycles, assigns `E###` IDs, and assigns all paths inside the
recipe root.

The plan must not select skills, scripts, commands, backends, feasibility, or
status. The later executor selects tools for each unit but must use the unit's
assigned `execution_dir`. Do not execute recipe-backed work before this plan
exists.

# Delegate Planned Strategy Execution

After `execution_plan.json` exists, use `delegate-strategy-execution`. The
parent assigns one sub-agent to the strategy lineage and passes only the
project, profile, lineage, strategy, recipe-root, plan, and explicit execution
constraints. Reuse that agent for resumed or bounded revised execution.

The worker follows the execution graph, loads domain workflows only for the
active E unit, and applies `manage-execution-unit`, `record-missing-evidence`,
`manage-calculation`, and `manage-procedure`. Existing recipe-local artifacts
are the checkpoint; do not create a wrapper state file.

The worker stops before S-level scientific evaluation. The parent owns user
interaction, returned-path validation, continuation after `resume_required`,
the strategy-agent pool, and all strategy-outcome decisions.

Codex may perform minor repairs during execution using its own judgment.

If a required calculation cannot be executed under current project policy or
available skills, do not silently downgrade it. Record the failed E attempt,
diagnose it, and complete E-level repair handling. Then choose one explicit
path:

- stop and ask the user;
- after a terminal `no_repair` or `escalate` decision, use
  `record-missing-evidence` to create unresolved, excluded, or blocked evidence
  records;
- update the strategy through the manuscript/update loop after documenting the
  gap;
- execute only the user-approved subset and label the result as bounded.

# Manage Execution Units And Calculations

Use `manage-execution-unit` after each E-level execution completes or fails.
It writes the factual attempt manifest, diagnoses that attempt, and performs up
to two selected execution-only repairs inside `E###/`, `E###-R1/`, and
`E###-R2/` until E-level handling terminates.

If a terminal E diagnosis still identifies absent required artifacts, use
`record-missing-evidence` before C-level aggregation. Then use
`manage-calculation` to write
`C###/execution/execution_manifest.json`. This manifest factually aggregates
the terminal E attempts and artifacts used by that C calculation.

Do not place diagnosis, evidence acceptance, caveats, exclusions, or repair
decisions in either manifest.

# Manage Procedure Execution

After every C-level manifest for a P procedure exists, use `manage-procedure`.
It writes `P###/procedure_diagnosis.json` as a grouped-execution handoff for
strategy diagnosis.

Evaluate procedure coverage, usable outputs, and remaining execution gaps only.
Do not judge scientific claims, strategy sufficiency, or the next strategy.

When P-level execution gaps should be repaired, the same skill stores numbered
repair records directly under `P###/` using the `-R1` and `-R2` suffixes. After
each repair, regenerate affected lower-level manifests and diagnose the
procedure again. Escalate after an unresolved `-R2`.

# Record Missing Evidence

Use `record-missing-evidence` only after the E-level manifest-diagnosis-repair
loop terminates with a `warn`, `fail`, or `unknown` diagnosis and a
`no_repair` or `escalate` repair decision. Use it for absent required artifacts,
including but not limited to:

- charge density;
- Bader charge;
- PDOS or DOS;
- wavefunction or projector files;
- kinetic barriers;
- solvent data;
- charged electrochemical-state data;
- any recipe-requested output that cannot be produced.

The record must link the terminal diagnosis and repair decision, name the
source recipe, required artifact, reason unavailable, impact on claims, and
whether the gap is blocking or nonblocking. It must not create or replace an
E- or C-level execution manifest.
