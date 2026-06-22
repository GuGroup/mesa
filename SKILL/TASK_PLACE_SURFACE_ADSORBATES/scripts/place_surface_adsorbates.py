#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path
import re
import sys
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


def remap_index(index: Any, original_to_poscar: list[int]) -> int | None:
    try:
        raw = int(index)
    except Exception:
        return None
    if 0 <= raw < len(original_to_poscar):
        return int(original_to_poscar[raw])
    return None


def remap_indices(indices: Any, original_to_poscar: list[int]) -> list[int]:
    if not isinstance(indices, (list, tuple)):
        return []
    out: list[int] = []
    for index in indices:
        remapped = remap_index(index, original_to_poscar)
        if remapped is not None:
            out.append(remapped)
    return out


def remap_site(site: Any, original_to_poscar: list[int]) -> Any:
    if not isinstance(site, dict):
        return site
    out = dict(site)
    if "surface_atom_indices" in out:
        out["surface_atom_indices"] = remap_indices(out.get("surface_atom_indices"), original_to_poscar)
    if "surface_atom_idx" in out:
        out["surface_atom_idx"] = remap_indices(out.get("surface_atom_idx"), original_to_poscar)
    return out


def remap_adsorbate_metadata(metadata: dict[str, Any], original_to_poscar: list[int]) -> dict[str, Any]:
    out = dict(metadata)
    if "atom_indices" in out:
        out["atom_indices"] = remap_indices(out.get("atom_indices"), original_to_poscar)
    if "anchor_index" in out and out.get("anchor_index") is not None:
        out["anchor_index"] = remap_index(out.get("anchor_index"), original_to_poscar)
    return out


def remap_site_graph_summary(summary: dict[str, Any], original_to_poscar: list[int]) -> dict[str, Any]:
    out = dict(summary)
    if isinstance(out.get("current_site"), dict):
        out["current_site"] = remap_site(out["current_site"], original_to_poscar)
    return out


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
        from slabuilder.utils import save_structure, vasp_export_metadata
    except Exception as exc:
        raise SystemExit(
            "Could not import slabuilder. Install it in the active environment. "
            f"Original error: {exc}"
        )

    slab_path = Path(args.slab).expanduser().resolve()
    slab = load_atoms(slab_path)
    with contextlib.redirect_stdout(sys.stderr):
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
        vasp_export = vasp_export_metadata(atoms)
        original_to_poscar = vasp_export.get("extxyz_index_to_poscar_index") or list(range(len(atoms)))
        poscar_to_original = vasp_export.get("poscar_index_to_extxyz_index") or list(range(len(atoms)))
        slab_atom_count = int(atoms.info.get("slab_atom_count", 0) or 0)
        original_slab_indices = list(range(slab_atom_count)) if slab_atom_count else []
        slab_atom_indices = remap_indices(original_slab_indices, original_to_poscar)
        with contextlib.redirect_stdout(sys.stderr):
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
                "surface_atom_idx": remap_indices(site.surface_atom_idx, original_to_poscar),
                "priority": site.priority,
                "placement_method": site.placement_method,
                "sources": site.sources,
                "validation_score": site.validation_score,
                "validation_notes": site.validation_notes,
            },
            "n_atoms": len(atoms),
            "slab_atom_count": slab_atom_count,
            "slab_atom_indices": slab_atom_indices,
            "adsorbate_atom_count": int(atoms.info.get("adsorbate_atom_count", 0) or 0),
            "adsorption_site_indices": ",".join(str(index) for index in remap_indices(site.surface_atom_idx, original_to_poscar)),
            "adsorption_site_atom_count": int(atoms.info.get("adsorption_site_atom_count", 0) or 0),
            "validation": validation,
            "site_graph_summary": remap_site_graph_summary({
                "backend": site_graph.get("backend"),
                "n_sites": site_graph.get("n_sites"),
                "n_edges": site_graph.get("n_edges"),
                "current_site": site_graph.get("current_site"),
                "warnings": site_graph.get("warnings"),
            }, original_to_poscar),
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
            "source_site": remap_site(json_info(atoms, "source_site_json", default={}), original_to_poscar),
            "paths": {
                "poscar": str(poscar_path),
            },
            "vasp_export": vasp_export,
        }
        adsorbate_metadata = json_info(atoms, "adsorbate_metadata_json", default={})
        if adsorbate_metadata:
            metadata["adsorbate_metadata"].update(remap_adsorbate_metadata(adsorbate_metadata, original_to_poscar))
        tags = atoms.get_tags().astype(int).tolist() if "tags" in getattr(atoms, "arrays", {}) else []
        if tags:
            metadata["atom_tags"] = [int(tags[int(original_index)]) for original_index in poscar_to_original]
        if args.write_extxyz:
            extxyz_path = save_structure(atoms, outdir / f"{stem}.extxyz", fmt="extxyz")
            metadata["paths"]["extxyz"] = str(extxyz_path)
        meta_path = outdir / f"{stem}.metadata.json"
        meta_path.write_text(json.dumps(metadata, indent=2, default=json_default))
        metadata["paths"]["metadata"] = str(meta_path)
        records.append(metadata)

    print(json.dumps({"generated": records}, indent=2, default=json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
