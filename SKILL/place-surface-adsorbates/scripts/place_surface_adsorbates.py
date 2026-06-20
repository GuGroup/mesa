#!/usr/bin/env python3
from __future__ import annotations

import argparse
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


def json_info(atoms, key: str, default: Any = None) -> Any:
    raw = atoms.info.get(key)
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def load_atoms(path: Path):
    from ase.io import read

    atoms = read(str(path), index=-1)
    atoms.set_pbc([True, True, False])
    return atoms


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Identify sites and place adsorbates with slabuilder.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--slab", required=True, help="Parent slab file, usually POSCAR/VASP.")
    parser.add_argument("--adsorbate", required=True, help='Adsorbate label, name, or "smiles:<SMILES>".')
    parser.add_argument("--max-sites", type=int, default=3, help="Maximum adsorption-site candidates to place.")
    parser.add_argument("--height", type=float, help="Optional adsorbate anchor height above the site in Angstrom.")
    parser.add_argument("--backend", default="auto", choices=["auto", "acat", "catkit", "pymatgen"], help="Site-identification backend.")
    parser.add_argument("--write-extxyz", action="store_true", help="Also write extxyz files and POSCAR/extxyz index mapping metadata.")
    parser.add_argument("--max-atoms", type=int, default=120, help="Maximum atom count accepted by validation.")
    parser.add_argument("--min-distance", type=float, default=0.5, help="Minimum interatomic distance threshold for validation in Angstrom.")
    parser.add_argument("--outdir", default="slabuilder_outputs/adsorbates", help="Output directory for POSCAR and metadata files.")
    args = parser.parse_args()

    try:
        from slabuilder import generate_all_adsorption_structures
        from slabuilder.structure_understanding import analyze_surface_sites_packet, validate_structure_packet
        from slabuilder.utils import save_structure
    except Exception as exc:
        raise SystemExit(
            "Could not import slabuilder. Install it in the active environment. "
            f"Original error: {exc}"
        )

    slab_path = Path(args.slab).expanduser().resolve()
    slab = load_atoms(slab_path)
    candidates = generate_all_adsorption_structures(
        slab,
        args.adsorbate,
        max_sites=args.max_sites,
        height=args.height,
        backend=args.backend,
    )
    if not candidates:
        raise SystemExit("No adsorption candidates were generated.")

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    stem_base = safe_name(f"{slab_path.stem}_{args.adsorbate}")
    for index, (site, atoms) in enumerate(candidates):
        stem = f"{stem_base}_site{index}_{safe_name(site.site_type)}"
        poscar_path = save_structure(atoms, outdir / f"{stem}_POSCAR", fmt="poscar")
        validation = validate_structure_packet(atoms, min_distance=args.min_distance, max_atoms=args.max_atoms)
        site_graph = analyze_surface_sites_packet(
            atoms,
            structure_id=f"ads:{stem}",
            target_adsorbate=args.adsorbate,
            backend="acat",
        )
        metadata = {
            "kind": "adsorbate",
            "parent_slab": str(slab_path),
            "adsorbate": args.adsorbate,
            "candidate_index": index,
            "site": {
                "site_type": site.site_type,
                "position": site.position,
                "surface_atom_idx": site.surface_atom_idx,
                "priority": site.priority,
                "placement_method": site.placement_method,
                "sources": site.sources,
                "validation_score": site.validation_score,
                "validation_notes": site.validation_notes,
            },
            "n_atoms": len(atoms),
            "slab_atom_count": int(atoms.info.get("slab_atom_count", 0) or 0),
            "adsorbate_atom_count": int(atoms.info.get("adsorbate_atom_count", 0) or 0),
            "adsorption_site_indices": atoms.info.get("adsorption_site_indices"),
            "adsorption_site_atom_count": int(atoms.info.get("adsorption_site_atom_count", 0) or 0),
            "validation": validation,
            "site_graph_summary": {
                "backend": site_graph.get("backend"),
                "n_sites": site_graph.get("n_sites"),
                "n_edges": site_graph.get("n_edges"),
                "current_site": site_graph.get("current_site"),
                "warnings": site_graph.get("warnings"),
            },
            "adsorbate_metadata": {
                key: atoms.info.get(key)
                for key in [
                    "adsorbate_builder",
                    "adsorbate_smiles",
                    "adsorbate_smiles_source",
                    "adsorbate_surrogate_smiles",
                    "adsorbate_fallback_reason",
                    "adsorbate_placement_backend",
                    "binding_contact_warning",
                ]
                if atoms.info.get(key) is not None
            },
            "source_site": json_info(atoms, "source_site_json", default={}),
            "paths": {
                "poscar": str(poscar_path),
            },
        }
        adsorbate_metadata = json_info(atoms, "adsorbate_metadata_json", default={})
        if adsorbate_metadata:
            metadata["adsorbate_metadata"].update(adsorbate_metadata)
        tags = atoms.get_tags().astype(int).tolist() if "tags" in getattr(atoms, "arrays", {}) else []
        if tags:
            metadata["atom_tags"] = tags
        if args.write_extxyz:
            from slabuilder.utils import vasp_export_metadata

            extxyz_path = save_structure(atoms, outdir / f"{stem}.extxyz", fmt="extxyz")
            metadata["paths"]["extxyz"] = str(extxyz_path)
            metadata["vasp_export"] = vasp_export_metadata(atoms)
        meta_path = outdir / f"{stem}.metadata.json"
        meta_path.write_text(json.dumps(metadata, indent=2, default=json_default))
        metadata["paths"]["metadata"] = str(meta_path)
        records.append(metadata)

    print(json.dumps({"generated": records}, indent=2, default=json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
