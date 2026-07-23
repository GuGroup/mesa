#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
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
    if args.site_backend != "weighted_alpha":
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


def load_record(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    return json.loads(Path(path).expanduser().read_text())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only slabuilder site and fragment inspection.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--structure", required=True, help="Structure file readable by ASE.")
    parser.add_argument("--metadata", help="Optional metadata JSON record.")
    parser.add_argument("--structure-id", help="Optional identifier to include in the output packet.")
    parser.add_argument("--min-distance", type=float, default=0.5, help="Minimum interatomic distance threshold for validation in Angstrom.")
    parser.add_argument("--max-atoms", type=int, default=200, help="Maximum atom count accepted by validation.")
    parser.add_argument("--target-adsorbate", default="H", help="Adsorbate label used for site matching and local transform proposals.")
    parser.add_argument("--site-backend", default="acat", choices=["acat", "auto", "catkit", "pymatgen", "weighted_alpha"], help="Backend used to rebuild adsorption sites.")
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
    parser.add_argument("--max-site-distance", type=float, default=3.5, help="Maximum neighbor site distance in Angstrom.")
    parser.add_argument("--neighbor-shell", type=int, default=2, help="Maximum neighbor shell to include.")
    parser.add_argument("--max-sites", type=int, default=120, help="Maximum site rows included in the output packet.")
    parser.add_argument("--max-edges", type=int, default=240, help="Maximum site-neighbor edges included in the output packet.")
    parser.add_argument("--selection-intent", help="Atom selection intent: adsorbate, fixed_slab, relaxable_slab, top_layers, bottom_layers, explicit, tag, element, or all.")
    parser.add_argument("--selection-indices", nargs="*", type=int, help="Explicit atom indices used when --selection-intent explicit.")
    parser.add_argument("--selection-layers", type=int, default=1, help="Number of top/bottom z-layers selected for layer-based selection intents.")
    parser.add_argument("--selection-tag", type=int, help="ASE tag value used when --selection-intent tag.")
    parser.add_argument("--selection-element", help="Element symbol used when --selection-intent element.")
    parser.add_argument("--include-fragments", action="store_true", help="Include covalent adsorbate fragment analysis.")
    parser.add_argument("--transform-type", choices=["diffusion", "dissociation"], help="Read-only local transform proposal type.")
    parser.add_argument("--moving-fragment", help="Formula for the moving fragment in dissociation proposals.")
    parser.add_argument("--remaining-fragment", help="Formula for the remaining fragment in dissociation proposals.")
    parser.add_argument("--break-bond", nargs=2, metavar=("A", "B"), help="Element symbols for the bond to break in dissociation proposals.")
    parser.add_argument("--max-transform-candidates", type=int, default=20, help="Maximum local transform proposal rows.")
    parser.add_argument("--out", help="Optional JSON output path. Output is always also printed to stdout.")
    args = parser.parse_args()

    try:
        from slabuilder.structure_understanding import (
            analyze_structure_packet,
            analyze_surface_sites_packet,
            identify_fragments_packet,
            propose_atom_selection_packet,
            propose_local_transform_packet,
            validate_structure_packet,
        )
    except Exception as exc:
        raise SystemExit(
            "Could not import slabuilder. Install it in the active environment. "
            f"Original error: {exc}"
        )

    structure_path = Path(args.structure).expanduser().resolve()
    atoms = load_atoms(structure_path, backend=args.site_backend)
    record = load_record(args.metadata)
    structure_id = args.structure_id or record.get("id") or structure_path.stem
    weighted_alpha_config = weighted_alpha_config_from_args(args)

    output: dict[str, Any] = {
        "structure_id": structure_id,
        "path": str(structure_path),
        "analysis": analyze_structure_packet(atoms, record=record, structure_id=structure_id),
        "validation": validate_structure_packet(
            atoms,
            record=record,
            min_distance=args.min_distance,
            max_atoms=args.max_atoms,
        ),
        "surface_sites": analyze_surface_sites_packet(
            atoms,
            record=record,
            structure_id=structure_id,
            backend=args.site_backend,
            target_adsorbate=args.target_adsorbate,
            max_site_distance=args.max_site_distance,
            neighbor_shell=args.neighbor_shell,
            max_sites=args.max_sites,
            max_edges=args.max_edges,
            weighted_alpha_config=weighted_alpha_config,
        ),
    }

    if args.selection_intent:
        output["selection"] = propose_atom_selection_packet(
            atoms,
            record=record,
            structure_id=structure_id,
            intent=args.selection_intent,
            indices=args.selection_indices,
            n_layers=args.selection_layers,
            tag=args.selection_tag,
            element=args.selection_element,
        )

    if args.include_fragments:
        output["fragments"] = identify_fragments_packet(
            atoms,
            record=record,
            structure_id=structure_id,
        )

    if args.transform_type:
        output["local_transform_proposal"] = propose_local_transform_packet(
            atoms,
            record=record,
            structure_id=structure_id,
            transform_type=args.transform_type,
            moving_fragment=args.moving_fragment,
            remaining_fragment=args.remaining_fragment,
            break_bond=args.break_bond,
            target_adsorbate=args.target_adsorbate,
            max_site_distance=args.max_site_distance,
            neighbor_shell=args.neighbor_shell,
            max_candidates=args.max_transform_candidates,
            backend=args.site_backend,
            weighted_alpha_config=weighted_alpha_config,
        )
        output["note"] = "Read-only proposal only; no endpoint pair was generated."

    text = json.dumps(output, indent=2, default=json_default, allow_nan=False)
    if args.out:
        Path(args.out).expanduser().write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
