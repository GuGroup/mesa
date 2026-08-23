---
name: select-next-strategy
description: Select and track the next MESA strategy lineage from the authoritative recommended queue. Use when filling configured strategy-agent slots, recording stable agent ownership, preserving a lineage across revisions, stopping new launches after a manuscript-ready result, or recording the single winning strategy.
---

For MESA work, read `SKILL/strategy/workflow.md` first.

# Select Next Strategy

Use the current strategy artifact and project status records to fill one
available strategy-agent slot per call.

## Select

```bash
python3 SKILL/strategy/select-next-strategy/scripts/select_next_strategy.py \
  --strategy-artifact project/<project_name>/strategy/current_strategy_plan.py \
  --status-dir project/<project_name>/strategy_execution/status \
  --max-active-strategies <profile_value> \
  --output project/<project_name>/strategy_execution/strategy_selection/<strategy_id>.json
```

The selector uses `updated_prioritization.recommended_order` when present,
otherwise `prioritization.recommended_order`. It skips `active`, `completed`,
`retired`, `blocked`, and `superseded` strategies. Repeat selection only while
the output reports an available strategy and another configured slot exists.

Selection returns `at_capacity` when all slots are occupied and
`launch_stopped` after an early-stop trigger. Both preserve active work.

Materialize a bounded revision without consuming another slot:

```bash
python3 SKILL/strategy/select-next-strategy/scripts/select_next_strategy.py \
  --strategy-artifact project/<project_name>/strategy/updated_strategy_plan.py \
  --status-dir project/<project_name>/strategy_execution/status \
  --max-active-strategies <profile_value> \
  --continue-lineage <root_strategy_id> \
  --strategy-id <current_strategy_id> \
  --output project/<project_name>/strategy_execution/strategy_selection/<run_id>.json
```

Prefer the current scientific strategy ID for a bounded revision. Legacy
revisions may declare the active lineage or current revision in `supersedes`.
Continuation remains available while new launches are stopped.

## Activate A Lineage

After the recipe and execution plan exist, assign resources, spawn one
execution agent, and record its ownership:

```bash
python3 SKILL/strategy/select-next-strategy/scripts/manage_strategy_status.py activate \
  --status-dir project/<project_name>/strategy_execution/status \
  --lineage-id <root_strategy_id> \
  --strategy-id <current_strategy_id> \
  --run-id <current_run_id> \
  --strategy-artifact project/<project_name>/strategy_execution/strategy_selection/<run_id>.json \
  --recipe-root project/<project_name>/strategy_execution/<run_id>_explicit_recipe \
  --agent-id <agent_id> \
  --max-active <profile_value>
```

For UMA, include `--gpu-index <physical_index>` after creating the project
policy lease. Keep the lease and agent for the lineage until terminal status.
Use the same command to bind a revised strategy artifact to the active lineage.
Supply `--agent-replacement-reason` only when the recorded agent is no longer
available.

## Record Outcome

Keep the scientific strategy ID for a bounded same-lineage revision and assign
a unique run ID such as `S1-R1` to its selected artifact, recipe root, and
report. Write one compact English report at:

```text
project/<project_name>/strategy_execution/strategy_results/<run_id>.md
```

Record its classification:

```bash
python3 SKILL/strategy/select-next-strategy/scripts/manage_strategy_status.py record-outcome \
  --status-dir project/<project_name>/strategy_execution/status \
  --lineage-id <root_strategy_id> \
  --strategy-id <current_strategy_id> \
  --run-id <current_run_id> \
  --classification <classification> \
  --report project/<project_name>/strategy_execution/strategy_results/<run_id>.md \
  --agent-id <agent_id>
```

`extend_strategy` keeps the lineage, agent, slot, and GPU lease active. Bind
the updated strategy and recipe with the optional `--next-*` arguments.
`manuscript_ready`, `prerequisite`, `replace_strategy`, and `blocked` terminate
the lineage. `manuscript_ready` also stops new strategy launches.

## Record The Winner

After all already-active lineages become terminal, compare manuscript-ready
candidates and record exactly one winner:

```bash
python3 SKILL/strategy/select-next-strategy/scripts/manage_strategy_status.py record-winner \
  --status-dir project/<project_name>/strategy_execution/status \
  --lineage-id <winning_lineage_id> \
  --reason "<concise evidence-based reason>" \
  --evidence-source project/<project_name>/strategy_execution/strategy_results/<run_id>.md \
  --output project/<project_name>/strategy_execution/winning_strategy.json
```

Repeat `--evidence-source` for every manuscript-ready candidate report.
Use `winning_strategy.json` as the sole computational strategy input to the
full manuscript workflow.

## Output Boundary

Selection records source artifact, queue, skipped states, capacity, selected
strategy, claim scope, and next action. Status files remain under
`strategy_execution/status/`; recipe artifacts remain independent.
