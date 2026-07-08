---
name: manage-vasp-jobs
description: Prepare, submit, and track cost-aware VASP calculations on the SGE HPC login node using the `vasp-job` CLI, including conservative parameter handling, refinement-default actual calculation settings, and explicit quick-screening settings. Use when the user wants to dry-run or run a VASP relaxation/SCF job, queue a job with qsub, choose screening versus refinement settings, check job status, list recent jobs, or inspect result files on the cluster.
---

# vasp-job

`vasp-job` is a globally installed CLI (via `uv tool`) that runs on the HPC login
node. It turns one job spec (YAML or JSON) into VASP input files
(`POSCAR`, `INCAR`, `KPOINTS`, `POTCAR`, `submit_vasp.sh`), submits them with SGE
`qsub`, and tracks the job afterwards. There is no API or SSH hop — you call the
command directly. The job spec may reference an existing POSCAR with
`structure.path`; relative paths are resolved from the spec file's directory.

Every command prints a single JSON object to stdout. Read that JSON to decide
the next step. On error you get `{"ok": false, "error": "..."}` and a non-zero exit
code — read `error`, fix the spec, and retry.

## Commands

| Command | What it does |
| --- | --- |
| `vasp-job schema` | Print the accepted job-spec JSON schema. Run this first if unsure of the input shape. |
| `vasp-job prepare <spec>` | Write input files only. No qsub. Use to dry-run and inspect before submitting. |
| `vasp-job submit <spec>` | Write input files and submit with `qsub`. Returns `job_uid` and `scheduler_id`. |
| `vasp-job status <id>` | Live SGE status for one job (`running` / `finished` / `failed` / `unknown`). |
| `vasp-job list [--limit N]` | Recent jobs (default 20), newest first, with compact id/name/state fields. |
| `vasp-job list --verbose` | Recent jobs with timestamps, preset, project, and `remote_dir`. Use only when those details are needed. |
| `vasp-job show <id>` | Full stored metadata plus live status for one job. |

`<spec>` is a file path, or `-` to read from stdin (`cat spec.yml | vasp-job submit -`).
`<id>` is the `job_uid` (preferred) or the raw SGE `scheduler_id`.

## Calculation policy

Actual VASP calculations default to **refinement-oriented settings**, not light
screening. VASP jobs are expensive and must come after structure-generation
gates:

1. Run slab termination screening first when a slab has multiple plausible
   terminations, polar directions, asymmetric top/bottom layers, or
   non-stoichiometric options.
2. Run adsorption-site/adsorbate enumeration outside VASP first. Do not submit a
   VASP job for every generated site or every reaction intermediate by default.
3. Submit VASP only for a small selected set of structures. For broad
   exploration, prefer structure generation plus metadata/geometry validation
   first, then `vasp-job prepare` dry-runs for the selected candidates.
4. Use the top-level values in [`defaults.yaml`](defaults.yaml) as the default
   refinement profile for actual calculations.
5. Use `profile.screening` from `defaults.yaml` only when the user explicitly
   asks for screening, quick comparison, rough triage, or low-cost geometry
   sanity checks. Report that the job is a screening job and should not be used
   as final adsorption/surface energy evidence.
6. Never run `freq` by default. Frequency jobs are only for selected relaxed
   endpoints and require an explicit user request.
7. For gas-phase molecules, use `build-gas-phase-models` first to create the
   isolated 15 Å-box POSCAR. Do not put gas structure generation in
   `build-slab-models`.

If a user asks to "run VASP" on many structures, first create/spec dry-runs and
ask which few structures should be submitted. Do not silently submit a large
job matrix. If the user wants a broad low-cost comparison, ask or record that
screening mode is being used explicitly.

## Job spec

`vasp-job` does not fill in VASP defaults. Choose one of three parameter modes:

