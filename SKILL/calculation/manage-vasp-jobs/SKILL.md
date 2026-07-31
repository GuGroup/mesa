---
name: manage-vasp-jobs
description: Prepare, submit, and track cost-aware VASP calculations on the SGE HPC login node using the `vasp-job` CLI, including conservative parameter handling and refinement-default actual calculation settings. Use when the user wants to dry-run or run a VASP relaxation/SCF job, queue a job with qsub, choose test/screening/refinement settings, check job status, list recent jobs, or inspect result files on the cluster.
---

For MESA end-to-end use, read `SKILL/calculation/workflow.md` before applying this skill.

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

## Local node-runner compatibility

This skill remains the SGE-per-calculation path. When the requested execution
model is a long-lived 48-core allocation plus direct VASP execution inside that
node, use this skill only through `vasp-job prepare` to create compatible input
folders. Then switch to `run-vasp-local-node` for execution, local queue
draining, and local status checks.

The local runner's 40-rank reserve rule does not apply to this SGE submit path:
`preset48std` and `preset48gam` request and use 48 SGE slots through `$NSLOTS`.

Do not call `vasp-job submit` for a prepared directory that will be consumed by
`run-vasp-local-node`. The local runner writes `.mesa_vasp_local_*` metadata and
also writes `.vasp_submit_finished` / `.vasp_submit_exit_code` compatibility
markers after execution.

`vasp-job prepare`'s `remote_dir` is a server-managed path (`project.root` is
not settable, see Parameter rules), not the MESA `project/<project_name>/`
directory. Before running `run-vasp-local-node`, copy the prepared input files
from `remote_dir` into the calculation's assigned execution directory (the
`P###/calculations/C###/execution/units/E###/` path from
`SKILL/calculation/workflow.md`), and point every local-runner command at that
project-local copy. Do not leave the job directory `run-vasp-local-node`
actually executes in outside the project tree.

### Local-node calculation defaults

`profile.local_node` in [`defaults.yaml`](defaults.yaml) is a fixed, user-set
default for the local-node path (spin off, `vasp_gam`/Gamma-only KPOINTS
`1 1 1`, ENCUT 350, PBE, EDIFF 5e-3, EDIFFG -0.08, POTIM 0.1, IVDW 12, NELM
100, NSW 80, PREC Normal, ALGO Fast, LREAL Auto, NCORE 8 on the 40-rank
allocation). Do not re-derive, tighten, or loosen these values on your own
judgment. Use them as-is except for the two documented overlays below, and
except when the user supplies their own parameter YAML (which always wins
outright, per Calculation policy item 8).

- **Single-point analysis overlay** (`profile.local_node.static_analysis`):
  use for a post-relaxation static job that feeds a descriptor script (e.g.
  `analyze-dband-center`, other PDOS-based analysis). Overlay it on
  `profile.local_node.common` + `task.static`. It only tightens
  SCF-convergence keys (`ediff`, `nelm`, `algo`) and adds DOS output
  (`lorbit: 11`, `lcharg: true`) — it must never change `gga`/`encut`/`ivdw`/
  `kpts`/`ismear`/`sigma` away from the relaxation it is analyzing, so both
  stay at the same level.
- **Small-system overlay** (`profile.local_node.small_system`): use only for a
  bulk unit cell or a gas-phase molecule with fewer than 20 atoms — never for
  slabs. It is moderately tighter (ENCUT 400, PREC Accurate, EDIFF 1e-5,
  EDIFFG -0.03, ALGO Normal, `lreal: false`), still not maximally strict, and
  keeps Gamma-only KPOINTS since the executable (`vasp_gam`) cannot sample a
  real mesh. For molecules (which use inlined parameters, no `task` block;
  see Gas-phase molecule calculations below) apply only the `common` half of
  this overlay.
