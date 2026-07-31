---
name: run-vasp-local-node
description: Run already-prepared VASP input directories directly inside an existing compute-node allocation, as a non-SGE execution path that does not use per-calculation `qsub`. Use when Codex needs to execute VASP without per-calculation qsub submission, drain a local queue of prepared VASP folders, or check local-runner status. Concrete core/rank counts and VASP calculation parameters live in this skill's body and in `manage-vasp-jobs`/`defaults.yaml`, not in this description.
---

For MESA end-to-end use, read `SKILL/calculation/workflow.md` before applying
this skill.

# Run VASP Local Node

Use this skill only after VASP inputs already exist. It does not generate
`POSCAR`, `INCAR`, `KPOINTS`, or `POTCAR`; use `manage-vasp-jobs` with
`vasp-job prepare` or an equivalent approved input-generation path first.

`vasp-job prepare` writes to a server-managed `remote_dir`, not the MESA
`project/<project_name>/` tree. Before running any command below, copy the
prepared input files into the calculation's assigned execution directory
(`P###/calculations/C###/execution/units/E###/`, per
`SKILL/calculation/workflow.md`) and run every `run`/`mark-ready`/`watch`/
`status` command against that project-local copy — not the raw `remote_dir`
and not an ad hoc path outside the project.

This skill is the non-SGE execution layer, and every command in it is typed
from the login node — never assume or instruct an interactive `qsub -I`
session or a direct `ssh` into a compute node; neither is required. A compute
node is reserved exactly once, non-interactively, by `qsub`-submitting the
long-lived allocation wrapper below (see "Reserve a node"); that submitted
job runs `watch` and stays alive on the node it was scheduled to, polling a
queue directory. From then on, everything you do — `vasp-job prepare`,
copying inputs into place, `mark-ready`, `status`, `list` — is plain
filesystem I/O against that same queue directory over the shared filesystem,
run from the login node. Only the actual `mpirun`/VASP process launched by
`run`/`watch` executes on the reserved node, and that already happens
automatically inside the job SGE placed there — nothing else needs to run on
the node itself. For this local-runner path, use 40 VASP MPI ranks by default
and reserve the remaining cores for Codex, shell, filesystem, and OS overhead.

# Boundaries

- Preserve `manage-vasp-jobs` for SGE-per-calculation `qsub` submission,
  `vasp-job status`, and existing queue presets.
- The 40-rank cap applies only to this local-node runner. Do not apply it to
  normal `manage-vasp-jobs` SGE submissions; `preset48*` SGE jobs use 48 slots.
- Use this skill when the calculation should not call `vasp-job submit` and
  should instead run inside the current node allocation.
- Run exactly one VASP calculation at a time. Do not start multiple `run` or
  `watch` processes and do not parallelize independent VASP folders inside one
  allocation.
- `mark-ready`, `status`, `list`, and the one-time `qsub` submission of the
  allocation wrapper all run from the login node — that is the normal case,
  not an exception. Only the actual VASP execution (`run`/`watch` launching
  `mpirun`) must happen inside a real allocation; do not launch `run`/`watch`
  directly from the login node without `--require-allocation` detecting a real
  allocation (`NSLOTS`/`SLURM_JOB_ID`) or, for an explicit local smoke test,
  `MESA_ALLOW_LOCAL_VASP=1`.
- Do not choose scientific VASP settings here. The runner only executes already
  prepared inputs.
- Do not invent or hardcode local execution settings (core/rank counts,
  launcher command, node allocation) or VASP calculation parameters into this
  skill's frontmatter `description`, chat responses, or ad hoc scripts. Source
  them from `manage-vasp-jobs`/`defaults.yaml` profiles or the active project
  profile, and keep parameter documentation in one place (`manage-vasp-jobs`).
- If the user supplies their own parameter/config YAML (a job spec, a common
  file, or an INCAR-derived parameter set), treat every value in it as
  authoritative. Do not silently tighten, loosen, or otherwise deviate from any
  field it sets; only fill in fields it leaves unset, using the profiles in
  `manage-vasp-jobs/defaults.yaml`.
- Record recipe-local `execution_manifest.json` entries with
  `skill: run-vasp-local-node`, the command used, input directory, local runner
  metadata, output logs, and acceptance boundary.

# Runner

The reusable runner is:

```bash
python SKILL/calculation/run-vasp-local-node/scripts/vasp_local_node_runner.py
```

It prints JSON for foreground commands and writes local metadata into each job
directory:

