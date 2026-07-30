---
name: run-vasp-local-node
description: Run prepared VASP input directories directly inside an already allocated compute node, especially a long-lived 48-core SGE allocation used as a local VASP runner with 40 VASP MPI ranks and strictly serial one-calculation-at-a-time execution. Use when Codex needs to execute VASP without per-calculation qsub submission, drain a local queue of prepared VASP folders, check local-runner status, or bridge vasp-job prepare output to direct node-local VASP execution while preserving existing SGE vasp-job behavior.
---

For MESA end-to-end use, read `SKILL/calculation/workflow.md` before applying
this skill.

# Run VASP Local Node

Use this skill only after VASP inputs already exist. It does not generate
`POSCAR`, `INCAR`, `KPOINTS`, or `POTCAR`; use `manage-vasp-jobs` with
`vasp-job prepare` or an equivalent approved input-generation path first.

This skill is the non-SGE execution layer. It assumes the user has already
entered or reserved a compute node, commonly by submitting one long-lived
48-core allocation job, and then runs VASP directly inside that allocation.
For this local-runner path, use 40 VASP MPI ranks by default and reserve the
remaining cores for Codex, shell, filesystem, and OS overhead.

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
- Do not run this from a login node unless the user explicitly confirms a local
  test or provides `MESA_ALLOW_LOCAL_VASP=1`.
- Do not choose scientific VASP settings here. The runner only executes already
  prepared inputs.
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

# Single Directory

Run one prepared directory from inside an allocated 48-core node:

```bash
python SKILL/calculation/run-vasp-local-node/scripts/vasp_local_node_runner.py \
  run /path/to/prepared_vasp_dir \
  --min-cores 40 \
  --max-cores 40 \
  --require-allocation \
  --executable std
```

For Gamma-only jobs where the prepared inputs intentionally use the Gamma VASP
binary:

```bash
python SKILL/calculation/run-vasp-local-node/scripts/vasp_local_node_runner.py \
  run /path/to/prepared_vasp_dir \
  --min-cores 40 \
  --max-cores 40 \
  --require-allocation \
  --executable gam
```

Use a custom site launcher when the cluster requires it:

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

# Local Queue

For a long-lived allocation, mark prepared directories as ready:

```bash
python SKILL/calculation/run-vasp-local-node/scripts/vasp_local_node_runner.py \
  mark-ready /path/to/prepared_vasp_dir
```

Then drain all ready directories under a queue root:

```bash
python SKILL/calculation/run-vasp-local-node/scripts/vasp_local_node_runner.py \
  watch /path/to/local_queue_root \
  --min-cores 40 \
  --max-cores 40 \
  --require-allocation \
  --executable std
```

`watch` discovers directories containing `.mesa_vasp_local_ready`, runs them
one at a time, skips completed jobs, and sleeps when no ready job exists. This
is intentionally serial: one prepared VASP folder consumes the 40-rank VASP
runner, then the next folder starts only after the previous command exits. Use
`--once` for a finite pass.

Check status:

```bash
python SKILL/calculation/run-vasp-local-node/scripts/vasp_local_node_runner.py \
  status /path/to/prepared_vasp_dir
```

List local queue candidates:

```bash
python SKILL/calculation/run-vasp-local-node/scripts/vasp_local_node_runner.py \
  list /path/to/local_queue_root
```

# Optional SGE Allocation Wrapper

The helper below is an allocation wrapper, not a per-calculation submitter:

```bash
qsub -v MESA_VASP_LOCAL_QUEUE_DIR=/path/to/local_queue_root \
  SKILL/calculation/run-vasp-local-node/scripts/start_48core_local_runner.sge.sh
```

It requests one 48-core SGE allocation and runs `watch` inside that allocation.
Inside that 48-core allocation, the runner uses only 40 VASP MPI ranks and runs
one calculation at a time. Edit a copy if the cluster queue, parallel
environment, module, or VASP command differs. Keep the actual VASP directories
prepared before marking them ready.

# Validation

Before an actual run, use:

```bash
python SKILL/calculation/run-vasp-local-node/scripts/vasp_local_node_runner.py \
  run /path/to/prepared_vasp_dir --dry-run --min-cores 1
```

The dry run validates required inputs and records the command that would run.
Actual evidence still requires downstream result analysis, usually
`analyze-relaxation-results`, before an endpoint can be accepted.
