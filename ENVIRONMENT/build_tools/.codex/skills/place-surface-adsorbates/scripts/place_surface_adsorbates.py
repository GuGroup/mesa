#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
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


def load_atoms(path: Path, *, backend: str = "auto"):
    from ase.io import read

    atoms = read(path)
    name = path.name.upper()
    is_vasp = name in {"POSCAR", "CONTCAR"} or path.suffix.lower() in {
        ".vasp", ".poscar"
    }
    if str(backend).strip().lower() != "weighted_alpha" or is_vasp:
        atoms.set_pbc([True, True, False])
    return atoms


def weighted_alpha_config_from_args(args):
    if args.backend != "weighted_alpha":
        return None
    explicit_values = (
        args.weighted_alpha_executable,
        args.weighted_alpha_radius_file,
        args.weighted_alpha_expected_sha256,
        args.weighted_alpha_expected_radius_sha256,
        args.weighted_alpha_runtime_sha256_manifest,
        args.weighted_alpha_expected_runtime_manifest_sha256,
        args.weighted_alpha_alpha_factor,
        args.weighted_alpha_probe_radius,
        args.weighted_alpha_placement_gap,
        args.weighted_alpha_placement_step,
        args.weighted_alpha_placement_max_distance,
        args.weighted_alpha_timeout_s,
    )
    if (
        not any(value is not None for value in explicit_values)
        and not args.weighted_alpha_allow_unpinned_runtime
    ):
        return None
    if not args.weighted_alpha_executable and not args.weighted_alpha_radius_file:
        manual_pin_values = (
            args.weighted_alpha_expected_sha256,
            args.weighted_alpha_expected_radius_sha256,
            args.weighted_alpha_runtime_sha256_manifest,
            args.weighted_alpha_expected_runtime_manifest_sha256,
        )
        if any(value is not None for value in manual_pin_values) or args.weighted_alpha_allow_unpinned_runtime:
            raise SystemExit(
                "Manual weighted-alpha pins/unsafe mode require both "
                "--weighted-alpha-executable and --weighted-alpha-radius-file."
            )
        from slabuilder.weighted_alpha_backend import resolve_weighted_alpha_config

        env = dict(os.environ)
        numeric_overrides = {
            "MESA_WEIGHTED_ALPHA_ALPHA_FACTOR": args.weighted_alpha_alpha_factor,
            "MESA_WEIGHTED_ALPHA_PROBE_RADIUS": args.weighted_alpha_probe_radius,
            "MESA_WEIGHTED_ALPHA_PLACEMENT_GAP": args.weighted_alpha_placement_gap,
            "MESA_WEIGHTED_ALPHA_PLACEMENT_STEP": args.weighted_alpha_placement_step,
            "MESA_WEIGHTED_ALPHA_PLACEMENT_MAX_DISTANCE": args.weighted_alpha_placement_max_distance,
            "MESA_WEIGHTED_ALPHA_TIMEOUT_S": args.weighted_alpha_timeout_s,
        }
        for key, value in numeric_overrides.items():
            if value is not None:
                env[key] = str(value)
        return resolve_weighted_alpha_config(environ=env)
    if not args.weighted_alpha_executable or not args.weighted_alpha_radius_file:
        raise SystemExit(
            "Explicit weighted-alpha configuration requires both "
            "--weighted-alpha-executable and --weighted-alpha-radius-file."
        )
    from slabuilder.weighted_alpha_backend import WeightedAlphaConfig

    return WeightedAlphaConfig(
        executable=Path(args.weighted_alpha_executable).expanduser().resolve(),
        radius_file=Path(args.weighted_alpha_radius_file).expanduser().resolve(),
        alpha_factor=(
            args.weighted_alpha_alpha_factor
            if args.weighted_alpha_alpha_factor is not None
            else 3.5
        ),
        probe_radius=(
            args.weighted_alpha_probe_radius
            if args.weighted_alpha_probe_radius is not None
            else 1.52
        ),
        placement_gap=(
            args.weighted_alpha_placement_gap
            if args.weighted_alpha_placement_gap is not None
            else 0.5
        ),
        placement_step=(
            args.weighted_alpha_placement_step
            if args.weighted_alpha_placement_step is not None
            else 0.0125
        ),
        placement_max_distance=(
            args.weighted_alpha_placement_max_distance
            if args.weighted_alpha_placement_max_distance is not None
            else 8.0
        ),
        timeout_s=(
            args.weighted_alpha_timeout_s
            if args.weighted_alpha_timeout_s is not None
            else 120.0
        ),
        expected_sha256=args.weighted_alpha_expected_sha256,
        expected_radius_sha256=args.weighted_alpha_expected_radius_sha256,
        runtime_sha256_manifest=(
            Path(args.weighted_alpha_runtime_sha256_manifest).expanduser().resolve()
            if args.weighted_alpha_runtime_sha256_manifest
            else None
        ),
        expected_runtime_manifest_sha256=(
            args.weighted_alpha_expected_runtime_manifest_sha256
        ),
        allow_unpinned_runtime=args.weighted_alpha_allow_unpinned_runtime,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Identify sites and place adsorbates with slabuilder.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--slab", required=True, help="Parent slab file, preferably extxyz.")
    parser.add_argument("--adsorbate", required=True, help='Adsorbate label, name, or "smiles:<SMILES>".')
    parser.add_argument("--max-sites", type=int, default=3, help="Maximum adsorption-site candidates to place.")
    parser.add_argument("--height", type=float, help="Legacy-backend adsorbate height in Angstrom; ignored for weighted-alpha contact-anchor placement.")
    parser.add_argument("--backend", default="auto", choices=["auto", "acat", "catkit", "pymatgen", "weighted_alpha"], help="Site-identification backend.")
    parser.add_argument("--weighted-alpha-executable", help="Optional pinned executable override; omit with the radius path to use the trusted private Release.")
    parser.add_argument("--weighted-alpha-radius-file", help="Optional radius-table override paired with the executable.")
    parser.add_argument("--weighted-alpha-expected-sha256", help="Required executable SHA-256 pin unless unsafe opt-out is selected.")
    parser.add_argument("--weighted-alpha-expected-radius-sha256", help="Required radius-table SHA-256 pin unless unsafe opt-out is selected.")
    parser.add_argument("--weighted-alpha-runtime-sha256-manifest", help="JSON manifest pinning the complete adjacent runtime artifact set.")
    parser.add_argument("--weighted-alpha-expected-runtime-manifest-sha256", help="Required SHA-256 pin for the runtime manifest itself unless unsafe opt-out is selected.")
    parser.add_argument("--weighted-alpha-allow-unpinned-runtime", action="store_true", help="UNSAFE local-development opt-out from executable/radius/DLL pins.")
    parser.add_argument("--weighted-alpha-alpha-factor", type=float, help="Weighted-alpha factor (default 3.5).")
    parser.add_argument("--weighted-alpha-probe-radius", type=float, help="Contact-anchor radius in Angstrom (default 1.52; compatibility option name).")
    parser.add_argument("--weighted-alpha-placement-gap", type=float, help="Engine placement gap in Angstrom (default 0.5).")
    parser.add_argument("--weighted-alpha-placement-step", type=float, help="Engine placement search step in Angstrom (default 0.0125).")
    parser.add_argument("--weighted-alpha-placement-max-distance", type=float, help="Engine placement search limit in Angstrom (default 8.0).")
    parser.add_argument("--weighted-alpha-timeout-s", type=float, help="Engine timeout in seconds (default 120).")
    parser.add_argument("--max-atoms", type=int, default=200, help="Maximum atom count accepted by validation.")
    parser.add_argument("--min-distance", type=float, default=0.5, help="Minimum interatomic distance threshold for validation in Angstrom.")
    parser.add_argument("--outdir", default="slabuilder_outputs/adsorbates", help="Output directory for extxyz, POSCAR, and metadata files.")
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
    slab = load_atoms(slab_path, backend=args.backend)
    weighted_alpha_config = weighted_alpha_config_from_args(args)
    candidates = generate_all_adsorption_structures(
        slab,
        args.adsorbate,
        max_sites=args.max_sites,
        height=args.height,
        backend=args.backend,
        weighted_alpha_config=weighted_alpha_config,
    )
    if not candidates:
        raise SystemExit("No adsorption candidates were generated.")

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    stem_base = safe_name(f"{slab_path.stem}_{args.adsorbate}")
    for index, (site, atoms) in enumerate(candidates):
        stem = f"{stem_base}_site{index}_{safe_name(site.site_type)}"
        extxyz_path = save_structure(atoms, outdir / f"{stem}.extxyz", fmt="extxyz")
        poscar_path = save_structure(atoms, outdir / f"{stem}_POSCAR", fmt="poscar")
        validation = validate_structure_packet(atoms, min_distance=args.min_distance, max_atoms=args.max_atoms)
        site_graph = analyze_surface_sites_packet(
            atoms,
            structure_id=f"ads:{stem}",
            target_adsorbate=args.adsorbate,
            backend=("weighted_alpha" if args.backend == "weighted_alpha" else "acat"),
            weighted_alpha_config=weighted_alpha_config,
        )
        site_payload = {
            "site_type": site.site_type,
            "position": site.position,
            "surface_atom_idx": site.surface_atom_idx,
            "priority": site.priority,
            "placement_method": site.placement_method,
            "sources": site.sources,
            "validation_score": site.validation_score,
            "validation_notes": site.validation_notes,
        }
        if site.metadata:
            site_payload["metadata"] = site.metadata
        metadata = {
            "kind": "adsorbate",
            "parent_slab": str(slab_path),
            "adsorbate": args.adsorbate,
            "candidate_index": index,
            "site": site_payload,
            "n_atoms": len(atoms),
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
            "paths": {
                "extxyz": str(extxyz_path),
                "poscar": str(poscar_path),
            },
            "vasp_export": vasp_export_metadata(atoms),
        }
        meta_path = outdir / f"{stem}.metadata.json"
        meta_path.write_text(
            json.dumps(metadata, indent=2, default=json_default, allow_nan=False)
        )
        metadata["paths"]["metadata"] = str(meta_path)
        records.append(metadata)

    print(
        json.dumps(
            {"generated": records}, indent=2, default=json_default, allow_nan=False
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
