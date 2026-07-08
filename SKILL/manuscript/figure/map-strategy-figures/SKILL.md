---
name: map-strategy-figures
description: Ask an LLM to identify conventional computational chemistry figure types from a MESA selected strategy's models, methods, adsorption sites, and procedures, then attach explicit recipe execution evidence into a compact figure_info.json mapping. Use after recipe-backed calculations/evidence checks when Codex must decide which standard DFT catalysis figures should be must-have, useful, or supplementary and route them to plotting/realization skills.
---

# Strategy Figure Mapper

## Scope

Use this skill to convert a selected computational strategy into figure intents.
The LLM sees only four strategy fields:

- `models`
- `methods`
- `dft_details.adsorption_sites`
- `procedures`

The LLM returns only generic figure names and levels. The script then
deterministically attaches explicit recipe procedures, calculation status,
artifacts, caveats, and blockers. It does not draw figures, validate chemistry,
write manuscript prose, or invent unsupported calculations.

## Workflow

Run the mapper on the selected strategy and explicit recipe root:

```bash
python SKILL/strategy-figure-mapper/scripts/map_strategy_figures.py \
  --strategy project/<project>/strategy_execution/strategy_selection/selected_strategy.json \
  --recipe-root project/<project>/strategy_execution/<strategy_id>_explicit_recipe
```

By default this writes:

```text
project/<project>/strategy_execution/<strategy_id>_figure/
  mapping/
    figure_info.json
    figure_info.md
```

Use `--figure-root` only when the strategy figure workspace should live
somewhere else. Use `--outdir` only for a one-off custom mapping directory.

Use `--dry-run` to inspect the exact prompt and four-field input without calling
the API. Use `--intent-json` to attach recipe evidence to a saved LLM result
without calling the API again.

## LLM Contract

The LLM must return JSON only:

```json
{
  "figures": [
    {
      "figure_type": "Free-energy diagram",
      "level": "must_have"
    }
  ]
}
```

Allowed levels are `must_have`, `useful`, and `supplementary`. Unsupported or
over-interpreted figures must be omitted, not returned as negative examples.

## Evidence Attachment

Treat the strategy/procedure text as the scientific authority and the explicit
recipe manifests as the availability check.

The mapper routes generic figure names through chemistry-agnostic figure
families:

- model/structure figures -> `structure-grid`
- free-energy/profile figures -> `energy-diagram`
- adsorption/free-energy/descriptor comparisons -> `descriptor-comparison`
- projected DOS, Bader, charge transfer, charge-density figures -> `electronic-descriptor`
- local geometry or relaxation checks -> `calculation-diagnostic`

If a returned figure type cannot be matched to explicit recipe evidence, keep it
as a blocked candidate with a blocker note. Do not add hard-coded
reaction-specific quantities such as HER-only descriptor names. Quantity hints
may be extracted generically from procedure text, for example `Delta G_NO` to
`delta_g_no_ev`.

## Output Contract

`figure_info.json` remains compact and realization-oriented:

```json
{
  "schema_version": 1,
  "mapper_mode": "llm_figure_intent",
  "strategy_id": "S1",
  "figures": [
    {
      "id": "F1",
      "level": "must_have",
      "figure_type": "Free-energy diagram",
      "type": "energy-diagram",
      "title": "Free-energy diagram",
      "source": {"procedures": ["P003"], "calculations": ["P003/C006"]},
      "artifacts": ["project/.../energy_diagram.svg"],
      "status": "accepted-with-caveat",
      "skill": "energy-diagram-plotter",
      "grounding": {"status": "grounded", "quantities": ["free_energy_profile"], "basis": ["P003: ..."]},
      "caveats": [],
      "blockers": []
    }
  ],
  "blockers": []
}
```

After mapping, use `strategy-figure-realizer` to create source, exported, QA,
and realization artifacts.
