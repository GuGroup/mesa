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
    text = re.sub(r"[^A-Za-z0-9_.@:-]+", "_", text.strip())
    return text.strip("_").replace(":", "-").replace("@", "_at_") or "structure"


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


def remap_binding_contact(record: Any, original_to_poscar: list[int]) -> Any:
    if not isinstance(record, dict):
        return record
    out = dict(record)
    if "closest_index" in out:
        out["closest_index"] = remap_index(out.get("closest_index"), original_to_poscar)
    return out


def remap_placement(record: Any, original_to_poscar: list[int]) -> Any:
    if not isinstance(record, dict):
        return record
    out = dict(record)
    out["atom_indices"] = remap_indices(out.get("atom_indices"), original_to_poscar)
    if "anchor_index" in out:
        out["anchor_index"] = remap_index(out.get("anchor_index"), original_to_poscar)
    if "site" in out:
        out["site"] = remap_site(out["site"], original_to_poscar)
    if "binding_contact" in out:
        out["binding_contact"] = remap_binding_contact(out["binding_contact"], original_to_poscar)
    return out


def remap_multi_metadata(metadata: dict[str, Any], original_to_poscar: list[int]) -> dict[str, Any]:
    out = dict(metadata)
    if "atom_indices" in out:
        out["atom_indices"] = remap_indices(out.get("atom_indices"), original_to_poscar)
    if "anchor_index" in out:
        out["anchor_index"] = remap_index(out.get("anchor_index"), original_to_poscar)
    if isinstance(out.get("placements"), list):
        out["placements"] = [remap_placement(item, original_to_poscar) for item in out["placements"]]
    return out


def parse_placement(text: str):
    from slabuilder.adsorption import AdsorbatePlacementSpec

    raw = str(text).strip()
    if not raw:
        raise argparse.ArgumentTypeError("empty placement")
    if "@" in raw:
        adsorbate, rest = raw.split("@", 1)
        parts = [part for part in rest.split(":") if part != ""]
    else:
        parts = raw.split(":")
        if raw.startswith("smiles:") and len(parts) <= 2:
            return AdsorbatePlacementSpec(adsorbate=raw)
        adsorbate = parts[0]
        parts = parts[1:]
    site_type = parts[0] if len(parts) >= 1 else None
    try:
        site_ordinal = int(parts[1]) if len(parts) >= 2 else 0
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid site ordinal in placement {text!r}") from exc
    try:
        height = float(parts[2]) if len(parts) >= 3 else None
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid height in placement {text!r}") from exc
    if len(parts) > 3:
        raise argparse.ArgumentTypeError(f"too many fields in placement {text!r}")
    return AdsorbatePlacementSpec(
        adsorbate=adsorbate,
        site_type=site_type,
        site_ordinal=site_ordinal,
        height=height,
    )


def load_atoms(path: Path):
    from ase.io import read

    atoms = read(str(path), index=-1)
    atoms.set_pbc([True, True, False])
    return atoms


