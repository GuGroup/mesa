# BUILD TOOLS KNOWLEDGE BASE

## OVERVIEW

- Vendored `slabuilder` engine for clean slabs, adsorbate placement, and read-only structure inspection.
- Runtime is exactly Python `3.11.*`; normal shared environment is conda/mamba env `modeling`.
- Package code is under `slabuilder/`; `.codex/skills/` contains embedded direct-script wrappers, not installed console entry points.

## WHERE TO LOOK

| Task | Location |
|---|---|
| Dependency/build metadata | `pyproject.toml`, `environment.yml` |
| Public construction API | `slabuilder/__init__.py` |
| Slab backend selection/sizing | `slabuilder/backend_policy.py`, `slabuilder/slab_gen.py` |
| Adsorbate/site generation | `slabuilder/adsorption.py`, `slabuilder/config.py` |
| Site graphs and inspection packets | `slabuilder/site_map.py`, `slabuilder/structure_understanding.py` |
| Geometry checks/export | `slabuilder/structure_checks.py`, `slabuilder/cell_shape.py`, `slabuilder/utils.py` |
| Optional chemical-name conversion | `slabuilder/opsin.py` |
| Package tests | `tests/` |
| Embedded wrappers | `.codex/skills/*/scripts/` |

## CODE MAP

- Public exports: `fetch_bulk_structures`, `BulkEntry`, `generate_slab`, `SlabResult`, `build_adsorbate_atoms`, `generate_all_adsorption_structures`.
- `generate_slab` is the main slab seam: target sizing -> backend choice -> termination generation -> adaptive thickness retry -> bottom constraint.
- Actual auto policy: explicit backend wins; symmetry preference selects pymatgen; oxides select surfaxe; nitrides and other materials select CatKit.
- CatKit failure falls back to pymatgen; surfaxe failure falls back to symmetrized pymatgen. Preserve warning/provenance behavior.
- `identify_adsorption_sites` merges CatKit, pymatgen, and compatible ACAT candidates; auto placement may try AutoAdsorbate first.
- `resolve_adsorbate_smiles` resolves explicit SMILES, configured aliases, RDKit SMILES, then optional OPSIN/Java names.
- `structure_understanding.py` owns bounded analysis, selection, fragment, site, transform-proposal, and validation packets.
- Hotspots are large: `adsorption.py`, `slab_gen.py`, and `structure_understanding.py`; trace callers and add focused tests before changing shared seams.

## CONVENTIONS

- Adsorbed structures use ASE tags: `0` fixed slab, `1` relaxable slab, `2` adsorbate.
- Store adsorption anchors in `atoms.info`/metadata (`adsorption_site_indices`, counts, source/site records); never overwrite role tags.
- Clean slabs may omit role tags when `FixAtoms` constraints identify their fixed support atoms.
- Preserve initial magnetic moments, constraints, periodic cell data, builder/backend provenance, and extxyz/POSCAR index mapping.
- Validate finite cell, positive volume/lengths, minimum distance, atom-count cap, tag/magmom lengths, and metadata index bounds before handoff.
- Default overlap guard is `0.5 Å`; default bottom fixing is `0.4` of material thickness unless explicit layers override it.
- Materials Project fetch requires `MP_API_KEY` or `PMG_MAPI_KEY`; OPSIN additionally requires the `opsin` extra and Java on `PATH`.
- Active workflow wrapper `SKILL/modeling/build-slab-models/scripts/build_slab_model.py` intentionally differs from the embedded wrapper. Treat drift explicitly: identify the authoritative consumer, test both surfaces, and synchronize only intended shared behavior.

## ANTI-PATTERNS

- Do not infer adsorbate or anchor atoms from coordinates when tags/metadata provide the contract.
- Do not strip tags, `FixAtoms`, magmoms, site provenance, validation records, or parent paths during conversion/export.
- Do not silently change backend fallback, termination filtering, stoichiometry policy, bounded output limits, or scientific defaults.
- Do not treat inspection transform proposals as generated endpoints or generated structures as energy evidence.
- Do not edit `.venv/`, caches, or generated `slabuilder_outputs/` as source.
- Do not assume embedded `.codex` wrappers and active `SKILL/modeling` wrappers are identical.

## COMMANDS

```bash
# From ENVIRONMENT/build_tools
mamba env create -f environment.yml
mamba env update -f environment.yml --prune

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v

.venv/bin/python .codex/skills/build-slab-models/scripts/build_slab_model.py --help
.venv/bin/python .codex/skills/place-surface-adsorbates/scripts/place_surface_adsorbates.py --help
.venv/bin/python .codex/skills/inspect-surface-sites/scripts/inspect_surface_sites.py --help
.venv/bin/python ../../SKILL/modeling/build-slab-models/scripts/build_slab_model.py --help
```