- **Frequency jobs on a solid** (`task.freq`): before submitting, fix every
  atom belonging to the solid (slab or bulk substrate) with selective
  dynamics (`F F F` in the POSCAR) and leave free only the adsorbate/molecule
  whose vibrations are being computed. This is a structure-preparation step,
  not an INCAR key. Keep `gga`/`encut`/`ivdw`/`kpts` identical to the relax
  job the frequency job follows; only `ibrion`/`nfree`/`potim`/`nsw`/`algo`/
  `ediff` change, per `task.freq` in `defaults.yaml`.

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
   isolated `20 20 21` Å orthorhombic POSCAR. Do not put gas structure generation in
   `build-slab-models`.
8. If the user supplies their own parameter/config YAML (a job spec, a
   `--common`/`extends` file, or an INCAR-derived parameter set), treat every
   value it sets as authoritative and never deviate from it — do not tighten,
   loosen, or "correct" a user-supplied value toward `defaults.yaml`. Only fill
   in fields the user's file leaves unset, using the profiles below. This is
   `defaults.yaml`'s job spec — do not restate specific parameter values
   (encut, core/rank counts, k-point settings, etc.) in this skill's
   frontmatter `description`, in `run-vasp-local-node`, or in `workflow.md`;
   keep the numbers in one place (`defaults.yaml`) and reference it by name.

If a user asks to "run VASP" on many structures, first create/spec dry-runs and
ask which few structures should be submitted. Do not silently submit a large
job matrix. If the user wants a broad low-cost comparison, ask or record that
screening mode is being used explicitly.

### DFT test policy

When the user explicitly asks for a DFT test, lightweight test run, g01 test, or
minimum VASP sanity run, use **DFT test explicit mode** instead of refinement or
screening mode:

- Use only `profile.dft_test` from [`defaults.yaml`](defaults.yaml), or the
  reusable [`common_dft_test.yml`](common_dft_test.yml). Do not merge the
  top-level refinement defaults and do not use `common_refinement.yml`.
- Keep DFT-test INCAR minimal and fast. Do not add refinement/accuracy helpers
  such as `lasph`, `addgrid`, or `ivdw` unless the user explicitly asks for
  them.
- Set explicit Gamma-only sampling with `vasp.kpts: [1, 1, 1]` and
  `vasp.gamma: true`; omit `vasp.parameters.kspacing` and
  `vasp.parameters.kgamma`.
- Use `queue.preset: presetg018gam` for Gamma-only test specs when g01 already
  has noticeable load. Use `presetg01gam` only when the user asks for 16 slots.
  Use `presetg018std` / `presetg01std` only if the spec is not Gamma-only.
- g01 submissions are sequential: the `presetg01*` templates request
  `a6000.q`, `hostname=g01`, and either 8 or 16 MPI slots, and `vasp-job submit` refuses a
  second indexed g01 preset job while another g01 preset job is still queued or
  running. Submit the next g01 job only after `vasp-job status <job_uid>` reports
  `finished` or `failed`.
- Report DFT-test jobs as lightweight sanity/test calculations, not final
  adsorption/surface energy evidence.

## Job spec

`vasp-job` does not fill in VASP defaults. Choose one of four parameter modes:

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
- **DFT test explicit mode**: Use only when the user asks for DFT test or g01
  lightweight test behavior. Read `profile.dft_test.common` and
  `profile.dft_test.task.<task>` from `defaults.yaml`, set
  `vasp.kpts: [1, 1, 1]`, set `vasp.gamma: true`, omit `kspacing`/`kgamma`, apply
  system-specific overrides, and set `queue.preset: presetg018gam` unless the
  calculation is explicitly non-Gamma-only.
