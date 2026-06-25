# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-24

## OVERVIEW
`mesa/SKILL` is a set of task bundles. Each task owns a narrow workflow boundary: extract context, evaluate reaction energy, build structures, place adsorbates, run/analyze MLIP or VASP, or assemble reaction paths.

## STRUCTURE
```text
SKILL/
|-- TASK1_experimental_information_extraction/
|-- TASK2_reaction_energy_evaluation/
|-- TASK_BUILD_GAS_PHASE_MODELS/
|-- TASK_BUILD_SLAB_MODELS/
|-- TASK_PLACE_SURFACE_ADSORBATES/
|-- TASK_CALCULATION_RESULT_ANALYZER/
|-- TASK_UMA*/
|-- TASK_VASP_JOB/
|-- _shared/                         # Imported Nature-family shared material.
|-- nature-writing/
|-- nature-polishing/
|-- nature-reviewer/
|-- nature-figure/
|-- energy-diagram-plotter/
|-- sabatier-volcano-plotter/
|-- adsorbate-structure-grid/
`-- ToBe*/
```

## WHERE TO LOOK
| Task | Location | Notes |
| --- | --- | --- |
| Deterministic extraction | `TASK1_experimental_information_extraction/` | Stdlib, no external APIs. |
| Reaction CSV evaluation | `TASK2_reaction_energy_evaluation/` | CSV validation/ranking; no VASP. |
| Clean slab generation | `TASK_BUILD_SLAB_MODELS/` | Uses slabuilder; stops at validated clean slabs. |
| Gas molecule structures | `TASK_BUILD_GAS_PHASE_MODELS/` | Neutral POSCAR/metadata only; no INCAR. |
| Surface adsorbates | `TASK_PLACE_SURFACE_ADSORBATES/` | Downstream of selected clean slab termination. |
| Result analysis | `TASK_CALCULATION_RESULT_ANALYZER/` | Read-only analyzer plus visual-review artifacts. |
| Manuscript loop | `TASK_MANUSCRIPT_LOOP/` | Post-computation manuscript workspace, claim/figure/reviewer gates, and prose-lock validators. |
| Manuscript typeset | `TASK_MANUSCRIPT_TYPESET/` | Typst/PDF and DOCX export assembly from the canonical `paper/` workspace. |
| Imported Nature writing | `nature-writing/`, `nature-polishing/`, `nature-reviewer/` | Catalyst-library guidance for Nature-family drafting, polishing, and pre-submission review. |
| Imported figure skills | `nature-figure/`, `energy-diagram-plotter/`, `sabatier-volcano-plotter/`, `adsorbate-structure-grid/` | Publication figure guidance plus catalyst-specific plotting/rendering helpers. |
| UMA/MLIP handoff | `TASK_UMA/`, `TASK_UMA_traj/`, `TASK_UMA_vib/` | Dry-run/local/qsub boundaries in README/controllers. |
| VASP jobs | `TASK_VASP_JOB/` | Has child instructions because job submission is high risk. |

## CONVENTIONS
- `SKILL.md` task folders use direct script paths relative to the task directory.
- TASK1/TASK2 expose `run(input_data, context)` and CLI dry-run examples.
- Many tests load modules by path, call `run(...)`, and separately exercise CLI output writing.
- Use `mamba run -n modeling` for slab/adsorbate/trajectory workflows that need scientific dependencies.
- Preserve the documented standard output envelope when a task defines one.
- Manuscript work must treat `paper/` as canonical: run the manuscript-loop
  validators before prose edits, and keep Typst/PDF/DOCX outputs disposable.
- Imported Nature/catalyst skills are standalone helpers for writing, reviewer
  simulation, polishing, and figures. Literature search and citation skills are
  intentionally not imported into MESA at this stage.

## ANTI-PATTERNS
- Do not let one task compensate for an unresolved upstream gate; return to the owning task.
- Do not strip tags/metadata from generated structures; downstream tasks depend on them.
- Do not submit calculations directly from broad generated candidate sets.
- Do not use OSZICAR-only analysis for structural conclusions.

## COMMANDS
```bash
python TASK1_experimental_information_extraction/MYSKILL/experimental_information_extraction.py --input TASK1_experimental_information_extraction/examples/input.example.json --output /tmp/task1.json --dry-run
python TASK2_reaction_energy_evaluation/MYSKILL/reaction_energy_evaluation.py --input TASK2_reaction_energy_evaluation/examples/input.example.json --output /tmp/task2.json --dry-run
mamba run -n modeling python TASK_BUILD_SLAB_MODELS/scripts/build_slab_model.py --formula Pt --miller 1 1 1
mamba run -n modeling python TASK_PLACE_SURFACE_ADSORBATES/scripts/place_surface_adsorbates.py --slab structures/Pt_111/POSCAR --adsorbate CO
python TASK_MANUSCRIPT_LOOP/scripts/init_paper_workspace.py --root /tmp/mesa_paper
python TASK_MANUSCRIPT_TYPESET/scripts/build_typst.py --paper /tmp/mesa_paper/paper --out /tmp/mesa_typeset --check-only
```
