---
name: classify-strategy-outcome
description: >-
  Assemble bounded evidence and classify a completed computational strategy
  into one ordered next-workflow route. Use after procedure-level execution
  handling when Codex must prepare an outer-LLM input or distinguish manuscript
  readiness, bounded strategy extension, prerequisite value, strategy replacement, or an
  external blocker.
---

For MESA end-to-end work, read `workflow.md` and
`SKILL/strategy/workflow.md` first.

# Classify Strategy Outcome

## Assemble Input

Run:

```bash
python3 SKILL/strategy/classify-strategy-outcome/scripts/prepare_strategy_outcome_input.py \
  --project-root . \
  --strategy-artifact project/<project_name>/strategy/current_strategy_plan.py \
  --strategy-id S1 \
  --recipe-root project/<project_name>/strategy_execution/<run_id>_explicit_recipe \
  --missing-evidence project/<project_name>/path/to/missing_evidence.json \
  --output project/<project_name>/strategy_execution/<run_id>_explicit_recipe/strategy_outcome_input.json
```

Repeat `--missing-evidence` when needed. Omit it when no missing-evidence record
exists.

The script:

- accepts original `generated_strategies` or an `updated_strategy_plan` linked
  to its original artifact through `revision_context`;
- extracts only the agreed claim, strategy, and prioritization fields, including
  each strategy's `decision_target` and `author_claim_support_if_successful`;
- inherits those two classification-boundary fields only for a revision tied
  to an existing strategy or its declared `supersedes` lineage;
- uses `recipe_index.json` only to require one terminal diagnosis for every
  procedure;
- validates that each `-R1` or `-R2` diagnosis was authorized by the preceding
  `repair_once` decision and has its matching repair outcome;
- selects the newest diagnosis from the validated repair chain;
- loads only JSON paths explicitly listed in
  `outputs_for_strategy_diagnosis`;
- includes explicitly supplied missing-evidence JSON; and
- writes one `strategy_outcome_input.json`.

Relative paths inside diagnoses are resolved from `--project-root`. A referenced
path must stay within that root.

## Boundary

The assembler must not search for extra evidence, follow nested references,
read raw logs or binaries, summarize values, judge evidence, or select a class.
Fail on missing procedures, malformed diagnoses, missing references,
non-JSON referenced outputs, invalid or incomplete P-level repair chains,
duplicate strategy IDs, or an unknown current strategy.

A `new_direction` requires a complete claim-boundary contract. The assembler
fails when those fields are absent.

`recipe_index.json` and source files are validation inputs; their unrestricted
contents are not copied into the LLM input.

## Classification

Run:

```bash
python3 SKILL/strategy/classify-strategy-outcome/scripts/classify_strategy_outcome.py \
  --input project/<project_name>/strategy_execution/<run_id>_explicit_recipe/strategy_outcome_input.json \
  --output project/<project_name>/strategy_execution/<run_id>_explicit_recipe/strategy_outcome_classification.json
```

The script calls the OpenAI Responses API, requests one class, and validates
the returned JSON. It reads `OPENAI_API_KEY` from the environment, `.env`, or
`DEPENDENCY/.env`. Use `--dry-run` to validate the assembled input without an
API call.

An individual scientific output above 250,000 bytes remains validated in the
assembled artifact but is omitted from the LLM prompt and listed as unavailable
in its prompt scope.

Apply an epistemic gate first: use `blocked` when external conditions or
insufficient records prevent a reliable judgment. Otherwise apply this order:

1. `manuscript_ready`: evidence directly supports the exact author-reported
   claim with sufficient coverage.
2. `extend_strategy`: the strategy's central hypothesis and direction remain
   valid, but one bounded additional computational procedure is needed to close
   a localized scientific evidence gap.
3. `prerequisite`: actual outputs materially enable another generated strategy
   and the relationship is supported by `prioritization.rationale`.
4. `replace_strategy`: the result is negative or unpromising, or recovery
   requires changing the strategy's central hypothesis or direction.

Negative scientific results are `replace_strategy`, not `blocked`.
Execution is assumed to have completed through the E/P diagnosis–repair
workflow before this classification begins.

The classification JSON contains:

- `schema_version`;
- `strategy_id`;
- `classification`;
- one concise `reason`;
- exact `evidence_sources`;
- a compact `next_run` for `extend_strategy`, `prerequisite`, or
  `replace_strategy`;
- a `blocker` only for `blocked`.

`next_run.report` must contain no more than six one-sentence items:

- `extend_strategy`: evidence gap, additional procedure, and expected evidence;
- `prerequisite`: inherited value, target-run objective, and any bounded
  constraint;
- `replace_strategy`: failed expectation, observed evidence, replacement
  implication, replacement hypothesis, procedure, and expected evidence.

`manuscript_ready` and `blocked` must set `next_run` to `null`.

The caller must reject invented sources, unknown strategy or procedure IDs,
reports longer than six sentences, missing class-specific information, or
contradictory fields.

## Final Boundary

This skill assembles evidence and classifies one strategy outcome. It does not
perform repairs, modify strategies, write manuscript text, update the strategy
queue, or install software.