- **Local-node explicit mode**: Use only when the prepared folder is meant for
  `run-vasp-local-node` (Gamma-only `vasp_gam` on a 40-rank local allocation),
  never for `vasp-job submit`. Read `profile.local_node.common` and
  `profile.local_node.task.<task>` from `defaults.yaml`; overlay
  `profile.local_node.static_analysis` only for a post-relaxation single-point
  job at the same level as its relax (e.g. d-band center, PDOS); overlay
  `profile.local_node.small_system` only for bulk/molecule systems with fewer
  than 20 atoms; apply system-specific overrides; and write the final merged
  values explicitly into `vasp.parameters`. Always set `vasp.kpts: [1, 1, 1]`
  and `vasp.gamma: true`, and omit `kspacing`/`kgamma`. These are fixed
  user-set defaults — do not tighten or loosen them beyond the documented
  overlays. If the user supplies their own parameter YAML, it overrides this
  profile entirely (see Calculation policy).

### Reuse common parameters (`extends` / `--common`)

To avoid re-typing the ~16 shared `common` keys for every job, the CLI merges a
reusable common spec file before the job spec (the job spec always wins on
conflict; merge is deep/recursive). This is the preferred way to run many jobs
in one project without hand-assembly drift.

- Bundled reusable blocks: [`common_refinement.yml`](common_refinement.yml),
  [`common_screening.yml`](common_screening.yml), and
  [`common_dft_test.yml`](common_dft_test.yml). Each carries only the
  task-agnostic `common` block for its mode.
- External file (recommended): use the common file for the selected mode, e.g.
  `vasp-job prepare spec.yml --common <path>/common_dft_test.yml` for DFT tests
  or `vasp-job prepare spec.yml --common <path>/common_refinement.yml` for
  refinement jobs.
  `--common` accepts an absolute path or a path relative to the current
  directory.
- In-spec: add the selected mode's common file to `extends`, such as
  `extends: common_dft_test.yml` for DFT tests or
  `extends: common_refinement.yml` for refinement. `extends` is a relative path
  (or list of relative paths) resolved **under the spec file's directory** —
  copy the common file next to the spec first. A list merges left to right
  (later wins), then the spec wins over all.

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

Example for a lightweight DFT-test `slab` job on g01:

```yaml
extends: common_dft_test.yml
job_name: co_pt111_test_001
task: slab
project: dft_test
structure: { format: poscar, path: POSCAR }
vasp:
  kpts: [1, 1, 1]
  gamma: true
  parameters:
    # task.slab from profile.dft_test.task.slab
    ibrion: 2
    isif: 2
    nsw: 100
    ediffg: -8.0e-2
    potim: 0.1
queue:
  preset: presetg018gam
```

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
- In DFT test explicit mode, assemble parameters only from
  `profile.dft_test.common` + `profile.dft_test.task.<task>`, set the top-level
  `vasp.kpts`/`vasp.gamma` from `profile.dft_test.vasp`, and record that the job
  is lightweight test evidence only.
- Decide `ismear`/`sigma` per job (metal slab vs gas-phase molecule/insulator
  differ by physical state). Decide `ispin`/`magmom` once per project instead
  of per job: check whether any structure in the project has a magnetic
  element (Fe/Co/Ni/Mn/Cr/...), then use that same `ispin` value (2 + `magmom`
  per-atom initial moments, or 1 with no `magmom`) for every slab/bulk
  calculation in the project — do not decide it structure-by-structure, since
  mixed `ispin` values break energy comparability across the project. This
  project-wide rule does not apply to the gas-phase molecule `spin_reference`
  exception below.
- `task` is optional but, when present, must be one of `bulk`, `slab`, `freq`, or
  `static`. It is recorded in metadata and helps choose the defaults overlay in
  screening/refinement explicit modes; the CLI itself does not merge task
  defaults.
- POSCAR is usually referenced with `structure.path`; relative paths are resolved
  from the spec file's directory. `structure.format` must be `poscar`. You may use
  `structure.content` instead to inline the POSCAR text, but set exactly one of
  `path` or `content`.
- `vasp.parameters` keys are lowercase vasp-ase keywords, not uppercase INCAR.
- k-points: use `kspacing` by default for refinement/screening. Both actual calculation and explicit
  screening use `kspacing: 0.30` (screening saves cost via encut/ediff/nelm/nsw,
  not by coarsening k-points). Set explicit `vasp.kpts` only when the user asks
  for a fixed mesh or the calculation is clearly a one-point Gamma-only job; then omit
  `kspacing`/`kgamma`. Do not add top-level `vasp.gamma` for ordinary KSPACING
  jobs; `vasp.parameters.kgamma` already controls Gamma-centered KSPACING
  meshes.
