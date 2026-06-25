# Writing the research prompt

SearchAgent works best when you provide research context, not only a material and
a reaction. The prompt is saved in `run_manifest.json`, used to expand search
queries, and used to prioritize the opportunity report (and, in full mode, the
LLM ranking and report).

## Inline or file

```bash
uv run paper-search run \
  --material RuO2 --reaction HER --out data/runs/ruo2-her \
  --prompt "Prioritize durability and alkaline-stability gaps."
```

For longer context use a Markdown file:

```bash
uv run paper-search run \
  --material RuO2 --reaction HER --out data/runs/ruo2-her \
  --prompt-file research-prompt.md
```

```markdown
We are choosing follow-up DFT calculations for a joint experimental/computational
HER project. The experimental team can synthesize RuO2-rich surfaces but needs
guidance on which facets have enough activity evidence and which ones lack
descriptor or stability data. Prioritize tractable slab calculations that close a
clear literature gap.
```

A CLI prompt value overrides `research.prompt` from `config.yaml`.

## Structured context in config

For reusable context, set the `research` block in `config.yaml`:

```yaml
research:
  prompt: >
    Prioritize DFT-feasible surfaces where HER activity is reported but
    descriptor and stability data are missing.
  decision_criteria:
    - prioritize surfaces with activity evidence but missing descriptors
  target_properties:
    - activity
    - descriptor
    - stability
  constraints:
    - full-text evidence only
  calculation_preferences:
    - adsorption/free-energy descriptors
    - surface stability under reaction-relevant conditions
```

These fields steer query expansion and the prioritization basis, and they appear
under `research_context` in the outputs.