- **Minimal edit mode**: Use when the user already provides VASP parameters, an
  INCAR-derived parameter set, or asks to preserve an existing setup. Keep their
  `vasp.parameters` values unchanged unless a value is invalid for the schema or
  the user explicitly asks for a change. Add only required job-spec structure
  (`job_name`, POSCAR reference or inline POSCAR, queue preset) and point out missing risky choices
  instead of silently replacing them.
- **Refinement explicit mode (default for actual calculations)**: Use when the
  user asks to prepare or run a VASP calculation from a selected structure
  without a complete parameter set. Read [`defaults.yaml`](defaults.yaml), take
  top-level `common`, overlay top-level `task.<task>`, apply system-specific
  overrides, and write the final merged values explicitly into
  `vasp.parameters`.
- **Screening explicit mode**: Use only when the user asks for screening, quick
  comparison, rough triage, or low-cost geometry sanity checks. Read
  top-level `common` and `task.<task>`, overlay `profile.screening.common` and
  `profile.screening.task.<task>`, apply system-specific overrides, and write
  the final merged values explicitly into `vasp.parameters`.

### Reuse common parameters (`extends` / `--common`)

To avoid re-typing the ~16 shared `common` keys for every job, the CLI merges a
reusable common spec file before the job spec (the job spec always wins on
conflict; merge is deep/recursive). This is the preferred way to run many jobs
in one project without hand-assembly drift.

- Bundled reusable blocks: [`common_refinement.yml`](common_refinement.yml) and
  [`common_screening.yml`](common_screening.yml). Each carries only the
  task-agnostic `common` block.
- External file (recommended): `vasp-job prepare spec.yml --common <path>/common_refinement.yml`.
  `--common` accepts an absolute path or a path relative to the current
  directory.
- In-spec: add `extends: common_refinement.yml` to the job spec. `extends` is a
  relative path (or list of relative paths) resolved **under the spec file's
  directory** — copy the common file next to the spec first. A list merges left
  to right (later wins), then the spec wins over all.

With reuse, the job spec only needs `job_name`, `task`, `structure`, the
`task.<task>` parameters, system overrides (`ismear`/`sigma`,
`ispin`/`magmom`), and `queue`:

```yaml
extends: common_refinement.yml   # or pass --common on the CLI
job_name: co_pt111_001
task: slab
structure: { format: poscar, path: POSCAR }
vasp:
  parameters:                    # task.slab + system overrides only
    ibrion: 2
    isif: 0
    nsw: 300
    ediffg: -5.0e-2
    potim: 0.1
    algo: Fast
queue: { preset: auto }
```

The preserved input record (`input_specs/*.yml`) stores the fully merged spec,
so a reused job remains self-contained and reproducible.

Example for a default refined `slab` job (top-level common + task.slab, smearing
left at the metal default):

```yaml
job_name: co_pt111_001          # letters, numbers, . _ - only (used in paths)
task: slab                      # optional enum recorded in metadata (bulk|slab|freq|static)
project: refinement             # optional group; omit or null for a flat layout

structure:
  format: poscar
  path: POSCAR                   # relative to this spec file; or use content: | inline

vasp:
  # Omit gamma unless this is explicitly a Gamma-only calculation; see below.
  parameters:                   # lowercase vasp-ase keywords, not uppercase INCAR tags
    # --- common (from defaults.yaml) ---
    gga: RP
    prec: Normal
    encut: 400
    ediff: 1.0e-5
    nelm: 200
    ismear: 1                   # metal slab; gas molecule/insulator -> 0 + sigma 0.05
    sigma: 0.1
    ispin: 1                    # magnetic system -> 2 (+ magmom: [...] per atom)
    ivdw: 12
    isym: 0
    ncore: 8
    lreal: Auto
    lcharg: false
    lwave: false
    kspacing: 0.30              # refinement default
    kgamma: true
    # --- task.slab ---
    ibrion: 2
    isif: 0
    nsw: 300
    ediffg: -5.0e-2
    potim: 0.1
    algo: Fast

queue:
  preset: auto                  # see "Queue presets" below
```

