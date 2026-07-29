---
name: vasp-job
description: Prepare, submit, and track VASP calculations on the SGE HPC login node using the `vasp-job` CLI. This branch is a fast-inference/smoke-test protocol — it always assembles `vasp.parameters` from this skill's lightweight `defaults.yaml`, never from user-supplied parameters. Use when the user wants to run a fast/lightweight VASP relaxation or SCF job, queue a job with qsub, check job status, list recent jobs, or inspect result files on the cluster.
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

This branch (`mesa-dft-test`) is a fast-inference/smoke-test protocol: **always
use the lightweight defaults in [`defaults.yaml`](defaults.yaml), never anything
else.** Do not switch into a "minimal edit" mode that preserves a user-supplied
`vasp.parameters` set or an INCAR pasted by the user — even if the user provides
their own parameters or asks to keep an existing setup, assemble
`vasp.parameters` from `defaults.yaml` (`common` + `task.<task>` + only the
required system-dependent overrides below) and write the merged result
explicitly into the spec. If the user's request conflicts with these fast
defaults (e.g. asks for tighter convergence or a denser k-mesh), point this out
before overriding anything, but the default action on this branch is always the
`defaults.yaml` values, not the user's numbers.

The only overrides you should still decide per job are system-dependent, not a
matter of style:

- `ismear`/`sigma`: metal slab keeps the `defaults.yaml` values (`1`/`0.20`);
  switch to `0`/`0.05` only for a gas-phase molecule or insulator.
- `ispin`/`magmom`: non-magnetic systems omit them (VASP default `ispin: 1`);
  magnetic systems (Fe/Co/Ni/Mn/Cr/...) need `ispin: 2` + per-atom `magmom`.

Example for a `slab` job (common + task.slab, this branch's lightweight/fast
defaults, smearing left at the metal default, explicit Gamma-only mesh):

```yaml
job_name: co_pt111_001          # letters, numbers, . _ - only (used in paths)
task: slab                      # optional enum recorded in metadata (bulk|slab|freq|static)
project: screening              # optional group; omit or null for a flat layout

structure:
  format: poscar
  path: POSCAR                   # relative to this spec file; or use content: | inline

vasp:
  kpts: [1, 1, 1]                # this branch's default: one-point Gamma-only mesh
  gamma: true
  parameters:                   # lowercase vasp-ase keywords, not uppercase INCAR tags
    # --- common (from defaults.yaml) ---
    gga: PE
    prec: Low                   # fastest PREC tier — always use this on this branch
    encut: 350
    ediff: 5.0e-4
    algo: Fast
    nelm: 80
    ismear: 1                   # metal slab; gas molecule/insulator -> 0 + sigma 0.05
    sigma: 0.20
    ispin: 1                    # magnetic system -> 2 (+ magmom: [...] per atom)
    isym: 0
    lasph: true
    addgrid: true
    ncore: 4
    lreal: Auto
    lcharg: false
    lwave: false
    # --- task.slab (inherits common ionic-relaxation defaults as-is) ---
    ibrion: 2
    isif: 2
    nsw: 100
    ediffg: -0.08

queue:
  preset: presetg01gam          # this branch's default: pinned to the lightweight g01 node
```

Parameter rules:

- Always assemble parameters from `defaults.yaml` (`common` + `task.<task>` +
  the system-dependent overrides above) and write them explicitly. Do not carry
  over a user-supplied `vasp.parameters` set or INCAR wholesale on this branch.
  The CLI passes `vasp.parameters` to vasp-ase as-is; it does not add or
  override anything.
- `task` is optional but, when present, must be one of `bulk`, `slab`, `freq`, or
  `static`. It is recorded in metadata and selects the `defaults.yaml` overlay;
  the CLI itself does not merge task defaults.
- POSCAR is usually referenced with `structure.path`; relative paths are resolved
  from the spec file's directory. `structure.format` must be `poscar`. You may use
  `structure.content` instead to inline the POSCAR text, but set exactly one of
  `path` or `content`.
- `vasp.parameters` keys are lowercase vasp-ase keywords, not uppercase INCAR.
- k-points: this branch's default — always — is the explicit one-point
  Gamma-only mesh: `vasp.kpts: [1, 1, 1]` + `vasp.gamma: true`, with
  `kspacing`/`kgamma` omitted entirely. Do not set `kgamma` alongside an
  explicit `vasp.kpts`; it only affects KSPACING-generated meshes and has no
  effect once `kpts` is set, so adding it is a no-op that just invites
  confusion with the `gamma`/`kgamma` distinction below. Only switch to a
  `kspacing` mesh (and drop `vasp.kpts`/`vasp.gamma`) if the user explicitly
  asks for denser sampling; point out the accuracy/speed tradeoff before doing
  so.
