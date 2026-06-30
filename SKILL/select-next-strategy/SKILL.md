---
name: select-next-strategy
description: Select the next MESA per-strategy execution item from a generated strategy artifact. Use when starting workflow.md "Per-Strategy Execution Loop" step 1, when checking prioritization.recommended_order or updated_prioritization.recommended_order, when a completed/blocked/retired strategy status must be skipped, or whenever Codex needs to record which computational chemistry strategy is allowed to run next.
---

# Select Next Strategy

## Purpose

Select exactly one strategy before any modeling or calculation begins. The
selection must come from the current strategy artifact's execution queue:

1. `updated_prioritization.recommended_order` from the latest
   `update-strategies-from-manuscript` artifact, if present and explicitly used
   as the current artifact.
2. Otherwise `prioritization.recommended_order` from the generated strategy
   artifact.

Do not select a strategy from memory, title order, strategy ID order, or local
preference.

## Required Inputs

- `strategy_artifact`: Python or JSON artifact containing `generated_strategies`,
  `updated_strategy_plan`, or an equivalent top-level strategy dictionary.
- `status_dir`: directory containing optional per-strategy status JSON files.
- `output`: path for the selected strategy record.

Status JSON files may be named `S3.json`, `S1.json`, etc. A strategy is skipped
only if its `status` is one of:

- `completed`
- `retired`
- `blocked`
- `superseded`

Missing status means `not_started`.

## Command

Run the bundled script:

```bash
python3 /home/mesa/mesa/SKILL/select-next-strategy/scripts/select_next_strategy.py \
  --strategy-artifact /path/to/generated_or_updated_strategy.py \
  --status-dir /path/to/project/strategy_execution/status \
  --output /path/to/project/strategy_execution/strategy_selection/selected_strategy.json
```

## Workflow

1. Read this `SKILL.md` completely.
2. Identify the current authoritative strategy artifact.
3. Run `scripts/select_next_strategy.py`.
4. Read the emitted `selected_strategy.json`.
5. Record the skill call and reason in the project log required by `AGENTS.md`.
6. Start modeling only for `selected_strategy_id`.

## Output Contract

The output JSON records:

- source strategy artifact
- selected queue key
- recommended order
- skipped strategies and statuses
- selected strategy ID and title
- selection rule
- what the selected strategy can prove
- what it cannot prove
- MESA-style `next_action`

Treat missing or empty recommended order as a hard failure. Stop and repair the
strategy artifact instead of selecting manually.

## Boundaries

- Do not run chemistry calculations.
- Do not update strategy status after completion; use the manuscript/update
  strategy workflow for that decision.
- Do not override `recommended_order` unless the user explicitly instructs it
  and the override is logged before modeling.
