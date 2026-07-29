# vasp-submit

`vasp-submit` provides the `vasp-job` command for preparing, submitting, and tracking VASP jobs directly on the Mirae SGE login node. It does not use a local API server or SSH proxy. The CLI writes VASP input files with `vasp-ase`, submits `submit_vasp.sh` with `qsub`, and stores lightweight job metadata for later status checks.

## Install On Mirae

Run this from the repository checkout on the Mirae login node:

```bash
cd ~/runners/vasp-submit-linker
CFLAGS="${CFLAGS:-} -std=gnu99" uv tool install --python 3.11 --editable . --constraint constraints.txt --force
```

`--python 3.11` is intentional for Mirae. The CFLAGS prefix keeps Pillow source
builds compatible with compilers that default to pre-C99 mode.

Check the installed command:

```bash
which vasp-job
vasp-job schema
```

## Mirae Environment Setup

Create the runtime config at `~/.config/vasp-submit/hpc-server.yml`:

```yaml
trusted_roots:
  - ~/runners/vasp_run

default_project_root: ~/runners/vasp_run
job_uid_length: 10
job_dir_pattern: "{uuid}"

vasp_pp_path: /home/shared/programs/vasp/vasp_pp/newpot_PBE
vasp_pp_version: null
vasp_ase_env: {}

default_queue:
  scheduler: sge
  preset: auto

queue_status_command: ~/runners/.qq-wrapper
auto_preset:
  prefer: [64, 48]
  node_core_ranges:
    48:
      - [1, 30]
    64:
      - [31, 40]

template_root: ~/runners/vasp-submit-linker
submit_templates:
  preset48gam: templates/sge/preset48gam.sh
  preset48std: templates/sge/preset48std.sh
  preset64gam: templates/sge/preset64gam.sh
  preset64std: templates/sge/preset64std.sh
  # Lightweight/limited-resource preset pinned to node g01 (a6000.q queue,
  # 16 MPI slots). Not part of `auto` selection — pin it explicitly.
  presetg01gam: templates/sge/presetg01gam.sh
  presetg01std: templates/sge/presetg01std.sh
```

Notes:

- `vasp_pp_path` is mapped to `VASP_PP_PATH` only while `vasp-ase` writes inputs.
- `queue_status_command` should print node names in the `n31` style used by the auto preset selector. It may print bare node names or include remaining/free-slot hints such as `n31 remaining=0`.
- `queue.preset: auto` chooses 64-core or 48-core from node availability. If no node is currently free, it defaults to a 48-core preset so SGE can queue the job instead of aborting before `qsub`. It chooses the Gamma-only VASP executable only for explicit `vasp.kpts: [1, 1, 1]` plus `vasp.gamma: true`; ordinary `kspacing` jobs use `vasp_std`.
- `presetg01std` / `presetg01gam` pin the job to node `g01` (`a6000.q` queue, 16 MPI slots) instead of the shared 48/64-core pool. Use this for lightweight/fast-inference test jobs; it is never chosen by `auto` — set it explicitly in `queue.preset`.
- g01 presets are sequentially guarded by `vasp-job submit`: before `qsub`, the CLI locks the configured project root and refuses submission when another indexed `presetg01std` or `presetg01gam` job is still queued/running. Submit the next g01 job only after `vasp-job status <job_uid>` reports `finished` or `failed`.
- VASP/INCAR defaults are not loaded from the server config. The agent skill writes final `vasp.parameters` explicitly into each job spec.

## Job Spec

A minimal lightweight slab relaxation spec (this branch's fast/test defaults,
explicit Gamma-only mesh) looks like this:

```yaml
schema_version: 1
job_name: co_pt111_001
task: slab
project: null

structure:
  format: poscar
  path: POSCAR

vasp:
  kpts: [1, 1, 1]
  gamma: true
  parameters:
    gga: PE
    prec: Low
    encut: 350
    ediff: 5.0e-4
    algo: Fast
    nelm: 80
    ismear: 1
    sigma: 0.20
    ibrion: 2
    nsw: 100
    isif: 2
    ediffg: -0.08
    lreal: Auto
    ncore: 4
    isym: 0
    lwave: false
    lcharg: false

queue:
  preset: presetg01gam
```

`structure.path` is resolved relative to the spec file. This branch's default is always the explicit one-point Gamma-only mesh shown above (`vasp.kpts: [1, 1, 1]` + `vasp.gamma: true`, with `kspacing`/`kgamma` omitted); only switch to a `kspacing` + `kgamma` mesh if the user explicitly asks for denser sampling.

## CLI Usage

```bash
vasp-job schema
vasp-job prepare input.yml
vasp-job submit input.yml
vasp-job status <job_uid_or_scheduler_id>
vasp-job show <job_uid_or_scheduler_id>
vasp-job list --limit 20
```

Preparation-only review and live submission are separate alternatives:

```bash
# Prepare and inspect without submitting.
vasp-job prepare input.yml

# Or, after explicit submission approval, prepare and submit in one command.
vasp-job submit input.yml
```

Do not chain `prepare input.yml` and `submit input.yml` expecting the second
command to reuse the first generated job directory; a spec without an explicit
`job_dir` receives a new job UID each time.

Every command prints one JSON object. On success, `prepare` returns `job_uid` and `remote_dir`; `submit` also returns `scheduler_id`. Keep `job_uid` for later status and metadata lookups.

Prepared and submitted jobs live under:

```text
~/runners/vasp_run/jobs/<job_uid>
```

The generated directory contains files such as `POSCAR`, `INCAR`, `POTCAR`, `submit_vasp.sh`, `input.yml`, and completion markers after the scheduler job exits.

## Development Checks

```bash
PYTHONPATH=src uv run --no-project --with pyyaml python -m unittest discover -s tests -v
```
