# Strategy Domain Workflow

Use this manual for strategy generation, bounded concurrent selection,
strategy-outcome classification, and evidence-backed revision.

# Skills

- `generate-strategies`
- `select-next-strategy`
- `classify-strategy-outcome`
- `update-strategies-from-manuscript`

# Generate Strategies

Generate multiple computational proof strategies after literature and
experimental evidence are ready. Preserve the decompose-style structure,
inherited references, explicit computational procedures, claim boundary, and
`prioritization.recommended_order`. In strategy artifacts, `experiment` means
computational experiment.

# Strategy Pool

Read `strategy_execution.max_active_strategy_agents` from the project profile.
Fill open slots by calling `select-next-strategy` once per lineage. The limit
applies to active strategy-execution agents; recipe-authorized calculation
count remains governed by dependencies and the calculation backend.

A lineage starts from one generated strategy and keeps one agent, one active
slot, and one UMA GPU lease through bounded revisions. A change to the central
hypothesis or direction terminates the current lineage and enters the queue as
a complete new strategy contract.

Keep the scientific strategy ID for `extend_strategy`. Use a unique `run_id`
and recipe root for each bounded revision so `next_run.target_strategy_id`
continues to match the strategy contract.
Use the strategy ID as the initial run ID.

Each slot is non-preemptive:

1. select one strategy for an open slot;
2. generate recipes and an execution plan;
3. assign resources, spawn its agent, and activate the lineage;
4. delegate execution and reuse that agent for resume and repair;
5. classify the terminal E/C/P evidence;
6. revise the same lineage or mark it terminal;
7. fill the released slot when strategy launch remains open.

# Result Report

After classification, write one compact English report under:

```text
project/<project_name>/strategy_execution/strategy_results/<run_id>.md
```

Record the decision target, recipe coverage, accepted evidence, missing or
excluded evidence, bounded conclusion, classification, and exact source paths.
This internal report is the updater input and candidate-comparison artifact;
it is not a full manuscript.

# Outcome Routes

- `manuscript_ready`: mark the lineage terminal and stop new strategy
  launches.
- `extend_strategy`: feed the result report to
  `update-strategies-from-manuscript`, bind the revised artifact and recipe to
  the same lineage through selection's continuation mode, and continue with
  the same agent.
- `prerequisite`: mark the lineage terminal and preserve its enabling evidence
  for the target strategy.
- `replace_strategy`: mark the lineage terminal; update or reprioritize the
  queue when its evidence changes the next direction.
- `blocked`: mark the lineage terminal with its external or evidentiary
  blocker.

Use the existing updater when evidence calls for revision or reprioritization.
Its output remains the current strategy plan. Updated same-lineage strategies
inherit classification-boundary fields from their declared original source;
new directions carry a complete evidence-backed claim-boundary contract.

# Early Stop And Winner

The first `manuscript_ready` result closes strategy launch. Let already-active
lineages reach a terminal outcome, compare all manuscript-ready candidates,
and record exactly one `winning_strategy.json`. With one active slot, the first
manuscript-ready lineage is the winner.

Use only the winning strategy's computational evidence for the full
manuscript. Retain other reports as internal project records. Literature and
general background citations remain available across the project source
library.

When no lineage is manuscript-ready, finish with terminal reports and
unresolved evidence rather than opening the manuscript workflow.
