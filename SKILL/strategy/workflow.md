# Strategy Domain Workflow

Use this manual for strategy generation, one-strategy selection, and strategy
updates after manuscript or bounded-result artifacts.

Strategy work controls the queue. It does not run modeling, calculations,
figures, or manuscript writing.

# Skills

- `generate-strategies`
- `select-next-strategy`
- `update-strategies-from-manuscript`

# Generate Strategies

Use `generate-strategies` after the literature and experimental evidence inputs
are ready.

Generate multiple computational chemistry proof strategies. Keep the strategy
structure compatible with the decompose-style schema:

- `problem`
- `axioms`
- `hypothesis`
- `experiment`
- `results`
- `conclusion`

Rules:

- In strategy artifacts, `experiment` means computational experiment.
- Do not write wet-lab plans unless the user explicitly requests them.
- Preserve source references inherited from literature and extraction outputs.
- Include explicit computational procedures that can later be translated into
  recipes.
- Treat `prioritization.recommended_order` as the default execution queue.

Save the generated strategy artifact under the project folder.

# Select One Strategy

Use `select-next-strategy` before recipe generation, modeling, calculation, or
manuscript work.

Selection rules:

- Select exactly one strategy from the current authoritative strategy artifact.
- Use `updated_prioritization.recommended_order` from the latest
  `update-strategies-from-manuscript` artifact when it is the current plan.
- Otherwise use `prioritization.recommended_order` from the original generated
  strategy artifact.
- Select the first strategy in the current recommended order unless it is
  completed, retired, blocked, or explicitly superseded.
- Do not select from memory, title order, local preference, or strategy ID
  order.
- Do not override the queue without an explicit logged reason.

The selected-strategy artifact must record:

- the selected strategy ID and source artifact;
- what the selected strategy can prove;
- what it cannot prove;
- inherited references and constraints;
- queue or blocker rationale.

Save the selected-strategy artifact under:

```text
project/<project_name>/strategy_execution/strategy_selection/
```

# Strategy As Contract

After selection, the selected strategy's computational procedures are the
contract for execution. The next required step is explicit recipe generation
with `generate-explicit-calculation-recipe`; do not jump directly into model
building or calculations.

# Update Strategy Plan

Use `update-strategies-from-manuscript` after a manuscript-like result artifact
or full manuscript exists for the selected strategy.

Inputs should include:

- selected strategy artifact;
- explicit recipe coverage;
- accepted calculation and analysis outputs;
- missing-evidence records;
- manuscript or bounded-result artifact;
- caveats, blockers, unsupported claims, and excluded claims.

The update must compare the result against the original strategy and the
explicit recipe coverage. It should decide whether to:

- stop or finalize;
- maintain the queue;
- revise a strategy;
- reprioritize the sequence;
- repair or repeat the current strategy;
- retire, block, or supersede a strategy;
- add a new computational direction.

Treat `updated_prioritization.recommended_order` as the next execution queue.
Only after this update may the workflow proceed to another strategy.
