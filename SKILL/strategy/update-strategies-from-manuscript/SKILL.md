---
name: update-strategies-from-manuscript
description: Update an existing computational chemistry strategy plan after one strategy has been completed and summarized in a manuscript or manuscript-like result artifact. Use when Codex needs to compare a completed strategy result, such as S1, against the original generate-strategies output and decide whether to maintain the original strategy sequence, revise details of the next strategy, reprioritize remaining strategies, repair/repeat the completed strategy, or add a new computational direction. The output must remain evidence-backed, preserve inherited references, and use decompose-style problem/axioms/hypothesis/experiment/results/conclusion strategy blocks.
---

# Update Strategies From Manuscript

## Overview

Use this skill after an initial `generate-strategies` plan exists and at least one strategy has been completed. The completed strategy should be represented by a manuscript, draft, report, or manuscript-like result artifact.

The updater must:

- Read the original generated strategy plan as the baseline.
- Read the manuscript result for the completed strategy, usually `S1`.
- Decide the next computational direction from evidence, not momentum.
- Preserve or revise the original strategy sequence only when the manuscript supports that decision.
- Add a new direction when the manuscript reveals a mechanism, failure mode, descriptor, surface state, or computational gap that the original plan missed or under-prioritized.
- Keep every strategy computational chemistry focused.
- Preserve inherited references from the original strategy plan and manuscript artifact.

## Inputs

Required:

- Original `generated_strategies` artifact from `generate-strategies`.
- Manuscript or manuscript-like artifact generated after completing one strategy.
- Completed strategy ID, such as `S1`.

Optional:

- Supporting result artifacts, such as calculation summaries, tables, figures-as-text, reviewer notes, or intermediate reports.
- Target task and material domain, if not already clear from the original strategy plan.

## Workflow

1. Confirm the original strategy artifact and manuscript artifact exist.
2. Run `scripts/update_strategies_from_manuscript.py`.
3. Review the output for:
   - explicit assessment of the completed strategy;
   - an explicit next-step decision;
   - referenced rationale for maintaining, revising, reprioritizing, repairing, or adding strategies;
   - computational-only strategy blocks;
   - no unsupported new directions hidden as high-confidence decisions.
4. Preserve the update artifact because it is the handoff from completed work to the next strategy cycle.

## Script

Run:

```bash
python3 /path/to/update-strategies-from-manuscript/scripts/update_strategies_from_manuscript.py \
  --original-strategies /path/to/generated_strategies.py \
  --manuscript /path/to/manuscript_or_result.md \
  --completed-strategy-id S1 \
  --target-task "..." \
  --material-domain "..."
```

Useful options:

- `--supporting-artifact`: additional result artifact. May be repeated.
- `--num-next-strategies`: requested number of updated strategies. Defaults to `5`.
- `--task-note`: non-conflicting computational context.
- `--output`: write generated text to a file.
- `--save-response`: write the full OpenAI API response JSON for debugging.
- `--dry-run`: validate inputs and print request metadata without calling the API.

The script reads `OPENAI_API_KEY` from the environment and uses only the Python standard library.

## Output Contract

The script asks for exactly one Python assignment named `updated_strategy_plan`:

```python
updated_strategy_plan = {
    "target_task": {...},
    "revision_context": {...},
    "completed_strategy_assessment": {...},
    "strategy_update_decision": {...},
    "updated_strategies": [
        {
            "strategy_id": "S2",
            "origin": "unchanged_from_original | revised_from_original | reprioritized_from_original | new_direction | repair_completed_strategy",
            "supersedes": "...",
            "revision_reason": "...",
            "problem": {...},
            "axioms": {...},
            "hypothesis": {...},
            "experiment": {...},
            "results": {...},
            "conclusion": {...},
            "decision_trace": [...]
        }
    ],
    "updated_prioritization": {...},
    "retired_or_deprioritized_strategies": [...],
    "new_unsupported_gaps": [...]
}
```

Each updated strategy must keep the decompose-style structure. `experiment` means computational experiment only. Do not propose synthesis, characterization, electrochemical tests, or wet-lab validation as a next strategy.

Reference objects must identify whether support came from the original strategy plan, the manuscript result, or a supporting artifact:

```python
{
    "artifact": "...",
    "artifact_type": "original_strategies | manuscript | supporting_artifact",
    "strategy_id": "...",
    "manuscript_section": "...",
    "inherited_source": {...},
    "supporting_statement": "...",
    "decision_role": "completed_result | limitation | original_plan | sequence_decision | revision_reason | new_direction | computational_test | risk | prioritization"
}
```

Use `None` for unavailable fields. Do not invent manuscript claims, strategy outcomes, references, DFT settings, or computed values.
