# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-24

## OVERVIEW
`vasp-submit-linker` is the `vasp-job` CLI package for preparing, submitting, listing, showing, and tracking VASP jobs directly on the Mirae SGE login node.

## STRUCTURE
```text
vasp-submit-linker/
|-- README.md
|-- pyproject.toml
|-- src/vasp_submit/hpc_server/
|-- templates/sge/
`-- tests/
```

## WHERE TO LOOK
| Task | Location | Notes |
| --- | --- | --- |
| User/operator flow | `README.md` | Install, config, job spec, CLI commands. |
| CLI entry | `pyproject.toml` | `vasp-job = vasp_submit.hpc_server.cli:main`. |
| Server logic | `src/vasp_submit/hpc_server/` | Config, renderer, job metadata, CLI. |
| SGE templates | `templates/sge/` | Queue preset scripts. |
| Contract tests | `tests/` | Job listing/show, renderer/qsub, spec normalization. |
| Docs CI | `.github/workflows/docs.yml` | Builds MkDocs strictly. |

## CONVENTIONS
- Install on Mirae with `uv tool install --python 3.11 . --constraint constraints.txt --force`.
- Runtime config lives at `~/.config/vasp-submit/hpc-server.yml`.
- Every CLI command prints one JSON object; parse JSON before deciding the next step.
- `structure.path` is resolved relative to the spec file.
- Tests use `unittest`, `PYTHONPATH=src`, mocks, and no live SGE dependency.

## ANTI-PATTERNS
- Do not use a local API server or SSH proxy; call `vasp-job` directly on the login node.
- Do not set POTCAR paths, queue internals, or `project.root` in job specs; server/preset config owns those.
- Do not treat `vasp.parameters.kgamma` as top-level `vasp.gamma`; they select different behavior.
- Do not rely on docs CI until `.[docs]` is declared or the workflow is corrected.

## COMMANDS
```bash
uv tool install --python 3.11 . --constraint constraints.txt --force
vasp-job schema
vasp-job prepare input.yml
vasp-job submit input.yml
vasp-job status <job_uid_or_scheduler_id>
vasp-job show <job_uid_or_scheduler_id>
vasp-job list --limit 20
PYTHONPATH=src uv run --no-project --with pyyaml python -m unittest discover -s tests -v
```
