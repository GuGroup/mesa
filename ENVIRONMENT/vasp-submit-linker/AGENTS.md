# VASP SUBMIT LINKER

## OVERVIEW

- `vasp-submit` is the SGE-login-node package behind the `vasp-job` CLI.
- It prepares VASP inputs, renders approved submit scripts, records job metadata,
  and queries scheduler/completion state.
- Treat scheduler interaction and filesystem materialization as safety-critical.

## WHERE TO LOOK

| Concern | Location |
|---|---|
| CLI commands, JSON, exit codes | `src/vasp_submit/hpc_server/cli.py` |
| Spec parsing, inheritance, normalization | `src/vasp_submit/common/spec.py` |
| Public JSON schema | `src/vasp_submit/common/schema.py` |
| Path containment | `src/vasp_submit/common/paths.py` |
| Input generation and submission | `src/vasp_submit/hpc_server/renderer.py` |
| Preset selection | `src/vasp_submit/hpc_server/auto_preset.py` |
| Status/index behavior | `src/vasp_submit/hpc_server/jobs.py` |
| SGE contracts | `templates/sge/` |
| Runtime-facing guidance | `README.md`, `examples/`, `.codex/skills/vasp-job/` |

## CODE MAP

- `main` routes `schema`, `prepare`, `submit`, `status`, `list`, and `show`.
- `load_and_resolve_spec` applies `extends`/`--common`; the job spec wins.
- `normalize_spec` is the untrusted-spec gate before materialization.
- `validated_job_dir` and `require_under_trusted_roots` enforce containment.
- `prepare_job` writes the job directory; `submit_job` is the live `qsub` edge.
- `status_job` combines live `qstat` state with template-written exit markers.

## CONVENTIONS

- Job specs, structure references, CLI identifiers, and inherited YAML are
  untrusted. Server config owns trusted roots, scheduler, templates, queue
  topology, VASP executable policy, and pseudopotential paths.
- Route every spec-derived path segment through `common.paths`; resolve and
  verify containment before reads, directory creation, metadata, or index I/O.
- Keep `schema.py`, manual normalization, README/examples, both VASP skills,
  tests, and template preset names synchronized when the contract changes.
- Preserve one JSON object on stdout per command. Error results use `ok: false`
  and a nonzero process exit, including scheduler submission failures.
- A successful submit must expose a parsed scheduler ID; do not report ambiguous
  `qsub` output as success.
- Preparation should be transactional. Never index a job as prepared before all
  required input files exist; overwrite must not retain stale calculation files.
- `prepare` is not submission approval. Live submission requires explicit user
  authority and must also comply with the active repository policy.

## ANTI-PATTERNS

- Never invoke live `qsub` or `qstat` from tests; patch subprocess boundaries or
  use disposable fake executables with asserted argv, cwd, stdout, and status.
- Never use `shell=True`, interpolate scheduler commands, or accept client-owned
  executable, PE, slot, root, or template paths.
- Never bypass safe-path helpers with direct joins from job UID, project,
  `job_dir`, `structure.path`, or `extends` input.
- Never assume source-tree template discovery proves wheel packaging.
- Never change an SGE template without checking queue/PE, module and binary
  compatibility, exit-marker behavior, and all four preset variants.
- Never let `queue.submit: false` or an unapproved dry-run flow reach `qsub`.

## COMMANDS

```bash
# Contract suite; expected baseline: 37 tests.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src uv run --no-project --with pyyaml \
  python -m unittest discover -s tests -v

# Build outside the tree, then prove templates are actually inside the wheel.
out="$(mktemp -d)"
uv build --wheel --out-dir "$out"
unzip -l "$out"/*.whl | rg 'templates/sge/preset(48|64)(gam|std)\.sh'
```

- The wheel-template check is mandatory after packaging changes. The current
  source-tree lookup can pass tests even when built wheels omit all templates.
