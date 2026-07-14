#!/usr/bin/env python3
# noqa: SIZE_OK
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from typing import Any


def json_default(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    try:
        import numpy as np
    except ImportError:
        return str(value)
    else:
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return float(value)
    return str(value)


def safe_name(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text.strip())
    return text.strip("_") or "structure"


def load_local_bulk_structure(path: Path):
    """Load a local bulk file into a pymatgen Structure.

    Tries pymatgen first (POSCAR/CIF/...), then falls back to ASE for formats
    pymatgen cannot read directly (e.g. extxyz). This is the entry point for the
    "start from a local or code-generated bulk" path, so multicomponent systems
    that are absent from the Materials Project can still seed slab generation.
    """
    from pymatgen.core import Structure

    try:
        return Structure.from_file(str(path))
    except (OSError, ValueError):
        from ase.io import read as ase_read
        from pymatgen.io.ase import AseAtomsAdaptor

        atoms = ase_read(str(path))
        if atoms.cell is None or atoms.cell.rank < 3:
            raise SystemExit(
                f"--bulk-file {path} has no full 3D cell; a periodic bulk is required."
            )
        return AseAtomsAdaptor.get_structure(atoms)


def cell_lengths(atoms) -> list[float]:
    return [float(x) for x in atoms.cell.lengths()]


def composition_counts(atoms) -> dict[str, int]:
    return dict(sorted(Counter(atoms.get_chemical_symbols()).items()))


def composition_counts_for_indices(atoms, indices: list[int]) -> dict[str, int]:
    symbols = atoms.get_chemical_symbols()
    return dict(sorted(Counter(symbols[i] for i in indices).items()))


def stoichiometry_record(atoms, bulk_formula: str) -> dict[str, Any]:
    from pymatgen.core import Composition

    slab_counts = composition_counts(atoms)
    bulk_reduced = Composition(bulk_formula).reduced_formula
    slab_reduced = Composition(slab_counts).reduced_formula
    return {
        "bulk_reduced_formula": bulk_reduced,
        "slab_reduced_formula": slab_reduced,
        "slab_composition": slab_counts,
        "is_stoichiometric": slab_reduced == bulk_reduced,
    }


def _surface_normal_projection(atoms) -> list[float]:
    """Project atom positions onto the surface normal defined by a × b."""
    import numpy as np

    normal = np.cross(atoms.cell[0], atoms.cell[1])
    norm = float(np.linalg.norm(normal))
    if norm == 0.0:
        return [float(x) for x in atoms.positions[:, 2]]
    unit = normal / norm
    return [float(x) for x in atoms.positions @ unit]


def layer_summary_record(atoms, layer_gap: float = 0.55) -> dict[str, Any]:
    """Summarize top/bottom surface layers for termination inspection.

    The projection onto a × b makes this robust to skewed in-plane cells. The
    output is intentionally compact and JSON-only because it is used by example
    scans, not by DFT input generation.
    """
    if len(atoms) == 0:
        return {
            "layer_gap_angstrom": float(layer_gap),
            "n_layers": 0,
            "top_layer": {"indices": [], "composition": {}},
            "bottom_layer": {"indices": [], "composition": {}},
            "top_bottom_layer_composition_match": True,
            "termination_signature": "empty",
        }

    z_values = _surface_normal_projection(atoms)
    order = sorted(range(len(z_values)), key=lambda i: z_values[i])
    layers: list[list[int]] = [[order[0]]]
    for idx in order[1:]:
        previous_z = max(z_values[i] for i in layers[-1])
        if z_values[idx] - previous_z > layer_gap:
            layers.append([idx])
        else:
            layers[-1].append(idx)

    def layer_record(indices: list[int]) -> dict[str, Any]:
        zs = [z_values[i] for i in indices]
        return {
            "indices": sorted(int(i) for i in indices),
            "composition": composition_counts_for_indices(atoms, indices),
            "z_min": float(min(zs)),
            "z_max": float(max(zs)),
        }

    bottom = layer_record(layers[0])
    top = layer_record(layers[-1])
    top_comp = top["composition"]
    bottom_comp = bottom["composition"]
    match = top_comp == bottom_comp
    signature = f"top={top_comp}; bottom={bottom_comp}"
    return {
        "layer_gap_angstrom": float(layer_gap),
        "n_layers": len(layers),
        "top_layer": top,
        "bottom_layer": bottom,
        "top_bottom_layer_composition_match": match,
        "termination_signature": signature,
    }


def termination_quality_record(
    result,
    stoich: dict[str, Any],
    surface_summary: dict[str, Any],
    target_n_atoms: int,
) -> dict[str, Any]:
    """Rank/label a termination for model-building triage.

    Lower score is better. This is not an energy ranking; it is a safety and
    bookkeeping ranking that prevents silently defaulting to a polar,
    asymmetric, or non-stoichiometric surface.
    """
    score = 0.0
    flags: list[str] = []

    if getattr(result, "is_polar", False):
        score += 100.0
        flags.append("polar")
    else:
        flags.append("nonpolar")

    if not getattr(result, "is_symmetric", True):
        score += 25.0
        flags.append("asymmetric_top_bottom")
    else:
        flags.append("symmetric_top_bottom")

    if not stoich["is_stoichiometric"]:
        score += 50.0
        flags.append("nonstoichiometric")
    else:
        flags.append("stoichiometric")

    if not surface_summary["top_bottom_layer_composition_match"]:
        score += 10.0
        flags.append("different_top_bottom_layer_composition")

    if target_n_atoms > 0:
        score += min(abs(getattr(result, "n_atoms", 0) - target_n_atoms) / target_n_atoms, 1.0) * 5.0

    if stoich["is_stoichiometric"] and not getattr(result, "is_polar", False) and getattr(result, "is_symmetric", True):
        recommendation = "safe_default_candidate"
    elif getattr(result, "is_polar", False) or not stoich["is_stoichiometric"]:
        recommendation = "explicit_review_required"
    else:
        recommendation = "usable_with_review"

    return {
        "score": round(float(score), 6),
        "recommendation": recommendation,
        "flags": flags,
        "note": "Heuristic triage only; compare surface energies before final DFT production.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build clean slab models with slabuilder.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--formula", help="Disabled direct Materials Project/formula input. This script exits if it is provided.")
    parser.add_argument("--bulk-file", help="Optimized bulk structure file (POSCAR/CIF/extxyz/...). Required for slab generation.")
    parser.add_argument("--miller", nargs=3, type=int, required=True, metavar=("H", "K", "L"), help="Surface Miller index.")
    parser.add_argument("--search-mode", choices=["formula", "material_id", "chemsys", "elements"], default=None, help="Disabled; Materials Project fetch is not part of slab generation.")
    parser.add_argument("--max-results", type=int, default=5, help="Disabled; Materials Project fetch is not part of slab generation.")
    parser.add_argument("--entry-index", type=int, default=0, help="Disabled; Materials Project fetch is not part of slab generation.")
    parser.add_argument("--backend", choices=["auto", "catkit", "pymatgen", "surfaxe"], default="auto", help="Slab generation backend.")
    parser.add_argument("--prefer-symmetry", action="store_true", help="When backend is auto, prefer pymatgen symmetry/non-polar filtering.")
    parser.add_argument("--target-n-atoms", type=int, default=60, help="Target total atom count used by automatic layer/supercell selection.")
    parser.add_argument("--target-lateral-size", type=float, default=7.5, help="Target a/b lateral lengths in Angstrom.")
    parser.add_argument("--target-slab-thickness", type=float, default=6.0, help="Target material slab thickness in Angstrom, excluding vacuum.")
    parser.add_argument("--vacuum", type=float, default=15.0, help="Total vacuum thickness in Angstrom.")
    parser.add_argument("--supercell-na", type=int, help="Explicit diagonal supercell repeat along the first surface lattice vector.")
    parser.add_argument("--supercell-nb", type=int, help="Explicit diagonal supercell repeat along the second surface lattice vector.")
    parser.add_argument("--n-layers", type=int, help="Explicit layer count override for slab generation.")
    parser.add_argument("--fix-layers", type=int, help="Fix an explicit number of bottom layers (overrides --fix-ratio).")
    parser.add_argument("--fix-ratio", type=float, help="Fraction (0..1) of material thickness fixed from the bottom, c-axis fractional (default 0.4).")
    parser.add_argument("--termination", type=int, default=0, help="Termination index to save when --all-terminations is not set.")
    parser.add_argument("--all-terminations", action="store_true", help="Advanced/diagnostic: save every generated termination instead of only --termination.")
    parser.add_argument("--allow-nonstoichiometric", action="store_true", help="Allow non-stoichiometric surface terminations such as O-rich or O-poor oxide slabs.")
    parser.add_argument("--write-extxyz", action="store_true", help="Also write extxyz files and POSCAR/extxyz index mapping metadata.")
    parser.add_argument("--max-atoms", type=int, default=120, help="Maximum atom count accepted by validation.")
    parser.add_argument("--min-distance", type=float, default=0.5, help="Minimum interatomic distance threshold for validation in Angstrom.")
    parser.add_argument("--outdir", default="slabuilder_outputs/slabs", help="Output directory for POSCAR and metadata files.")
    args = parser.parse_args()

    if args.formula:
        raise SystemExit(
            "Direct Materials Project/formula slab generation is disabled. "
            "Use import-bulk-structure to import the source bulk, optimize it "
            "under the root calculation policy, then rerun build-slab-models "
            "with --bulk-file <optimized-bulk>."
        )
    if not args.bulk_file:
        raise SystemExit(
            "Provide --bulk-file <optimized-bulk>. Direct Materials "
            "Project/formula inputs are disabled for slab generation."
        )

    try:
        from slabuilder import generate_slab
        from slabuilder.structure_understanding import validate_structure_packet
        from slabuilder.utils import save_structure
    except ImportError as exc:
        raise SystemExit(
            "Could not import slabuilder. Install it in the active environment. "
            f"Original error: {exc}"
        )

    import types

    bulk_path = Path(args.bulk_file).expanduser().resolve()
    if not bulk_path.is_file():
        raise SystemExit(f"--bulk-file not found: {bulk_path}")
    structure = load_local_bulk_structure(bulk_path)
    entry = types.SimpleNamespace(
        structure=structure,
        formula=structure.composition.reduced_formula,
        mpid="local",
        energy_above_hull=None,
    )
    bulk_source = "optimized_bulk_file"
    search_mode = "bulk_file"
    args.entry_index = 0
    supercell = None
    if args.supercell_na or args.supercell_nb:
        if not (args.supercell_na and args.supercell_nb):
            raise SystemExit("Provide both --supercell-na and --supercell-nb.")
        supercell = (args.supercell_na, args.supercell_nb)

    slabs = generate_slab(
        entry.structure,
        tuple(args.miller),
        vacuum=args.vacuum,
        target_lateral_size=args.target_lateral_size,
        target_slab_thickness=args.target_slab_thickness,
        target_n_atoms=args.target_n_atoms,
        fix_layers=args.fix_layers,
        fix_ratio=args.fix_ratio,
        backend=None if args.backend == "auto" else args.backend,
        prefer_symmetry=args.prefer_symmetry,
        supercell=supercell,
        n_layers_override=args.n_layers,
        catkit_layer_type="trim" if args.allow_nonstoichiometric else "stoich",
    )
    if not slabs:
        raise SystemExit("slabuilder generated no slab terminations.")
    available_termination_count = len(slabs)
    if not args.all_terminations and (args.termination < 0 or args.termination >= len(slabs)):
        raise SystemExit(f"--termination {args.termination} out of range for {len(slabs)} terminations.")

    if args.all_terminations:
        chosen = list(enumerate(slabs))
    else:
        chosen = [(args.termination, slabs[args.termination])]
    selected_termination_indices = [int(term_index) for term_index, _ in chosen]

    skipped_nonstoich: list[dict[str, Any]] = []
    filtered: list[tuple[int, Any, dict[str, Any]]] = []
    for term_index, result in chosen:
        stoich = stoichiometry_record(result.ase_atoms, entry.formula)
        if stoich["is_stoichiometric"] or args.allow_nonstoichiometric:
            filtered.append((term_index, result, stoich))
        else:
            skipped_nonstoich.append({"termination": int(term_index), **stoich})

    if not filtered:
        raise SystemExit(
            "No stoichiometric slab terminations selected. "
            "Use --allow-nonstoichiometric to save O-rich/O-poor or otherwise "
            "non-stoichiometric terminations.\n"
            + json.dumps({"skipped_nonstoichiometric": skipped_nonstoich}, indent=2, default=json_default)
        )

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    hkl = "".join(str(x) for x in args.miller)
    for term_index, result, stoich in filtered:
        atoms = result.ase_atoms
        stem = safe_name(f"{entry.formula}_{entry.mpid}_{hkl}_term{term_index}")
        poscar_path = save_structure(atoms, outdir / f"{stem}_POSCAR", fmt="poscar")
        validation = validate_structure_packet(atoms, min_distance=args.min_distance, max_atoms=args.max_atoms)
        surface_summary = layer_summary_record(atoms)
        termination_quality = termination_quality_record(result, stoich, surface_summary, args.target_n_atoms)
        metadata = {
            "kind": "slab",
            "formula": entry.formula,
            "bulk_formula": entry.formula,
            "slab_formula": atoms.get_chemical_formula(),
            "stoichiometry": stoich,
            "mpid": entry.mpid,
            "bulk_source": bulk_source,
            "bulk_file": str(bulk_path) if args.bulk_file else None,
            "bulk_energy_above_hull": getattr(entry, "energy_above_hull", None),
            "miller": list(args.miller),
            "termination": int(term_index),
            "available_termination_count": available_termination_count,
            "all_terminations_requested": bool(args.all_terminations),
            "backend": getattr(result, "backend", None),
            "is_polar": bool(getattr(result, "is_polar", False)),
            "is_symmetric": bool(getattr(result, "is_symmetric", True)),
            "surface_summary": surface_summary,
            "termination_quality": termination_quality,
            "n_atoms": len(atoms),
            "cell_lengths": cell_lengths(atoms),
            "slab_thickness": getattr(result, "slab_thickness", None),
            "n_layers": getattr(result, "n_layers", None),
            "n_fixed": len(getattr(result, "fix_indices", []) or []),
            "supercell": {
                "na": getattr(result, "supercell_na", None),
                "nb": getattr(result, "supercell_nb", None),
                "matrix": getattr(result, "supercell_matrix", None),
            },
            "validation": validation,
            "paths": {
                "poscar": str(poscar_path),
            },
        }
        if args.write_extxyz:
            from slabuilder.utils import vasp_export_metadata

            extxyz_path = save_structure(atoms, outdir / f"{stem}.extxyz", fmt="extxyz")
            metadata["paths"]["extxyz"] = str(extxyz_path)
            metadata["vasp_export"] = vasp_export_metadata(atoms)
        meta_path = outdir / f"{stem}.metadata.json"
        meta_path.write_text(json.dumps(metadata, indent=2, default=json_default))
        metadata["paths"]["metadata"] = str(meta_path)
        records.append(metadata)

    ranked_records = sorted(
        records,
        key=lambda item: (
            item["termination_quality"]["score"],
            item["termination"],
        ),
    )
    best_score = ranked_records[0]["termination_quality"]["score"] if ranked_records else None
    recommended_candidates = [
        record["termination"]
        for record in ranked_records
        if record["termination_quality"]["score"] == best_score
    ]
    signature_counts: dict[str, dict[str, Any]] = {}
    for record in ranked_records:
        signature = record["surface_summary"]["termination_signature"]
        bucket = signature_counts.setdefault(
            signature,
            {
                "terminations": [],
                "count": 0,
                "top_layer": record["surface_summary"]["top_layer"]["composition"],
                "bottom_layer": record["surface_summary"]["bottom_layer"]["composition"],
            },
        )
        bucket["terminations"].append(record["termination"])
        bucket["count"] += 1

    selection_warnings: list[str] = []
    if not args.all_terminations and available_termination_count > 1:
        selection_warnings.append(
            f"{available_termination_count} terminations were generated, but this run saved only --termination {args.termination}; run --all-terminations before production."
        )
    if len(recommended_candidates) > 1:
        selection_warnings.append(
            "Multiple terminations have the same best heuristic score; choose explicitly."
        )
    if not any(record["termination_quality"]["recommendation"] == "safe_default_candidate" for record in ranked_records):
        selection_warnings.append(
            "No safe default candidate found; termination choice requires explicit review."
        )
    if any(not record["stoichiometry"]["is_stoichiometric"] for record in ranked_records):
        selection_warnings.append(
            "At least one saved termination is non-stoichiometric."
        )
    if any(not record["is_symmetric"] for record in ranked_records):
        selection_warnings.append(
            "At least one saved termination has asymmetric top/bottom surfaces."
        )
    if any(not record["surface_summary"]["top_bottom_layer_composition_match"] for record in ranked_records):
        selection_warnings.append(
            "At least one saved termination exposes different top and bottom layer compositions."
        )

    termination_summary_path = outdir / "termination_summary.json"
    termination_summary = {
        "selected_bulk": {
            "mpid": entry.mpid,
            "formula": entry.formula,
            "entry_index": args.entry_index,
            "search_mode": search_mode,
            "bulk_source": bulk_source,
        },
        "miller": list(args.miller),
        "available_termination_count": available_termination_count,
        "selected_termination_indices": selected_termination_indices,
        "all_terminations_requested": bool(args.all_terminations),
        "allow_nonstoichiometric": bool(args.allow_nonstoichiometric),
        "skipped_nonstoichiometric": skipped_nonstoich,
        "recommended_termination": ranked_records[0]["termination"] if ranked_records else None,
        "recommended_termination_candidates": recommended_candidates,
        "selection_warnings": selection_warnings,
        "unique_surface_signatures": list(signature_counts.values()),
        "ranked_terminations": [
            {
                "termination": record["termination"],
                "backend": record["backend"],
                "score": record["termination_quality"]["score"],
                "recommendation": record["termination_quality"]["recommendation"],
                "flags": record["termination_quality"]["flags"],
                "stoichiometry": record["stoichiometry"],
                "is_polar": record["is_polar"],
                "is_symmetric": record["is_symmetric"],
                "surface_summary": record["surface_summary"],
                "paths": record["paths"],
            }
            for record in ranked_records
        ],
    }
    termination_summary_path.write_text(json.dumps(termination_summary, indent=2, default=json_default))

    summary = {
        "selected_bulk": {
            "mpid": entry.mpid,
            "formula": entry.formula,
            "entry_index": args.entry_index,
            "search_mode": search_mode,
            "bulk_source": bulk_source,
        },
        "skipped_nonstoichiometric": skipped_nonstoich,
        "termination_summary": str(termination_summary_path),
        "recommended_termination": termination_summary["recommended_termination"],
        "recommended_termination_candidates": termination_summary["recommended_termination_candidates"],
        "selection_warnings": termination_summary["selection_warnings"],
        "generated": records,
    }
    print(json.dumps(summary, indent=2, default=json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