- Treat `vasp.parameters.kgamma` and top-level `vasp.gamma` as different
  controls. `kgamma: true` means a Gamma-centered KSPACING mesh; it does not
  select the gamma-only VASP executable.
- Do not set POTCAR / `potcar` (server `vasp_pp_path`), queue internals
  (`pe`/`slots`/`vasp_command`), or `project.root` — server/preset-managed.

Run `vasp-job schema` for accepted top-level fields. The spec you submit (with
your full parameters) is recorded in the job's `input.yml`.

## Frequency (`freq`) task: fix the slab, free only the adsorbate

`vasp-job` never edits POSCAR content — it writes exactly what
`structure.path`/`structure.content` gives it. Before submitting a `task: freq`
job on an optimized adslab, prepare that POSCAR/CONTCAR yourself (outside
`vasp-job`) so that:

- **every slab atom is fixed** — Selective Dynamics `F F F` — regardless of
  which atoms were free during the prior `task: slab` optimization. This is
  stricter than the bottom-layer fixing used when *building* the slab (e.g.
  `build-slab-models`'s `--fix-ratio`): a frequency/Hessian calculation must
  not move any slab atom, not just the bottom support layers.
- **only the adsorbate atoms are free** — Selective Dynamics `T T T` — so
  `IBRION=5` only finite-displaces those atoms. This restricts the computed
  Hessian to the adsorbate's vibrational modes (the ones that feed ZPE/entropy
  corrections) and keeps the calculation cheap, which is the point of this
  branch's lightweight protocol. Do not skip this step even for a quick test —
  an unfixed slab turns a small adsorbate-only Hessian into a full slab-phonon
  calculation and defeats the "fast inference" goal entirely.

Never reuse the relaxed `task: slab` CONTCAR's Selective Dynamics flags
as-is for a `freq` job — those still mark the top slab layers as free (correct
for relaxation, wrong for the frequency calculation). Regenerate the flags
first, e.g. with ASE:

```python
from ase.io import read, write
from ase.constraints import FixAtoms

atoms = read("CONTCAR", format="vasp")  # optimized adslab from task: slab
adsorbate_indices = [...]  # from the placement skill's tags/metadata, not the slab
slab_indices = [i for i in range(len(atoms)) if i not in adsorbate_indices]
atoms.set_constraint(FixAtoms(indices=slab_indices))
write("POSCAR_freq", atoms, format="vasp")
```

Point the `freq` job spec's `structure.path` at the regenerated file
(`POSCAR_freq` above), not at the raw `task: slab` CONTCAR.

## Queue presets

`queue.preset` selects which SGE submit template is used:

- `presetg01gam` is this branch's default, and on this branch the **only**
  preset you should use unless the user explicitly asks otherwise. It pins the
  job to the lightweight node `g01` (`a6000.q` queue, 16 MPI slots) and runs
  `vasp_gam`, matching the mandatory `vasp.kpts: [1, 1, 1]` + `vasp.gamma: true`
  mesh from `defaults.yaml`.
- `presetg01std` — same node, but runs `vasp_std`. Only use this if the user
  explicitly asks for a non-Gamma-only k-mesh (denser `kspacing`); never switch
  to it "to be safe" — this branch's whole point is the fast Gamma-only path.
- `auto` picks 48- vs 64-core from current free nodes (`qq`) — only use this if
  the user asks to run off the shared pool instead of `g01`. For the VASP
  executable, `auto` must choose `gam` only when the spec explicitly has both
  `vasp.kpts: [1, 1, 1]` and `vasp.gamma: true` for a Gamma-only calculation. Do
  not infer `gam` from `vasp.parameters.kgamma: true`, from KSPACING, from task
  type, or from a Gamma-centered multi-point mesh. If uncertain, leave
  `vasp.gamma` unset and use `std`.
- `preset64std`, `preset64gam`, `preset48std`, `preset48gam` — pin the shared
  pool explicitly (not this branch's default; use only on explicit request).

## Workflow

1. (Optional) Learn the schema: `vasp-job schema`.
2. Write the spec to a file, e.g. `spec.yml`: assemble `vasp.parameters` from
   `defaults.yaml` (never from a user-supplied set), set `task` only to `bulk`,
   `slab`, `freq`, or `static`, and point `structure.path` at the POSCAR file
   (or inline it with `structure.content`).
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
