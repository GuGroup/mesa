---
name: map-strategy-figures
description: Propose conventional computational-chemistry figure intents from a selected strategy and attach matching recipe artifacts without analyzing scientific results. Use after recipe execution when Codex needs a compact figure_info.json for figure realization; block only when authoritative missing-evidence summaries or records are present.
---

For MESA end-to-end use, read `SKILL/manuscript/workflow.md` first.

# Strategy Figure Mapper

## Scope

The mapper has two narrow responsibilities:

1. Ask an LLM for generic figure names and importance levels from only
   `models`, `methods`, `dft_details.adsorption_sites`, and `procedures`.
2. Associate those intents with explicit recipe calculations and artifacts.

It does not validate chemistry, judge calculation success, remove figures for
scientific reasons, analyze results, or decide whether a figure proves a claim.
It retains every normalized LLM figure intent in `figure_info.json`.

## Run

```bash
python3 SKILL/manuscript/figure/map-strategy-figures/scripts/map_strategy_figures.py \
  --strategy project/<project>/strategy_execution/strategy_selection/selected_strategy.json \
  --recipe-root project/<project>/strategy_execution/<strategy_id>_explicit_recipe
```

Use `--intent-json` for a saved intent response, or `--dry-run` to inspect the
four-field prompt without calling the API.

Default output:

```text
project/<project>/strategy_execution/<strategy_id>_figure/mapping/
  figure_info.json
  figure_info.md
```

## Blocking Rule

Block a figure only when a matched calculation raises missing evidence through
one of these authoritative artifacts:

- `missing_evidence_summary.json` with status `blocked`, `excluded`, or
  `unresolved`, or with nonempty missing-evidence records;
- `missing_evidence_records.json` with a nonempty `records` list.

Do not use `acceptance_state`, `validation_status`, failed endpoints, excluded
results, scientific caveats, or any ordered status policy to block a figure.
Copy manifest caveats as information only.

If no recipe entry matches an intent, retain the intent with
`grounding.matched=false` and a nonblocking note. Match from C-task text rather
than a recipe-role taxonomy; attach artifacts only after matching.

## LLM Contract

The LLM returns JSON only:

```json
{
  "figures": [
    {"figure_type": "Free-energy diagram", "level": "must_have"}
  ]
}
```

Allowed levels are `must_have`, `useful`, and `supplementary`.

## Output Contract

```json
{
  "schema_version": 3,
  "mapper_mode": "llm_figure_intent",
  "strategy_id": "S1",
  "figures": [
    {
      "id": "F1",
      "figure_type": "Free-energy diagram",
      "type": "energy-diagram",
      "status": "mapped",
      "source": {"procedures": ["P004"], "calculations": ["P004/C001"]},
      "artifacts": ["project/.../free_energy_diagram.png"],
      "grounding": {"matched": true, "quantities": ["free_energy_profile"], "basis": ["P004: ..."]},
      "missing_evidence": [],
      "blockers": [],
      "notes": []
    }
  ],
  "text_only_evidence": [],
  "blockers": []
}
```

`status` is `blocked` only under the missing-evidence rule above; otherwise it
is `mapped`. After mapping, use `realize-strategy-figures`.
