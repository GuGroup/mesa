# Imported Skill Routing

The manuscript loop owns orchestration and evidence gates. Imported Nature and
catalyst skills provide role-specific technique, but they do not override MESA
source-of-truth boundaries.

## Global Rules

- Load this routing file before reviewer rounds, figure generation/review,
  architecture, section writing, or prose revision.
- Treat `paper/` as canonical. Imported skills may guide outputs, but they must
  work from explicit `paper/` paths and may not infer state from chat memory.
- Literature search, citation verification, reference export, and autonomous
  hypothesis generation remain out of scope for this v1 manuscript loop.
- Missing inputs become `BLOCKER` issues or orchestrator tasks. Do not invent
  calculations, values, methods, citations, figures, or reviewer opinions.

## Writing and Architecture

- `chem-manuscript-architect` must use `SKILL/nature-writing` for
  Nature-family article architecture and section-contract structure. It may
  produce story spine, figure order, outline, and section contracts only.
- `chem-section-writer` must use `SKILL/nature-writing` before drafting any
  locked section chunk.
- `chem-revision-editor` and `chem-section-writer` must use
  `SKILL/nature-polishing` only after section claims, figures, and reviewer
  resolutions are locked. Polishing may improve flow, concision, and terminology
  but must not add claims or citations.
- `chem-revision-editor` must also use
  `references/revision-audit-trail.md` and record author responses, change
  plans, unified diffs, changed-file indexes, and verification notes for the
  active round.

## Reviewer Agents

- `chem-significance-reviewer`, `chem-method-reviewer`, and
  `chem-claim-reviewer` must use `SKILL/nature-reviewer` as the
  Nature-family referee stance and report-structure guide.
- MESA evidence rules are stricter than generic reviewer guidance. If
  `nature-reviewer` would ask for prior-work support, the agent must write a
  "prior-work check required" issue rather than searching for or inventing
  citations.
- Reviewers are read-only. They write structured issue records only.

## Figure Generation and Review

- For general scientific figure planning, composition, QA, and export checks,
  use `SKILL/nature-figure`.
- For reaction-coordinate, adsorption, or free-energy profiles, use
  `SKILL/energy-diagram-plotter`.
- For descriptor/activity, Sabatier, or volcano relationships, use
  `SKILL/sabatier-volcano-plotter`.
- For slab, adsorbate, optimized-structure, or surface-state grids, use
  `SKILL/adsorbate-structure-grid`.
- `chem-figure-reviewer` must use `SKILL/nature-figure` for figure QA and must
  also check any catalyst-specific figure against its source skill contract.

## Environment

Use the manuscript tooling environment for imported plotting/export scripts:

```bash
mamba env create -f mesa/ENVIRONMENT/manuscript_tools/environment.yml
mamba env update -f mesa/ENVIRONMENT/manuscript_tools/environment.yml --prune
mamba run -n mesa-manuscript python -m playwright install chromium
```

Run scripts through the env unless a command is explicitly stdlib-only:

```bash
mamba run -n mesa-manuscript python mesa/SKILL/energy-diagram-plotter/scripts/plot_energy_diagram.py --help
mamba run -n mesa-manuscript python mesa/SKILL/sabatier-volcano-plotter/scripts/plot_volcano.py --help
mamba run -n mesa-manuscript python mesa/SKILL/adsorbate-structure-grid/scripts/build_grid_figure.py --help
mamba run -n mesa-manuscript python mesa/SKILL/TASK_MANUSCRIPT_TYPESET/scripts/export_docx.py --help
```
