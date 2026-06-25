# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-24

## OVERVIEW
`ENVIRONMENT/` contains the runtime packages and installation surfaces that MESA skills call into: the local `slabuilder` scientific engine and the `vasp-job` HPC submission helper.

## STRUCTURE
```text
ENVIRONMENT/
|-- build_tools/
|   |-- pyproject.toml
|   |-- environment.yml
|   |-- slabuilder/
|   `-- tests/
`-- vasp-submit-linker/
    |-- pyproject.toml
    |-- src/vasp_submit/
    |-- templates/
    `-- tests/
```

## WHERE TO LOOK
| Task | Location | Notes |
| --- | --- | --- |
| Scientific runtime env | `build_tools/environment.yml` | Creates/updates `modeling`. |
| Slabuilder package config | `build_tools/pyproject.toml` | Python 3.11, Hatchling, direct VCS deps. |
| Slabuilder logic | `build_tools/slabuilder/` | Large files in adsorption, slab generation, structure understanding. |
| VASP CLI package config | `vasp-submit-linker/pyproject.toml` | `vasp-job = vasp_submit.hpc_server.cli:main`. |
| Mirae install and checks | `vasp-submit-linker/README.md` | `uv tool install`, `unittest discover`, CLI usage. |
| Docs CI | `vasp-submit-linker/.github/workflows/docs.yml` | Runs `mkdocs build --strict`. |

## CONVENTIONS
- Use `mamba` for `build_tools`; `environment.yml` installs the package editable with pip.
- `build_tools` permits direct VCS dependencies via `tool.hatch.metadata.allow-direct-references = true`.
- `vasp-submit-linker` is installed on Mirae with `uv tool install --python 3.11 . --constraint constraints.txt --force`.
- `vasp-submit-linker` tests run with `PYTHONPATH=src uv run --no-project --with pyyaml python -m unittest discover -s tests -v`.

## ANTI-PATTERNS
- Do not assume a root-level Python package or shared test runner exists.
- Do not run browser-backed visual tools before installing Playwright Chromium into `modeling`.
- Do not rely on the docs workflow until the `.[docs]` extra mismatch is checked.

## COMMANDS
```bash
cd build_tools
mamba env create -f environment.yml
mamba env update -f environment.yml --prune
mamba run -n modeling python -m playwright install chromium

cd ../vasp-submit-linker
PYTHONPATH=src uv run --no-project --with pyyaml python -m unittest discover -s tests -v
```
