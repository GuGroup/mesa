---
name: realize-strategy-figures
description: Realize map-strategy-figures figure_info.json candidates into a strategy figure workspace with source files, PNG exported figures, QA notes, and a realization manifest. Use after map-strategy-figures when Codex must copy existing PNG assets, generate simple tabular PNG figures, prepare specialized renderer manifests, and record blocked or skipped figure candidates.
---

For MESA end-to-end use, read `SKILL/manuscript/workflow.md` before applying this skill.

# Strategy Figure Realizer

## Scope

Use this skill to turn `map-strategy-figures` output into file-backed figure
artifacts under the same `<strategy_id>_figure/` workspace.

It orchestrates figure realization; it does not validate chemistry or invent
missing evidence. It may copy already-rendered PNG figures, generate simple
table-backed PNG charts, prepare source manifests for specialized figure
skills, and write QA/blocker notes.

## Workflow

Run the realizer on the mapping output:

```bash
python SKILL/manuscript/figure/realize-strategy-figures/scripts/realize_strategy_figures.py \
  --mapping project/<project>/strategy_execution/<strategy_id>_figure/mapping/figure_info.json
```

Default output:

```text
project/<project>/strategy_execution/<strategy_id>_figure/
  mapping/
  source/
  exported/    # PNG files only
  qa/
  realization/
    figure_realization.json
    figure_realization.md
```

## Behavior

- `energy-diagram`: copy existing PNG exports and source plot specs.
- `descriptor-comparison`: generate a compact PNG bar chart from
  strategy-backed descriptor CSV/JSON artifacts. Do not plot project-local
  composite scores unless the strategy or recipe explicitly names them.
- `benchmark-comparison`: generate a compact PNG comparison chart from
  benchmark JSON artifacts.
- `calculation-diagnostic`: collect existing analyzer/contact-sheet PNGs.
- `structure-grid`: write a `render-adsorbate-structure-grid` source manifest. If
  existing analyzer overlay PNGs are available, compose a real grid PNG from
  those images; otherwise leave the candidate `source-ready` with the
  recorded specialized-renderer command.
- blocked or `si-archive` candidates: write QA/blocker notes; do not fabricate
  exported figures.

Use `--force` to overwrite existing realized outputs. Use `--include-blocked`
only when blocked candidates should receive source/QA bookkeeping.

The exported figure contract is PNG-only. Keep vector or PDF formats outside
`exported/` unless the skill is explicitly extended with an output-format
option later.

## Scientific Grounding

Respect `figure_info.json` `grounding` fields. If a candidate is not grounded,
record it as blocked/skipped and do not export a figure. For
`descriptor-comparison`, plot only metrics listed in `grounding.quantities`;
the metric name can be reaction-specific, such as `delta_g_no_ev`, as long as it
was authorized by the mapping. Ignore extra columns that happen to exist in
source tables. When staging source copies, sanitize known ungrounded derived
fields or narrative text such as local bounded-activity scores unless the
mapping grounding explicitly authorizes them.

## Output Contract

The realization manifest records one record per mapped figure:

```json
{
  "id": "F1",
  "type": "energy-diagram",
  "state": "realized",
  "source_files": ["..."],
  "exported_files": ["..."],
  "qa_file": "...",
  "command": "..."
}
```

Valid states are `realized`, `source-ready`, `blocked`, `skipped`, and `failed`.