Parameter rules:

- In minimal edit mode, preserve user-supplied VASP parameters. Do not rewrite
  smearing, spin, k-points, convergence, vdW, or relaxation controls just because
  they differ from `defaults.yaml`; warn or ask only when the choice is clearly
  inconsistent with the requested calculation.
- In refinement explicit mode, assemble parameters from top-level
  `defaults.yaml` (`common` + `task.<task>` + overrides) and write them
  explicitly. The CLI passes `vasp.parameters` to vasp-ase as-is; it does not
  add or override anything.
- In screening explicit mode, assemble parameters from
  top-level `common` + top-level `task.<task>` with
  `profile.screening.common` + `profile.screening.task.<task>` overlaid, then
  apply system-specific overrides. Record in the user-facing response that the
  job is a screening job and is not final-quality evidence.
- Decide the system-dependent ones per job: `ismear`/`sigma` (metal slab vs
  gas-phase molecule/insulator) and `ispin`/`magmom`. If `ispin: 2`, include
  `magmom` (per-atom initial moments).
- `task` is optional but, when present, must be one of `bulk`, `slab`, `freq`, or
  `static`. It is recorded in metadata and helps choose the defaults overlay in
  screening/refinement explicit modes; the CLI itself does not merge task
  defaults.
- POSCAR is usually referenced with `structure.path`; relative paths are resolved
  from the spec file's directory. `structure.format` must be `poscar`. You may use
  `structure.content` instead to inline the POSCAR text, but set exactly one of
  `path` or `content`.
- `vasp.parameters` keys are lowercase vasp-ase keywords, not uppercase INCAR.
- k-points: use `kspacing` by default. Both actual calculation and explicit
  screening use `kspacing: 0.30` (screening saves cost via encut/ediff/nelm/nsw,
  not by coarsening k-points). Set explicit `vasp.kpts` only when the user asks
  for a fixed mesh or the calculation is clearly a one-point Gamma-only job; then omit
  `kspacing`/`kgamma`. Do not add top-level `vasp.gamma` for ordinary KSPACING
  jobs; `vasp.parameters.kgamma` already controls Gamma-centered KSPACING
  meshes.
- Treat `vasp.parameters.kgamma` and top-level `vasp.gamma` as different
  controls. `kgamma: true` means a Gamma-centered KSPACING mesh; it does not
  select the gamma-only VASP executable.
- Do not set POTCAR / `potcar` (server `vasp_pp_path`), queue internals
  (`pe`/`slots`/`vasp_command`), or `project.root` — server/preset-managed.

Run `vasp-job schema` for accepted top-level fields. The spec you submit (with
your full parameters) is recorded in the job's `input.yml`.

## Gas-phase molecule calculations

Use this section only after `build-gas-phase-models` produced a gas molecule
POSCAR and metadata.

- For gas molecule geometry optimization, omit `task` until the CLI has a
  dedicated gas-relax task, and write the relaxation parameters explicitly.
  Do not label gas relaxation as `task: slab`.
- For gas single-point energy, use `task: static`.
- For gas frequency, use `task: freq`, only after a selected relaxed endpoint
  exists and the user explicitly asks for frequency.
- Use Gamma-only sampling: set `vasp.kpts: [1, 1, 1]` and `vasp.gamma: true`;
  omit `kspacing` and `vasp.parameters.kgamma` for that job.
- Use molecule/insulator smearing: `ismear: 0`, `sigma: 0.05`.
- Spin: read the `spin_reference` block in the gas metadata from
  `build-gas-phase-models`. Apply its `recommended_ispin` and, when
  `recommended_ispin: 2`, set `nupdown: <recommended_nupdown>` (locks the
  multiplicity for the isolated molecule) and an initial `magmom`. This is the
  one place spin IS applied from upstream metadata — e.g. O2→ispin 2/nupdown 2,
  NO→ispin 2/nupdown 1. In minimal edit mode preserve explicit user-supplied
  `ispin`/`magmom`/`nupdown` instead. Never infer charge.
