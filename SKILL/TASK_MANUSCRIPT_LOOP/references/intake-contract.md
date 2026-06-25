# Gate 0 Intake Contract

Gate 0 converts completed MESA artifacts into a deterministic manuscript
workspace. It is a normalization step only: it does not calculate, repair,
reinterpret, or complete missing science.

## Required Source Files

The intake source may include:

- MESA task output envelopes from build, adsorbate placement, reaction-energy,
  UMA, VASP, or analyzer tasks.
- Analyzer folders containing `analysis_summary.json`, metrics, selected frames,
  visual-review request files, visual-review outputs, overlays, and notes.
- Structure files such as POSCAR, CONTCAR, CIF, XYZ, EXTXYZ, or trajectory
  snapshots.
- Tables such as CSV, TSV, YAML, or JSON summaries from completed calculations.
- Human prior notes that describe provenance, decisions, known caveats, or
  intentionally excluded data.
- Manually supplied reference context, if present. Literature search and
  citation verification are excluded from v1.

## Required Output Files

Gate 0 must produce or confirm:

- `paper/inputs/manifest.yaml`: complete inventory of normalized source files.
- `paper/logic/result-inventory.md`: readable inventory grouped by system,
  method, status, and intended manuscript role.
- `paper/state/current-stage.yaml`: stage state set to `results_inventory`,
  `claim_matrix`, or a blocked intake state.
- `paper/state/ledger.jsonl`: append-only event for intake completion or block.

## Manifest Fields

Each source item in `paper/inputs/manifest.yaml` must include:

- `id`: stable lowercase identifier, unique within the manifest.
- `kind`: one of `result`, `structure`, `table`, `figure`, `note`,
  `reference-context`, or `mesa-envelope`.
- `path`: path relative to the paper root or fixture root.
- `source_task`: originating MESA task or `manual`.
- `status`: `primary`, `supporting`, `exploratory`, `failed`, or `excluded`.
- `provenance`: calculation ID, run ID, or note explaining origin.
- `units`: units for numeric results, or `not_applicable`.
- `claim_role`: `candidate-evidence`, `context`, `method-detail`, or
  `do-not-use`.
- `blockers`: list of missing metadata or empty list.

## Blocking Conditions

Gate 0 blocks if a primary result lacks provenance, units, method identity,
system identity, convergence status, structure identity, or a clear link to the
source artifact. Blocked items must stay in the manifest with explicit blockers;
they must not be silently omitted.

## No Prose Rule

No section prose may be created in Gate 0. The only allowed manuscript output is
state and inventory material under `paper/inputs/`, `paper/logic/`, and
`paper/state/`.
