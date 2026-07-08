# vasp-submit

`vasp-submit` provides the `vasp-job` command for preparing, submitting, and tracking VASP jobs directly on the Mirae SGE login node. It does not use a local API server or SSH proxy. The CLI writes VASP input files with `vasp-ase`, submits `submit_vasp.sh` with `qsub`, and stores lightweight job metadata for later status checks.

## Install On Mirae

Run this from the repository checkout on the Mirae login node:

```bash
cd ~/runners/vasp-submit-linker
uv tool install --python 3.11 . --constraint constraints.txt --force
```

`--python 3.11` is intentional for Mirae: it keeps the scientific Python stack on available wheels and avoids source builds that require newer system compilers.

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
```

Notes:

- `vasp_pp_path` is mapped to `VASP_PP_PATH` only while `vasp-ase` writes inputs.
- `queue_status_command` should print node names in the `n31` style used by the auto preset selector. It may print bare node names or include remaining/free-slot hints such as `n31 remaining=0`.
- `queue.preset: auto` chooses 64-core or 48-core from node availability. If no node is currently free, it defaults to a 48-core preset so SGE can queue the job instead of aborting before `qsub`. It chooses the Gamma-only VASP executable only for explicit `vasp.kpts: [1, 1, 1]` plus `vasp.gamma: true`; ordinary `kspacing` jobs use `vasp_std`.
- VASP/INCAR defaults are not loaded from the server config. The agent skill writes final `vasp.parameters` explicitly into each job spec.

## Job Spec

A minimal KSPACING-based bulk relaxation spec looks like this:

```yaml
schema_version: 1
job_name: si_bulk_001
task: bulk
project: null

structure:
  format: poscar
  path: POSCAR

vasp:
  parameters:
    gga: RP
    prec: Normal
    encut: 400
    ediff: 1.0e-4
    nelm: 1000
    ismear: 0
    sigma: 0.05
    ispin: 1
    ivdw: 12
    isym: 0
    ncore: 8
    lreal: Auto
    lcharg: false
    lwave: false
    kspacing: 0.30
    kgamma: true
    ibrion: 2
    isif: 3
    nsw: 1000
    ediffg: -5.0e-2
    potim: 0.1
    algo: Fast

queue:
  preset: auto
```

`structure.path` is resolved relative to the spec file. Use explicit `vasp.kpts` only when a fixed mesh is required; for the default workflow, prefer `vasp.parameters.kspacing` and `kgamma`.

## CLI Usage

```bash
vasp-job schema
vasp-job prepare input.yml
vasp-job submit input.yml
vasp-job status <job_uid_or_scheduler_id>
vasp-job show <job_uid_or_scheduler_id>
vasp-job list --limit 20
```

Typical flow:

```bash
vasp-job prepare input.yml
vasp-job submit input.yml
vasp-job status <job_uid>
vasp-job show <job_uid>
```

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
