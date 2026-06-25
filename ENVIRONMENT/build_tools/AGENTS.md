# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-24

## OVERVIEW
`build_tools` packages the trimmed vendored `slabuilder` engine used by MESA skills for bulk/slab generation, adsorbate construction, site policies, structure understanding, and visual-review support.

## STRUCTURE
```text
build_tools/
|-- pyproject.toml
|-- environment.yml
|-- slabuilder/
|   |-- adsorption.py
|   |-- slab_gen.py
|   `-- structure_understanding.py
`-- tests/
```

## WHERE TO LOOK
| Task | Location | Notes |
| --- | --- | --- |
| Dependencies/build | `pyproject.toml` | Python `==3.11.*`, Hatchling, direct VCS deps. |
| Runtime env | `environment.yml` | `modeling` env, editable install, aseview export. |
| Adsorbates/sites | `slabuilder/adsorption.py` | Largest hotspot; site and adsorbate building logic. |
| Slab generation | `slabuilder/slab_gen.py` | Backend policy, terminations, slab sizing. |
| Structure checks | `slabuilder/structure_understanding.py` | Validation/interpretation helpers. |
| Contract tests | `tests/` | `unittest` tests for backend policy, adsorbates, structure understanding. |

## CONVENTIONS
- The package is installed editable through the mamba env; use the `modeling` env for skill workflows.
- Optional extras: `.[opsin]` for chemical-name resolution, `.[dev]` for pytest/coverage.
- OPSIN also needs Java on `PATH`; labels and SMILES still work without it.
- Visual review tools need `aseview[export]` and a one-time `playwright install chromium`.

## ANTI-PATTERNS
- Do not assume Materials Project lookup works without `MP_API_KEY` or `PMG_MAPI_KEY`.
- Do not make non-DFT-ready atom-count expansions unless the user explicitly asks.
- Do not use name-based adsorbate resolution when a label or `smiles:<SMILES>` is available.

## COMMANDS
```bash
mamba env create -f environment.yml
mamba env update -f environment.yml --prune
mamba run -n modeling python -m playwright install chromium
pip install -e ".[opsin]"
pip install -e ".[dev]"
```
