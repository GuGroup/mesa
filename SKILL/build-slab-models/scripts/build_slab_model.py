#!/usr/bin/env python3
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

        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return float(value)
    except Exception:
        pass
    return str(value)


def safe_name(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text.strip())
    return text.strip("_") or "structure"


def cell_lengths(atoms) -> list[float]:
    return [float(x) for x in atoms.cell.lengths()]


def composition_counts(atoms) -> dict[str, int]:
    return dict(sorted(Counter(atoms.get_chemical_symbols()).items()))


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build clean slab models with slabuilder.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--formula", required=True, help="Formula, chemical system, or MP id.")
    parser.add_argument("--miller", nargs=3, type=int, required=True, metavar=("H", "K", "L"), help="Surface Miller index.")
    parser.add_argument("--search-mode", choices=["formula", "material_id", "chemsys", "elements"], default=None, help="Materials Project search mode. If omitted, mp-* inputs use material_id and all others use formula.")
    parser.add_argument("--max-results", type=int, default=5, help="Maximum Materials Project bulk candidates to fetch before sorting.")
    parser.add_argument("--entry-index", type=int, default=0, help="Bulk candidate index after slabuilder sorting.")
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

    try:
        from slabuilder import fetch_bulk_structures, generate_slab
        from slabuilder.structure_understanding import validate_structure_packet
        from slabuilder.utils import save_structure
    except Exception as exc:
        raise SystemExit(
            "Could not import slabuilder. Install it in the active environment. "
            f"Original error: {exc}"
        )

    search_mode = args.search_mode
    if search_mode is None:
        search_mode = "material_id" if args.formula.startswith("mp-") else "formula"

    entries = fetch_bulk_structures(args.formula, max_results=args.max_results, search_mode=search_mode)
    if not entries:
        raise SystemExit(f"No bulk structures found for {args.formula!r}.")
    if args.entry_index < 0 or args.entry_index >= len(entries):
        raise SystemExit(f"--entry-index {args.entry_index} out of range for {len(entries)} entries.")

    entry = entries[args.entry_index]
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
    if not args.all_terminations and (args.termination < 0 or args.termination >= len(slabs)):
        raise SystemExit(f"--termination {args.termination} out of range for {len(slabs)} terminations.")

    if args.all_terminations:
        chosen = list(enumerate(slabs))
    else:
        chosen = [(args.termination, slabs[args.termination])]

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
        metadata = {
            "kind": "slab",
            "formula": entry.formula,
            "bulk_formula": entry.formula,
            "slab_formula": atoms.get_chemical_formula(),
            "stoichiometry": stoich,
            "mpid": entry.mpid,
            "bulk_energy_above_hull": getattr(entry, "energy_above_hull", None),
            "miller": list(args.miller),
            "termination": int(term_index),
            "backend": getattr(result, "backend", None),
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

    summary = {
        "selected_bulk": {
            "mpid": entry.mpid,
            "formula": entry.formula,
            "entry_index": args.entry_index,
            "search_mode": search_mode,
        },
        "skipped_nonstoichiometric": skipped_nonstoich,
        "generated": records,
    }
    print(json.dumps(summary, indent=2, default=json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
