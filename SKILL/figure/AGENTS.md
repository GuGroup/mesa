# FIGURE DOMAIN KNOWLEDGE

## OVERVIEW

`SKILL/figure/` turns accepted or explicitly caveated scientific evidence into
standalone plots, structure renders, or publication assemblies. It does not
create missing chemistry, validate calculations, or upgrade diagnostic evidence
into interpretation-grade results.

## WHERE TO LOOK

| Need | Location | Boundary |
|---|---|---|
| Domain evidence and handoff gate | `workflow.md` | Read before every figure leaf |
| VASP total/projected DOS | `plot-dos/` | Converged static `vasprun.xml`; diagnostic-only if unconverged |
| Reaction/free-energy profile | `plot-energy-diagram/` | Validated numeric state table with explicit units/basis |
| Sabatier/descriptor activity plot | `plot-sabatier-volcano/` | Declare descriptor, activity metric, units, and envelope origin |
| Slab/adsorbate structure table | `render-adsorbate-structure-grid/` | Trusted existing structures; rendering is not convergence evidence |
| Multi-panel journal assembly | `create-nature-figure/` | Existing panels/data; agent-authored Python-or-R workflow |
| Runtime assignment | `../../DEPENDENCY/runtimes.yaml` | Check before copying a leaf command |
| Manuscript routing consumer | `../manuscript/figure/` | Mapping/realization owns PNG manuscript handoff |

## CONVENTIONS

- Gate on source acceptance first: recipe/result lineage, validation state,
  caveats, and intended use must be known before any visual encoding.
- Route to the narrowest leaf. DOS is not a generic Nature assembly; a structure
  grid is not evidence that an adsorption state exists or is relaxed.
- Treat `plot-dos`, `plot-energy-diagram`, `plot-sabatier-volcano`, and
  `render-adsorbate-structure-grid` as deterministic leaves. Prefer their
  bundled schemas and scripts; inspect the produced file at final size.
- Treat `create-nature-figure` as a router and authoring contract, not a bundled
  renderer. Resolve the blocking Python/R choice, load only that backend, and
  never cross-render previews, exports, or QA with the other backend.
- Preserve beside every deliverable: source data/structure paths, originating
  recipe or result, plotting skill/script, units, label definitions,
  transformations, acceptance state, and caveats. A bare image path is not a
  complete figure artifact.
- Use PNG for the current DOCX realization handoff. Retain SVG/PDF and source
  specs/scripts for editable or archival work when the leaf supports them.
- Keep captions, figure numbers, claims, and explanatory prose outside structure
  grids; only concise row/column headers belong inside that renderer.
- Before trusting a leaf, compare `SKILL.md`, `references/input-schema.md`, CLI
  flags/defaults, examples, and style files. Unknown style keys must not be
  assumed effective merely because an example contains them.
- For `create-nature-figure`, verify every manifest-referenced fragment and
  on-demand reference exists. Verify any advertised demo/asset path with
  `git ls-files` and `git check-ignore -v`; ignored or absent assets are not a
  usable bundled capability.
- Visual QA checks scientific meaning as well as layout: units, Fermi/zero
  reference, higher-is-better direction, envelope provenance, missing
  projections/states, clipping, readable final-size text, and editable vector
  text where promised.

## ANTI-PATTERNS

- Do not invent missing points, adsorption states, benchmark values, uncertainty,
  statistics, or a fitted volcano envelope for visual completeness.
- Do not describe electronic-energy proxies as free energies without an explicit
  boundary in labels/caption, or descriptor-only volcanoes as activity proof.
- Do not read bond lengths, adsorption heights, relaxation, or convergence from
  a structure render; return to analysis artifacts.
- Use only active identifiers: `create-nature-figure`, `plot-energy-diagram`,
  `render-adsorbate-structure-grid`, and the current kebab-case calculation and
  analysis skill names. Do not route through retired aliases or `TASK_*` names.
- Run `render-adsorbate-structure-grid` in its registered `mesa-modeling`
  runtime. Run the Python-only `create-nature-figure` workflow in
  `mesa-manuscript`.
- Do not claim provenance compliance from renderer output alone; current leaf
  scripts write figures/CSV/cache files but do not enforce the domain metadata
  sidecar contract.
