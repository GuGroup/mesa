---
name: vasp-job
description: Prepare, submit, and track VASP calculations on the SGE HPC login node using the `vasp-job` CLI, including conservative VASP parameter handling. Use when the user wants to run a VASP relaxation/SCF job, queue a job with qsub, choose minimal versus full parameter edits, check job status, list recent jobs, or inspect result files on the cluster.
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
| `vasp-job list [--limit N]` | Recent jobs (default 20), newest first, with summary metadata. |
| `vasp-job show <id>` | Full stored metadata plus live status for one job. |

`<spec>` is a file path, or `-` to read from stdin (`cat spec.yml | vasp-job submit -`).
`<id>` is the `job_uid` (preferred) or the raw SGE `scheduler_id`.

## Job spec

`vasp-job` does not fill in VASP defaults. Choose one of two parameter modes:

- **Minimal edit mode**: Use when the user already provides VASP parameters, an
  INCAR-derived parameter set, or asks to preserve an existing setup. Keep their
  `vasp.parameters` values unchanged unless a value is invalid for the schema or
  the user explicitly asks for a change. Add only required job-spec structure
  (`job_name`, POSCAR reference or inline POSCAR, queue preset) and point out missing risky choices
  instead of silently replacing them.
- **Full explicit mode**: Use when the user asks you to prepare a job from a
  structure without a complete parameter set, or asks for this protocol's
  defaults. Read [`defaults.yaml`](defaults.yaml), take `common`, overlay
  `task.<task>`, apply system-specific overrides, and write the final merged
  values explicitly into `vasp.parameters`.

Example for a `slab` job (common + task.slab, smearing left at the metal default):

```yaml
job_name: co_pt111_001          # letters, numbers, . _ - only (used in paths)
task: slab                      # optional enum recorded in metadata (bulk|slab|freq|static)
project: screening              # optional group; omit or null for a flat layout

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
    ediff: 1.0e-4
    nelm: 1000
    ismear: 1                   # metal slab; gas molecule/insulator -> 0 + sigma 0.05
    sigma: 0.1
    ispin: 1                    # magnetic system -> 2 (+ magmom: [...] per atom)
    ivdw: 12
    isym: 0
    ncore: 8
    lreal: Auto
    lcharg: false
    lwave: false
    kspacing: 0.30              # or set vasp.kpts for a fixed mesh (then drop kspacing)
    kgamma: true
    # --- task.slab ---
    ibrion: 2
    isif: 0
    nsw: 1000
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
- In full explicit mode, assemble parameters from `defaults.yaml`
  (`common` + `task.<task>` + overrides) and write them explicitly. The CLI
  passes `vasp.parameters` to vasp-ase as-is; it does not add or override
  anything.
- Decide the system-dependent ones per job: `ismear`/`sigma` (metal slab vs
  gas-phase molecule/insulator) and `ispin`/`magmom`. If `ispin: 2`, include
  `magmom` (per-atom initial moments).
- `task` is optional but, when present, must be one of `bulk`, `slab`, `freq`, or
  `static`. It is recorded in metadata and helps choose the defaults overlay in
  full explicit mode; the CLI itself does not merge task defaults.
- POSCAR is usually referenced with `structure.path`; relative paths are resolved
  from the spec file's directory. `structure.format` must be `poscar`. You may use
  `structure.content` instead to inline the POSCAR text, but set exactly one of
  `path` or `content`.
- `vasp.parameters` keys are lowercase vasp-ase keywords, not uppercase INCAR.
- k-points: use `kspacing` (default). Set explicit `vasp.kpts` only when the user asks for a fixed mesh or the calculation is clearly a one-point Gamma-only job; then omit `kspacing`/`kgamma`. Do not add top-level `vasp.gamma` for ordinary KSPACING jobs; `vasp.parameters.kgamma` already controls Gamma-centered KSPACING meshes.
- Treat `vasp.parameters.kgamma` and top-level `vasp.gamma` as different
  controls. `kgamma: true` means a Gamma-centered KSPACING mesh; it does not
  select the gamma-only VASP executable.
- Do not set POTCAR / `potcar` (server `vasp_pp_path`), queue internals
  (`pe`/`slots`/`vasp_command`), or `project.root` — server/preset-managed.

Run `vasp-job schema` for accepted top-level fields. The spec you submit (with
your full parameters) is recorded in the job's `input.yml`.

## Queue presets

`queue.preset` selects which SGE submit template is used:

- `auto` picks 48- vs 64-core from current free nodes (`qq`). For the VASP executable, `auto` must choose `gam` only when the spec explicitly has both `vasp.kpts: [1, 1, 1]` and `vasp.gamma: true` for a Gamma-only calculation. Do not infer `gam` from `vasp.parameters.kgamma: true`, from KSPACING, from task type, or from a Gamma-centered multi-point mesh. If uncertain, leave `vasp.gamma` unset and use `std`.
- `preset64std`, `preset64gam`, `preset48std`, `preset48gam` — pin it explicitly.

## Workflow

1. (Optional) Learn the schema: `vasp-job schema`.
2. Write the spec to a file, e.g. `spec.yml`: choose minimal edit mode or full
   explicit mode, set `task` only to `bulk`, `slab`, `freq`, or `static`, and
   point `structure.path` at the POSCAR file (or inline it with `structure.content`).
3. Dry-run: `vasp-job prepare spec.yml`. On success you get
   `{"ok": true, "prepared": true, "job_uid": "...", "remote_dir": "..."}`. Inspect
   `remote_dir` (`INCAR`, `KPOINTS`, `POTCAR`, `submit_vasp.sh`) if the user wants to
   review before submitting.
4. Submit: `vasp-job submit spec.yml` →
   `{"ok": true, "job_uid": "...", "scheduler_id": "123456", "remote_dir": "..."}`.
   Keep the `job_uid` — it is the handle for everything after this.
5. Track: `vasp-job status <job_uid>` for live state, or `vasp-job show <job_uid>`
   for metadata + status. `vasp-job list` shows recent jobs across the account.
6. Results: finished jobs leave output files in `remote_dir` (`OUTCAR`,
   `OSZICAR`, `CONTCAR`, `vasprun.xml`, ...). Read them from there.

A job is done when `status`/`show` reports `finished: true` (`state: finished` for a
clean exit, `state: failed` for a non-zero VASP exit code). `state: unknown` means it
is neither in the queue nor has a completion marker yet — check again shortly.

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
| `Unknown job_uid` | The id is wrong or the job index is on another root — check `vasp-job list`. |
