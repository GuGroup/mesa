# Calculation Domain Workflow

Use this manual for recipe-backed calculations, active backend execution,
calculation result checks, and reaction-pathway bookkeeping. The active project
may be UMA/MLIP-only, VASP-only, or another policy explicitly defined by the
project profile.

Calculations must be authorized by explicit recipe artifacts.

# Skills

- `relax-uma-trajectory`
- `calculate-uma-vibrational-frequencies`
- `analyze-relaxation-results`
- `manage-vasp-jobs`
- `balance-reaction-pathway`

# Calculation Policy

The active `project/<project_name>/project_profile.md` is the source of truth
for calculation backend policy. Do not restate or override the active backend
here. Before running calculation skills, read the project profile and apply its
backend, submission, scheduler, artifact-generation, and acceptance rules.

Do not prepare VASP-compatible files by default. Prepare them only when the
active policy allows VASP-related artifacts and a recipe, interoperability
need, or user instruction specifically calls for them. In a UMA/MLIP-only
project, use UMA skills for evidence-producing calculations and do not create
VASP job folders unless the project policy explicitly permits input-only
interoperability artifacts.

# Entry Requirements

Before running a calculation, confirm:

- the selected strategy has an explicit recipe directory;
- `execution_plan.json` exists and contains the execution unit;
- the calculation is tied to a specific `P###/C###/recipe.json`;
- required structures and prior artifacts exist or are explicitly recorded as
  missing;
- the calculation method and output intent match the recipe.

Do not interpret strategy procedures ad hoc when a recipe exists.

# UMA Relaxation

Use `relax-uma-trajectory` for UMA-backed relaxation or trajectory tasks
requested by a recipe.

Select the skill or script at execution time, but use the execution unit's
assigned `execution_dir` as its work directory. Never invent or substitute
another output root. Process `execution_units` in their listed topological order
and start a unit only after its `depends_on` artifacts exist.

Single-consumer units use:

```text
P###/calculations/C###/execution/units/E###/
```

Multi-consumer units use:

```text
<strategy_id>_explicit_recipe/shared_execution/E###/
```

Include relaxed structures, trajectories, logs, inputs, generated
backend-specific inputs or interoperability artifacts only when policy permits
them, and manifest entries.

# UMA Vibrations

Use `calculate-uma-vibrational-frequencies` for recipe-backed vibrational
frequency or thermochemical correction tasks.

Record:

- input structure and source relaxation;
- displacement or vibrational settings;
- frequencies and thermochemical outputs;
- failed, imaginary, unstable, or caveated modes;
- acceptance state and caveats.

# Backend-Specific Job Management

Use `manage-vasp-jobs` only when the active project profile allows VASP
preparation, dry-run/status inspection, or execution. If the active project is
UMA/MLIP-only and does not allow VASP artifacts, do not use `manage-vasp-jobs`
and do not call the `vasp-job` CLI.

When backend-specific files are prepared but not run, state that boundary in
the recipe-local manifest. Examples include "UMA relaxation only; no VASP
input generated" or "VASP input prepared for interoperability only; no VASP
execution".

# Reaction Pathway Bookkeeping

Use `balance-reaction-pathway` when a recipe needs reaction stoichiometry,
state definitions, or balanced pathway metadata for downstream energy or free
energy analysis.

This bookkeeping does not replace actual energy, vibration, or analysis
outputs required by recipes.

# Result Checks

Use `analyze-relaxation-results` for relaxation and raw-result sanity checks
where trajectories or optimization outputs exist.

Check and record:

- convergence or termination status;
- final structure availability;
- obvious geometry failures;
- energy and force trends when available;
- warnings, failed jobs, or incomplete outputs;
- whether the artifact is accepted, accepted-with-caveat, exploratory, failed,
  or excluded.

For batch analysis, do not summarize `warn` endpoints only by count. Build a
warning triage artifact with warning classes, affected endpoint IDs, visual
review status, and the downstream decision for each class. User-facing progress
updates should stay compact: counts, top warning classes, failed IDs, and paths
to summary/triage files. Keep full analyzer JSON and stdout/stderr in files.

# Execution Manifest

After each E-level execution completes or fails, use
`write-execution-manifest`. After E-level diagnosis and repair terminate for a
C recipe, use `write-calculation-manifest`. Every calculation recipe that
produces or uses artifacts must have:

```text
C###/execution/execution_manifest.json
C###/execution/units/E###/execution_manifest.json
```

For multi-consumer units, place the E-level manifest at
`<strategy_id>_explicit_recipe/shared_execution/E###/execution_manifest.json`.
Repair attempts use sibling `E###-R1/` and `E###-R2/` directories. Keep the
C-level manifest as the factual aggregation of terminal E attempts.

Follow the root workflow's factual manifest contract. Keep diagnosis,
acceptance, scientific caveats, exclusions, and repair decisions in separate
artifacts. Do not store execution status in generated `recipe.json` files.
