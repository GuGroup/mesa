# Calculation Domain Workflow

Use this manual for recipe-backed calculations, VASP-input preparation policy,
UMA relaxation, UMA vibrations, calculation result checks, and reaction-pathway
bookkeeping.

Calculations must be authorized by explicit recipe artifacts.

# Skills

- `relax-uma-trajectory`
- `calculate-uma-vibrational-frequencies`
- `analyze-calculation-results`
- `manage-vasp-jobs`
- `balance-reaction-pathway`

# Test Calculation Policy

The root `workflow.md` is the source of truth for calculation backend policy.
Under the current root policy, the active execution backend is UMA only and UMA
outputs are treated as authoritative for this test project.

For this test project:

- Prepare VASP-compatible input files when useful for interoperability.
- Do not execute or submit VASP jobs unless the project policy changes.
- Do not use `manage-vasp-jobs` to submit calculations in this test. Use it
  only for preparation, dry-run, status inspection, or future policy-enabled
  VASP work.
- Use `relax-uma-trajectory` for structure relaxations, including bulk and
  clean-slab optimization.
- Use `calculate-uma-vibrational-frequencies` for vibrational calculations.
- If local GPU UMA execution is requested, run UMA locally on the GPU node; do
  not submit UMA through qsub unless explicitly required.

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
VASP-compatible inputs when useful, and manifest entries.

# UMA Vibrations

Use `calculate-uma-vibrational-frequencies` for recipe-backed vibrational
frequency or thermochemical correction tasks.

Record:

- input structure and source relaxation;
- displacement or vibrational settings;
- frequencies and thermochemical outputs;
- failed, imaginary, unstable, or caveated modes;
- acceptance state and caveats.

# VASP Job Management

Use `manage-vasp-jobs` only for VASP input preparation, dry-run/status
inspection, or future policy-enabled VASP work during this test. Do not execute
or submit VASP jobs.

When VASP-compatible files are prepared but not run, state that boundary in the
recipe-local manifest.

# Reaction Pathway Bookkeeping

Use `balance-reaction-pathway` when a recipe needs reaction stoichiometry,
state definitions, or balanced pathway metadata for downstream energy or free
energy analysis.

This bookkeeping does not replace actual energy, vibration, or analysis
outputs required by recipes.

# Result Checks

Use `analyze-calculation-results` for relaxation and raw-result sanity checks
where trajectories or optimization outputs exist.

Check and record:

- convergence or termination status;
- final structure availability;
- obvious geometry failures;
- energy and force trends when available;
- warnings, failed jobs, or incomplete outputs;
- whether the artifact is accepted, accepted-with-caveat, exploratory, failed,
  or excluded.

# Execution Manifest

Every calculation recipe that produces or uses artifacts must have:

```text
C###/execution/execution_manifest.json
```

The manifest must record:

- source recipe path and source procedure ID;
- skill or project-local script used;
- command or controller input used, when applicable;
- input artifacts;
- output artifacts;
- validation status;
- acceptance state: `accepted`, `accepted-with-caveat`, `exploratory`,
  `failed`, or `excluded`;
- caveats, unsupported pieces, or policy boundaries.

Do not store execution status in generated `recipe.json` files.