def json_info(atoms, key: str, default: Any = None) -> Any:
    raw = atoms.info.get(key)
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Place multiple adsorbates on distinct sites of one clean slab.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--slab", required=True, help="Parent clean slab file, usually POSCAR/VASP.")
    parser.add_argument(
        "--placement",
        action="append",
        type=parse_placement,
        required=True,
        help=(
            "Adsorbate placement spec. Use ADS:SITE[:ORDINAL[:HEIGHT]] or ADS@SITE[:ORDINAL[:HEIGHT]]. "
            "Examples: CO:top:0, O:hollow:1, H:bridge:2. SITE may be top, bridge, hollow, fcc_hollow, hcp_hollow."
        ),
    )
    parser.add_argument("--backend", default="auto", choices=["auto", "acat", "catkit", "pymatgen"], help="Site-identification backend.")
    parser.add_argument("--min-site-separation", type=float, default=1.8, help="Minimum in-plane distance between selected sites in Angstrom.")
    parser.add_argument("--max-atoms", type=int, default=160, help="Maximum atom count accepted by validation.")
    parser.add_argument("--min-distance", type=float, default=0.5, help="Minimum interatomic distance threshold for validation in Angstrom.")
    parser.add_argument("--write-extxyz", action="store_true", help="Also write extxyz files and POSCAR/extxyz index mapping metadata.")
    parser.add_argument("--outdir", default="slabuilder_outputs/multi_adsorbates", help="Output directory.")
    args = parser.parse_args()

    try:
        from slabuilder.adsorption import add_multiple_adsorbates_to_slab
        from slabuilder.structure_understanding import validate_structure_packet
        from slabuilder.utils import save_structure, vasp_export_metadata
    except Exception as exc:
        raise SystemExit(
            "Could not import slabuilder. Install it in the active environment. "
            f"Original error: {exc}"
        )

    slab_path = Path(args.slab).expanduser().resolve()
    slab = load_atoms(slab_path)
    with contextlib.redirect_stdout(sys.stderr):
        atoms = add_multiple_adsorbates_to_slab(
            slab,
            args.placement,
            backend=args.backend,
            min_site_separation=args.min_site_separation,
        )
        validation = validate_structure_packet(
            atoms,
            min_distance=args.min_distance,
            max_atoms=args.max_atoms,
        )

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    placement_label = "__".join(
        safe_name(
            f"{spec.adsorbate}@{spec.site_type or 'any'}{spec.site_ordinal}"
            + (f"h{spec.height:g}" if spec.height is not None else "")
        )
        for spec in args.placement
    )
    stem = safe_name(f"{slab_path.stem}__multi__{placement_label}")
    poscar_path = save_structure(atoms, outdir / f"{stem}_POSCAR", fmt="poscar")
    vasp_export = vasp_export_metadata(atoms)
    original_to_poscar = vasp_export.get("extxyz_index_to_poscar_index") or list(range(len(atoms)))
    poscar_to_original = vasp_export.get("poscar_index_to_extxyz_index") or list(range(len(atoms)))

    multi_metadata = json_info(atoms, "multi_adsorbate_metadata_json", default=[])
    adsorbate_metadata = json_info(atoms, "adsorbate_metadata_json", default={})
    remapped_multi = [remap_placement(item, original_to_poscar) for item in multi_metadata]
    remapped_ads = remap_multi_metadata(adsorbate_metadata, original_to_poscar)
    slab_atom_count = int(atoms.info.get("slab_atom_count", 0) or len(slab))

    metadata = {
        "kind": "multi_adsorbate",
        "parent_slab": str(slab_path),
        "placements_requested": [
            {
                "adsorbate": spec.adsorbate,
                "site_type": spec.site_type,
                "site_ordinal": int(spec.site_ordinal),
                "height": spec.height,
            }
            for spec in args.placement
        ],
        "placements": remapped_multi,
        "n_atoms": len(atoms),
        "slab_atom_count": slab_atom_count,
        "slab_atom_indices": remap_indices(list(range(slab_atom_count)), original_to_poscar),
        "adsorbate_atom_count": int(atoms.info.get("adsorbate_atom_count", 0) or (len(atoms) - slab_atom_count)),
        "adsorbate_metadata": remapped_ads,
        "adsorption_site_indices": ",".join(
            str(index)
            for index in remap_indices(
                [int(x) for x in str(atoms.info.get("adsorption_site_indices", "")).split(",") if x.strip()],
                original_to_poscar,
            )
        ),
        "validation": validation,
        "paths": {
            "poscar": str(poscar_path),
        },
        "vasp_export": vasp_export,
    }
    tags = atoms.get_tags().astype(int).tolist() if "tags" in getattr(atoms, "arrays", {}) else []
    if tags:
        metadata["atom_tags"] = [int(tags[int(original_index)]) for original_index in poscar_to_original]
    if args.write_extxyz:
        extxyz_path = save_structure(atoms, outdir / f"{stem}.extxyz", fmt="extxyz")
        metadata["paths"]["extxyz"] = str(extxyz_path)

    meta_path = outdir / f"{stem}.metadata.json"
    metadata["paths"]["metadata"] = str(meta_path)
    meta_path.write_text(json.dumps(metadata, indent=2, default=json_default))

    print(json.dumps({"generated": metadata}, indent=2, default=json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
