---
name: delegate-strategy-execution
description: >-
  Delegate one planned MESA strategy execution to a fresh, bounded sub-agent
  while keeping raw modeling, calculation, analysis, and repair context outside
  the parent thread. Use after an explicit recipe root and execution_plan.json
  exist, when the strategy must run through terminal E-, C-, and P-level
  execution handling before returning to the parent for S-level evaluation.
---

# Delegate Strategy Execution

## Purpose

Keep strategy-execution context outside the parent thread. Delegate one
strategy's recipe-backed execution graph to one fresh sub-agent, use existing
E/C/P records as durable checkpoints, and stop before scientific S-level
evaluation.

This skill coordinates existing workflows and skills. It does not replace
their contracts or create a second execution state.

## Entry Requirements

Require:

- one active project path;
- one strategy ID;
- its `<strategy_id>_explicit_recipe/` root;
- `recipe_index.json`;
- `execution_plan.json`;
- every indexed `procedure.json`, `mapping.json`, and `recipe.json`;
- the active `project_profile.md`;
- any explicit user restriction that affects execution.

Do not delegate strategy generation, strategy selection, recipe generation, or
execution planning. If the recipe index, plan, or referenced recipes are
missing or inconsistent, report the exact paths and stop.

## Parent Contract

1. Read `workflow.md` and `SKILL/orchestration/workflow.md`.
2. Resolve the entry paths and confirm that exactly one strategy is in scope.
3. Inspect only enough existing E/C/P records to determine whether execution is
   new, resumable, or already terminal.
4. Spawn exactly one fresh sub-agent for the active execution attempt. Use no
   inherited conversation context when the environment supports that option. A
   suitable task name is
   `strategy_execution_<strategy_id>` using lowercase letters, digits, and
   underscores.
5. Pass only the bounded delegation input below.
6. Wait for the terminal response and validate its returned paths without
   loading raw calculation or repair detail into the parent context.
7. For `resume_required`, start one new sequential sub-agent from the same
   artifact checkpoint only after the previous worker has ended.

Do not perform delegated execution in the parent. Do not run two workers for
the same strategy concurrently. If sub-agents are unavailable, report the
boundary instead of silently executing in the parent.

Keep user interaction, returned-path validation, and all S-level evaluation in
the parent.

## Delegation Input

Pass:

```text
project_path: <exact project/<project_name> path>
project_profile: <exact path>
strategy_id: <S###>
recipe_root: <exact explicit-recipe root>
execution_plan: <exact execution_plan.json path>
user_execution_constraints: <explicit constraints or none>
```

Do not pass literature content, manuscript content, strategy-generation
reasoning, or the parent conversation. The recipes and plan are the execution
contract.

## Sub-Agent Boundary

Include these instructions in every delegated task:

- Read `workflow.md`, `SKILL/orchestration/workflow.md`,
  `manage-execution-unit`, `manage-calculation`, `manage-procedure`, and
  `record-missing-evidence`.
- Read a modeling, calculation, or analysis workflow only when the current E
  unit requires that domain; then read each selected worker skill completely.
- Do not spawn another sub-agent.
- Follow the execution plan's dependencies, consumers, and assigned paths.
- Use the project profile only for the execution policy required by the active
  domain workflow. Never use it to modify scientific strategy, recipes, or the
  execution plan.
- Write only inside the recipe root at paths authorized by the execution plan
  and the E/C/P management skills, except for required append-only
  `skill_call_log.md` entries.
- Write all project artifacts in English.
- Do not overwrite finalized manifests, diagnoses, repair records, or missing
  evidence.
- Do not modify repository source, the project profile, selected strategy,
  recipe index, procedure, mapping, recipe, or execution plan.
- Do not generate strategies or recipes, replan execution, write manuscript
  content, classify strategy outcome, or select another strategy.
- Stop at the terminal boundary and return only the compact handoff.

## Checkpoint And Resume

Treat existing recipe-local artifacts as the only durable execution checkpoint.
Do not create a wrapper state, progress index, or delegation report.

On every fresh or resumed run:

1. Read `execution_plan.json`.
2. Inspect existing E attempt chains through `manage-execution-unit`.
3. Inspect C manifests through `manage-calculation`.
4. Inspect P diagnosis and repair chains through `manage-procedure`.
5. Resume from the earliest unfinished plan node without repeating terminal
   work or overwriting prior attempts.

If records are ambiguous, diagnose or report the ambiguity. Do not infer that
raw output alone makes an E, C, or P terminal.

## Ordered Execution Loop

Repeat:

1. Reconcile existing artifacts before starting new execution. Complete any
   required E management for an already executed attempt before dispatching
   another E.
2. Identify E units whose dependencies are terminal and whose required input
   artifacts are available.
3. When several E units are ready, process them sequentially in execution-plan
   order.
4. Load each ready E's source recipe and consumer recipes. Select the narrowest
   matching domain skill; use an appropriate project-local method only when no
   matching skill applies.
5. Execute the E task in its plan-assigned directory. Record the actual
   executor, invocation, inputs, and outputs.
6. Apply `manage-execution-unit` through its terminal manifest, diagnosis, and
   repair boundary.
7. After terminal non-pass E handling, apply `record-missing-evidence` for
   required artifacts that remain unavailable.
8. When every E source required by a C is terminal, apply
   `manage-calculation`.
9. When every C manifest required by a P exists, apply `manage-procedure`
   through its terminal diagnosis and repair boundary.
10. Rescan the graph and continue until every P is terminal or no additional
    work can proceed.

Execute a multi-consumer shared E only once. Ensure each consuming C manifest
links the exact shared artifacts it used.

Continue independent ready work when another branch is blocked. Never bypass a
dependency or silently substitute an easier proxy.

When an authorized calculation is still running, monitor it through the
matching domain skill instead of treating unchanged external state as a
blocker.

## Terminal Status

Return exactly one status:

- `complete`: every indexed P procedure has a terminal `manage-procedure`
  handoff;
- `blocked`: unfinished work remains, no additional ready work can proceed,
  and continuation requires user action, an external-state change, software
  installation, or a recipe/execution-plan change;
- `resume_required`: work remains executable from existing artifacts, but the
  current worker must stop because of its context, time, or local resource
  boundary.

`complete` describes execution handling only. It may include failed, warned,
excluded, or missing evidence and must not be interpreted as scientific
strategy success.

Before returning `resume_required`, finish and persist the current artifact
stage so a fresh worker can resume without reconstructing unsaved reasoning.

## Compact Handoff

Return only:

```text
status: <complete | blocked | resume_required>
strategy_id: <S###>
recipe_root: <exact path>
terminal_procedure_diagnoses: <exact paths or none>
missing_evidence_records: <exact paths or none>
blocked_execution_units: <E IDs with terminal record paths or none>
resume_from: <next unfinished E/C/P IDs or none>
user_action: <one sentence or none>
boundary: stopped before S-level evaluation
```

Do not include detailed scientific findings, raw logs, calculation summaries,
repair narratives, or strategy recommendations in the terminal response. The
parent validates these paths and begins S-level evaluation separately.
