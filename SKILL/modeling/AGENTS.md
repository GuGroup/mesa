# MODELING DOMAIN KNOWLEDGE

## OVERVIEW

Recipe-backed atomistic structure preparation. Surface work routes through
`workflow.md#surface-preparation`; leaf skills retain narrow generation duties.

## WHERE TO LOOK

| Need | Location |
|---|---|
| Domain entry gates and artifact layout | `workflow.md` |
| Surface sequence and cross-domain handoffs | `workflow.md#surface-preparation` |
| Clean slab generation contract and CLI | `build-slab-models/` |
| Gas reference generation contract and CLI | `build-gas-phase-models/` |
| Adsorbate placement controller/runtime | `place-adsorbates-with-adsorbdiff/` |
| Literature-backed surface proposals | `propose-surface-models-from-literature/` |
| Bulk/slab engine implementation | `../../ENVIRONMENT/build_tools/slabuilder/` |
| Calculation optimization contract | `../calculation/workflow.md` |
| Skill-to-runtime assignment | `../../DEPENDENCY/runtimes.yaml` |

## CONVENTIONS

- Route every recipe-backed surface task through this precedence chain:
  `bulk create/import -> bulk optimization -> slab build -> clean slab
  optimization -> adsorbate placement`.
- Treat `workflow.md#surface-preparation` as the router, not a structure generator.
  Use leaf skills for their named operation only.
- Require the authorizing `P###/C###` recipe and execution plan before work.
  Missing authorization, accepted predecessor, or provenance is a stop gate.
- Keep generation and optimization distinct. `build-slab-models` creates and
  validates clean slabs; the calculation domain owns bulk/slab optimization
  under the selected top-level policy.
- Carry source recipe/procedure IDs, acceptance state, input/output paths,
  relaxation settings/results, validation, and caveats through every handoff.
- Preserve inherited structure metadata and constraints. For MP-derived bulk,
  retain the original material ID and available `initial_magmoms` even when an
  optimized local artifact is passed to slabuilder with `--bulk-file`.
- Place adsorbates only on the accepted optimized clean slab. Carry termination,
  frozen/mobile atoms, and clean-relaxation provenance into placement metadata.
- Use `mesa-modeling` for slabuilder/ASE/pymatgen CLIs and the manual
  `mesa-adsorbdiff` runtime for AdsorbDiff. Calculation runtimes are selected
  by the calculation domain according to the root workflow policy. Do not mix
  interpreters.
- Verify the AdsorbDiff repository, database, configs, and checkpoints exist at
  the chosen runtime paths. `assets/AdsorbDiff` is absent in some checkouts and
  must not be assumed merely because a skill document names it.
- Save model and execution manifests in the authorizing recipe's `execution/`
  directory; artifact existence alone is not acceptance.
- When adding or renaming a skill, synchronize this catalog, root `workflow.md`,
  `DEPENDENCY/runtimes.yaml`, cross-skill links, and `agents/openai.yaml`.

## ANTI-PATTERNS

- Do not use slabuilder's direct MP-to-slab path inside the surface procedure to
  bypass the required optimized-bulk handoff.
- Do not treat prepared inputs, generated POSCARs, or dry-run plans as completed
  optimization or accepted evidence.
- Do not make a generation skill submit calculations or make a calculation
  skill silently choose a different structure, termination, or adsorbate.
- Do not discard original Selective Dynamics flags, inherited constraints,
  material identifiers, magnetic metadata, or recipe-local provenance.
- Do not describe AdsorbDiff as vendored or runnable until its absent/ignored
  asset boundary and machine-specific CUDA/checkpoint requirements are verified.
- Do not let domain/root catalogs, runtime routing, UI metadata, examples, and
  cross-skill handoffs name different active skills.
- Do not infer scientific completion from a zero exit code without inspecting
  validation, acceptance state, and required output artifacts.