- Dipole: if the gas metadata `dipole_hint.likely_polar` is true, set
  `ldipol: true` and `idipol: 4` for the molecule-in-a-box job.

Example gas relaxation spec:

```yaml
schema_version: 1
job_name: co2_gas_relax_001
project: gas_refs

structure:
  format: poscar
  path: CO2_gas_POSCAR.vasp

vasp:
  kpts: [1, 1, 1]
  gamma: true
  parameters:
    gga: RP
    prec: Normal
    encut: 400
    ediff: 1.0e-5
    nelm: 200
    ismear: 0
    sigma: 0.05
    ispin: 1
    ivdw: 12
    isym: 0
    ncore: 8
    lreal: Auto
    lcharg: false
    lwave: false
    ibrion: 2
    isif: 0
    nsw: 300
    ediffg: -5.0e-2
    potim: 0.1
    algo: Fast

queue:
  preset: auto
```

Example gas frequency spec after relaxation:

```yaml
schema_version: 1
job_name: co2_gas_freq_001
task: freq
project: gas_refs

structure:
  format: poscar
  path: CONTCAR

vasp:
  kpts: [1, 1, 1]
  gamma: true
  parameters:
    gga: RP
    prec: Normal
    encut: 400
    ediff: 1.0e-6
    nelm: 200
    ismear: 0
    sigma: 0.05
    ispin: 1
    ivdw: 12
    isym: 0
    ncore: 8
    lreal: Auto
    lcharg: false
    lwave: false
    ibrion: 5
    nfree: 2
    potim: 0.015
    nsw: 1
    isif: 0
    algo: Normal

queue:
  preset: auto
```

## Queue presets

`queue.preset` selects which SGE submit template is used:

- `auto` picks 48- vs 64-core from current free nodes (`qq`). For the VASP executable, `auto` must choose `gam` only when the spec explicitly has both `vasp.kpts: [1, 1, 1]` and `vasp.gamma: true` for a Gamma-only calculation. Do not infer `gam` from `vasp.parameters.kgamma: true`, from KSPACING, from task type, or from a Gamma-centered multi-point mesh. If uncertain, leave `vasp.gamma` unset and use `std`.
- `preset64std`, `preset64gam`, `preset48std`, `preset48gam` — pin it explicitly.

## Workflow

1. (Optional) Learn the schema: `vasp-job schema`.
2. Ensure upstream gates are complete: selected slab termination, selected
   adsorption site/intermediate, atom count, fixed atoms, and structure
   validation. Do not use VASP as the first filter over a large generated set.
3. Write the spec to a file, e.g. `spec.yml`: choose minimal edit, refinement
   explicit by default for actual calculations, or screening explicit only when
   the user asked for quick screening/comparison. Set `task` only to `bulk`,
   `slab`, `freq`, or `static`, and point `structure.path` at the POSCAR file
   (or inline it with `structure.content`).
4. Dry-run: `vasp-job prepare spec.yml`. On success you get
   `{"ok": true, "prepared": true, "job_uid": "...", "remote_dir": "..."}`. Inspect
   `remote_dir` (`INCAR`, `KPOINTS`, `POTCAR`, `submit_vasp.sh`) if the user wants to
   review before submitting.
5. Submit only after the user has selected the small candidate set:
   `vasp-job submit spec.yml` →
   `{"ok": true, "job_uid": "...", "scheduler_id": "123456", "remote_dir": "..."}`.
   Keep the `job_uid` — it is the handle for everything after this.
6. Track: `vasp-job status <job_uid>` for live state, or `vasp-job show <job_uid>`
   for metadata + status. `vasp-job list` is intentionally compact; use
   `vasp-job list --verbose` only when timestamps, preset, project, or `remote_dir`
   are needed.
7. Results: finished jobs leave output files in `remote_dir` (`OUTCAR`,
   `OSZICAR`, `CONTCAR`, `vasprun.xml`, ...). Read them from there.