- DFT test mode is always explicit one-point Gamma-only unless the user
  explicitly asks otherwise: set `vasp.kpts: [1, 1, 1]`, set
  `vasp.gamma: true`, and omit `kspacing`/`kgamma`.
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

- `auto` picks 48- vs 64-core from current free/remaining nodes (`qq`). If no node is currently free, `auto` defaults to a 48-core preset so SGE can queue the job instead of aborting before `qsub`. For the VASP executable, `auto` must choose `gam` only when the spec explicitly has both `vasp.kpts: [1, 1, 1]` and `vasp.gamma: true` for a Gamma-only calculation. Do not infer `gam` from `vasp.parameters.kgamma: true`, from KSPACING, from task type, or from a Gamma-centered multi-point mesh. If uncertain, leave `vasp.gamma` unset and use `std`.
- `preset64std`, `preset64gam`, `preset48std`, `preset48gam` — pin it explicitly.
- `presetg018std`, `presetg018gam` — pin to SGE `a6000.q`, `hostname=g01`, and
  `mpi_8 8`. Prefer these for quick DFT tests when g01 has existing load.
- `presetg01std`, `presetg01gam` — pin to SGE `a6000.q`, `hostname=g01`, and
  `mpi_16 16`. Use only when the user asks for 16 slots. These g01 presets are
  not selected by `auto`; set them explicitly for DFT tests. `vasp-job submit`
  enforces one active indexed g01 preset job at a time.

All SGE submit templates load `vasp/6.3.2-vtst-vaspsol-beef-intel` and then run
`mpirun -machinefile $TMPDIR/machines -n $NSLOTS vasp_std` or `vasp_gam`; the
`std`/`gam` choice is controlled by the selected preset.

## Workflow

1. (Optional) Learn the schema: `vasp-job schema`.
2. Ensure upstream gates are complete: selected slab termination, selected
   adsorption site/intermediate, atom count, fixed atoms, and structure
   validation. Do not use VASP as the first filter over a large generated set.
3. Write the spec to a file, e.g. `spec.yml`: choose minimal edit, DFT test
   explicit for requested g01/lightweight tests, refinement explicit by default
   for actual calculations, or screening explicit only when the user asked for
   quick screening/comparison. Set `task` only to `bulk`, `slab`, `freq`, or
   `static`, and point `structure.path` at the POSCAR file (or inline it with
   `structure.content`).
4. Dry-run: `vasp-job prepare spec.yml`. On success you get
   `{"ok": true, "prepared": true, "job_uid": "...", "remote_dir": "..."}`. Inspect
   `remote_dir` (`INCAR`, `KPOINTS`, `POTCAR`, `submit_vasp.sh`) if the user wants to
   review before submitting.
5. Submit only after the user has selected the small candidate set. For g01
   DFT tests, submit one spec at a time and wait for the previous g01 job to
   finish or fail before submitting the next:
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
- When `finished`, run `analyze-relaxation-results`
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
| `Unknown queue.preset` / `No free 48/64 nodes` | Use a valid preset, retry `auto` later when nodes free up, or reinstall/update `vasp-job` if `presetg01std`/`presetg01gam` is missing from `vasp-job schema`. |
| `g01 sequential policy blocked submission` | A `presetg01*` job is still queued/running. Wait for `vasp-job status <job_uid>` to report `finished` or `failed`, then submit the next g01 test job. |
| `vasp-ase did not generate required file` | Server-side POTCAR/`vasp_pp_path` issue — report it to the user. |
| `Unknown job_uid` | The id is wrong or the job index is on another root — check `vasp-job list`; use `vasp-job list --verbose` if you need roots or directories. |
