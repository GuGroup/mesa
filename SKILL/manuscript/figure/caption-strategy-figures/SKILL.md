---
name: caption-strategy-figures
description: Create public manuscript-style figure titles and captions for map-strategy-figures and realize-strategy-figures outputs. Use after figures have been mapped and realized when Codex must write paper-ready figure_title, caption, and extended_caption fields from figure_info.json, figure_realization.json, exported PNGs, grounding quantities, caveats, blockers, and source metadata while keeping workflow provenance out of public text.
---

For MESA end-to-end use, read `SKILL/manuscript/workflow.md` before applying this skill.

# Strategy Figure Captioner

## Scope

Use this skill after `map-strategy-figures` and `realize-strategy-figures`.
It writes manuscript-facing figure titles and captions; it does not draw
figures, validate chemistry, or add new scientific claims.

The captioner reads:

- `<strategy_id>_figure/mapping/figure_info.json`
- `<strategy_id>_figure/realization/figure_realization.json`
- realized QA/source metadata referenced by those files

Default output:

```text
project/<project>/strategy_execution/<strategy_id>_figure/
  caption/
    caption_info.json
    caption_info.md
```

## Workflow

Run:

```bash
python SKILL/manuscript/figure/caption-strategy-figures/scripts/caption_strategy_figures.py \
  --mapping project/<project>/strategy_execution/<strategy_id>_figure/mapping/figure_info.json
```

Use `--no-llm` for deterministic captions only. Without `--no-llm`, the script
uses OpenAI when `OPENAI_API_KEY` is available and falls back to deterministic
captions if the model output is missing or rejected.

Useful options:

```bash
--save-prompt project/.../caption/llm_prompt.txt
--save-response project/.../caption/llm_response.json
--outdir project/.../caption
```

## Caption Rules

Figure titles and captions must be public, manuscript-facing text:

- Use only figure type, routed type, realized state, scientific system label,
  reaction label, plotted quantities, and figure-visible content.
- Do not add causal interpretation, performance claims, experimental claims, or
  manuscript-level conclusions.
- Do not mention unsupported descriptors or blocked figures as if realized.
- For blocked figures, keep `figure_title`, `caption`, and `extended_caption`
  empty and record blockers only in metadata.
- Prefer academically conventional phrasing such as "computed", "modeled",
  "optimized", "free-energy diagram", and "adsorption free-energy comparison".
- Round non-integer values in public caption text to at most two decimal places
  (for example, `1.184` becomes `1.18`); leave integers as integers. Preserve
  full precision in source and provenance data.

Use `figure_title` for a concise heading without trailing punctuation. The
future DOCX inserter can format it as `Fig. N | {figure_title}. {caption}`
without inventing or rewriting scientific text.

Never place internal workflow/provenance language in `figure_title`, `caption`,
or `extended_caption`, including:

- `strategy`, `procedure`, `P001`/`C001` IDs, source procedure/calculation IDs
- `mapping`, `realization`, `realized`, `exported`, `PNG`, `QA`
- `caveat`, `blocker`, `artifact`, `manifest`, file paths, or JSON filenames

Keep those details in `provenance`, `source_basis`, `caveats`, and `blockers`.

## Output Contract

`caption_info.json` contains public title/caption fields plus internal provenance:

```json
{
  "schema_version": 2,
  "strategy_id": "S1",
  "captions": [
    {
      "figure_id": "F4",
      "state": "realized",
      "figure_type": "Adsorption free-energy comparison",
      "exported_files": ["project/.../F4_descriptor-comparison.png"],
      "figure_title": "Adsorption free-energy comparison",
      "caption": "Bars show computed Delta G_H (eV) values across pristine and Ni-modified MoS2 edge motifs.",
      "extended_caption": "The comparison summarizes the thermodynamic quantities calculated for each modeled motif.",
      "source_basis": ["P005"],
      "caption_source": "deterministic",
      "caveats": [],
      "blockers": [],
      "provenance": {
        "source_basis": ["P005"],
        "source_calculations": ["P005/C003"],
        "grounding_quantities": ["delta_g_h_ev"],
        "exported_files": ["project/.../F4_descriptor-comparison.png"],
        "source_files": [],
        "realization_notes": [],
        "caveats": [],
        "blockers": []
      }
    }
  ]
}
```

Use the `Public Captions` section of `caption_info.md` for manuscript review.
Use `Internal Provenance` only for audit/debugging.