```text
.mesa_vasp_local_state.json
.mesa_vasp_local_started
.mesa_vasp_local_finished
.mesa_vasp_local_exit_code
.mesa_vasp_local.lock
vasp.local.stdout
vasp.local.stderr
vasp.local.command.json
```

For compatibility with prepared `vasp-job` folders, successful or failed runs
also write `.vasp_submit_finished` and `.vasp_submit_exit_code`, and update
`.vasp_submit_metadata.json` / its `index_path` when those files exist.

The runner defaults to `vasp_std` for `--executable std` and `vasp_gam` for
`--executable gam`. The SGE allocation wrapper loads
`vasp/6.3.2-vtst-vaspsol-beef-intel` by default before invoking the runner;
set `MESA_VASP_MODULE` only when the site module differs.

# Reserve a Node

This is the standard entry point, and it is a single `qsub` batch submission
from the login node — not an interactive session:

```bash
qsub -v MESA_VASP_LOCAL_QUEUE_DIR=/path/to/local_queue_root \
  SKILL/calculation/run-vasp-local-node/scripts/start_48core_local_runner.sge.sh
```

SGE schedules this job onto one 48-core node and, once there, it runs `watch`
on `MESA_VASP_LOCAL_QUEUE_DIR` and stays alive — it does not exit after one
calculation. That one node is now reserved for as long as this job keeps
running. Everything after this point (below) happens from the login node
against `MESA_VASP_LOCAL_QUEUE_DIR` over the shared filesystem; nothing else
needs to run on the node. Edit a copy of the script if the cluster queue,
parallel environment, module, or VASP command differs. Cancel the reservation
with the cluster's normal job-cancel command (e.g. `qdel <job_id>`) when no
more calculations are expected.

# Local Queue

From the login node, mark each prepared directory as ready once its inputs
are in place under the project execution directory:

```bash
python SKILL/calculation/run-vasp-local-node/scripts/vasp_local_node_runner.py \
  mark-ready /path/to/prepared_vasp_dir
```

The `watch` job reserved above discovers directories containing
`.mesa_vasp_local_ready` under the same queue root, runs them one at a time,
skips completed jobs, and sleeps when no ready job exists. This is
intentionally serial: one prepared VASP folder consumes the 40-rank VASP
runner, then the next folder starts only after the previous one exits. Keep
`mark-ready`-ing new directories under the same queue root for as long as the
reservation is alive; you do not need to resubmit or re-enter anything.

Check status (login node, reads job-directory metadata, no allocation
needed):

```bash
python SKILL/calculation/run-vasp-local-node/scripts/vasp_local_node_runner.py \
  status /path/to/prepared_vasp_dir
```

List local queue candidates (login node):

```bash
python SKILL/calculation/run-vasp-local-node/scripts/vasp_local_node_runner.py \
  list /path/to/local_queue_root
```

# Single Directory (advanced)

`run` launches VASP directly and requires an actual allocation
(`--require-allocation` checks `NSLOTS`/`SLURM_JOB_ID`), so it cannot be typed
interactively from the login node. Use it only when you need one-off,
non-queue execution — e.g. inside a dedicated one-off `qsub` wrapper script
(mirroring `start_48core_local_runner.sge.sh` but calling `run` on a single
directory instead of `watch` on a queue root), not the reserve-then-mark-ready
flow above:

```bash
python SKILL/calculation/run-vasp-local-node/scripts/vasp_local_node_runner.py \
  run /path/to/prepared_vasp_dir \
  --min-cores 40 \
  --max-cores 40 \
  --require-allocation \
  --executable std
```

For Gamma-only jobs where the prepared inputs intentionally use the Gamma VASP
binary, pass `--executable gam` instead. Use a custom site launcher when the
cluster requires it:

```bash
python SKILL/calculation/run-vasp-local-node/scripts/vasp_local_node_runner.py \
  run /path/to/prepared_vasp_dir \
  --min-cores 40 \
  --max-cores 40 \
  --require-allocation \
  --vasp-command 'mpirun -machinefile {machinefile} -n {cores} {executable}'
```

Placeholders supported by `--vasp-command` are `{cores}`, `{executable}`,
`{job_dir}`, and `{machinefile}`. Environment variables in the template are
expanded before execution.

# Validation

Before an actual run, use:

```bash
python SKILL/calculation/run-vasp-local-node/scripts/vasp_local_node_runner.py \
  run /path/to/prepared_vasp_dir --dry-run --min-cores 1
```

The dry run validates required inputs and records the command that would run.
Actual evidence still requires downstream result analysis, usually
`analyze-relaxation-results`, before an endpoint can be accepted.