A job is done when `status`/`show` reports `finished: true` (`state: finished` for a
clean exit, `state: failed` for a non-zero VASP exit code). `state: unknown` means it
is neither in the queue nor has a completion marker yet — check again shortly.

## Unattended polling, restart, and recovery

For hands-off operation, do not assume one submit equals one converged result.
Poll until done, then verify and recover automatically.

### Polling
- After submit, poll `vasp-job status <job_uid>` with **exponential backoff**
  (e.g. 60s → 120s → 240s, capped ~600s) up to a max wall time, instead of a
  fixed tight loop.
- `state: unknown` right after submit is normal — re-check after a short delay;
  only treat it as a problem if it persists across several polls with no
  `remote_dir` outputs appearing.

### Verify, then gate
- When `finished`, run the calculation-result-analyzer (`TASK_CALCULATION_RESULT_ANALYZER`)
  on `remote_dir` and read its `verdict`:
  - `pass` → accept the endpoint, continue the workflow.
  - `warn` → accept only with the recorded caveat (inspect overlay if a human is
    available); for fully unattended runs, treat a convergence-related `warn`
    like `fail`.
  - `fail` → run the recovery step below.

### Recovery (bounded auto-restart)
Classify the failure and act, capping restarts (default 3) per structure:

```bash
mamba run -n modeling python scripts/diagnose_vasp_failure.py --dir <remote_dir> --max-retries 3 --retry-count <n>
```

Map `recommended_action` to a new job spec, then `vasp-job submit` it:

| `recommended_action` | What to do |
| --- | --- |
| `continue_from_contcar` | New spec, `structure.path: CONTCAR` from `remote_dir`, same params (raise `nsw` if it was the limiter). |
| `continue_from_contcar_algo_normal` | Continue from `CONTCAR` and set `algo: Normal` (or `All`) for electronic non-convergence (NELM hit). |
| `continue_from_contcar_reduce_potim` / `restart_reduce_potim` | Restart with smaller `potim` (e.g. 0.05) and `algo: Normal` (ZBRENT line-search failure). |
| `restart_algo_normal` / `restart_clean` | Resubmit from the original POSCAR with the adjusted control. |
| `inspect_structure` | Do NOT blindly resubmit (ZPOTRF/atoms-too-close, no progress); re-check the structure/min-distance first. |
| `escalate_drop_candidate` | Retry budget exhausted — stop retrying, mark the candidate failed, and move on. |

Always pass the running `--retry-count` so the helper escalates instead of
looping forever. Reuse common parameters via `extends` (above) so a restart spec
differs from the original only by `structure.path` and the few recovery
overrides.

## Common errors

| `error` contains | Fix |
| --- | --- |
| `task must be one of` | Use `task: bulk\|slab\|freq\|static` (or omit it). |
| `top-level potcar is not supported` | Remove `potcar`; configure via `vasp.xc` / `vasp.parameters`. |
| `queue.pe is managed by ...` (or `slots`, `vasp_command`) | Leave only `preset` / `submit` under `queue`. |
| `structure.format must be poscar` | Set `structure.format: poscar`. |
| `structure must set exactly one of content or path` | Use either `structure.path: POSCAR` or inline POSCAR text in `structure.content`, not both. |
| `structure.path not found` | Check the POSCAR path relative to the spec file directory. |
| `vasp.parameters must be a mapping` | `parameters` is a mapping of lowercase keys. |
| `job_name must contain only ...` | Use letters, numbers, `.`, `_`, `-` only. |
| `Unknown queue.preset` / `No free 48/64 nodes` | Use a valid preset, or retry `auto` later when nodes free up. |
| `vasp-ase did not generate required file` | Server-side POTCAR/`vasp_pp_path` issue — report it to the user. |
| `Unknown job_uid` | The id is wrong or the job index is on another root — check `vasp-job list`; use `vasp-job list --verbose` if you need roots or directories. |
