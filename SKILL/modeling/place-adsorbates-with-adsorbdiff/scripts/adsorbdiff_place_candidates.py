#!/usr/bin/env python3
"""Place a checked AdsorbDiff adsorbate on a prepared POSCAR slab."""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REPO = SKILL_DIR / "assets" / "AdsorbDiff"
DEFAULT_DB = DEFAULT_REPO / "adsorbdiff" / "placement" / "pkls" / "adsorbates.pkl"
TASK_ID = "place-adsorbates-with-adsorbdiff.place-candidates"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def json_safe(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return json_safe(value.tolist())
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def select_adsorbate_kwargs(args: argparse.Namespace, metadata: dict[str, Any]) -> dict[str, Any]:
    selected = metadata.get("adsorbate", {}).get("selected") if isinstance(metadata.get("adsorbate"), dict) else None
    selected = selected or metadata.get("selected")
    if args.adsorbate_id is not None:
        return {"adsorbate_id_from_db": args.adsorbate_id}
    if args.smiles:
        return {"adsorbate_smiles_from_db": args.smiles}
    if isinstance(selected, dict) and selected.get("id") is not None:
        return {"adsorbate_id_from_db": int(selected["id"])}
    if isinstance(selected, dict) and selected.get("smiles"):
        return {"adsorbate_smiles_from_db": selected["smiles"]}
    raise ValueError("adsorbate id or SMILES is required")


def write_lmdb(images: list[Any], lmdb_output: Path, sid: str) -> None:
    import lmdb
    import torch
    from adsorbdiff.utils.atoms_to_graphs import AtomsToGraphs

    lmdb_output.mkdir(parents=True, exist_ok=True)
    db_path = lmdb_output / "data.0000.lmdb"
    db = lmdb.open(
        str(db_path),
        map_size=1099511627776,
        subdir=False,
        meminit=False,
        map_async=True,
    )
    a2g = AtomsToGraphs(max_neigh=50, radius=6, r_energy=False, r_forces=False, r_fixed=True, r_distances=False)
    try:
        for index, atoms in enumerate(images):
            image = a2g.convert(atoms)
            image.sid = f"{sid}_{index}"
            image.fid = index
            image.tags = torch.tensor(atoms.get_tags())
            txn = db.begin(write=True)
            txn.put(f"{index}".encode("ascii"), pickle.dumps(image, protocol=-1))
            txn.commit()
        txn = db.begin(write=True)
        txn.put("length".encode("ascii"), pickle.dumps(len(images), protocol=-1))
        txn.commit()
    finally:
        db.sync()
        db.close()


def place_candidates(
    prepared_poscar: Path,
    metadata_path: Path,
    output_dir: Path,
    repo: Path,
    db_path: Path,
    adsorbate_id: int | None,
    smiles: str | None,
    mode: str,
    num_sites: int,
    num_augmentations_per_site: int,
    interstitial_gap: float,
    lmdb_output: Path | None,
    sid: str,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    artifacts: list[dict[str, str]] = []
    messages: list[str] = []
    data: dict[str, Any] = {}
    try:
        sys.path.insert(0, str(repo))
        import ase.io
        from ase.constraints import FixAtoms
        from adsorbdiff.placement import Adsorbate, AdsorbateSlabConfig, Bulk, Slab

        metadata = load_json(metadata_path)
        tags = metadata["tags"]
        slab_atoms = ase.io.read(str(prepared_poscar), format="vasp")
        if len(slab_atoms) != len(tags):
            raise ValueError("prepared POSCAR atom count does not match metadata tags")
        slab_atoms.set_tags(tags)
        slab_atoms.pbc = [True, True, False]
        slab_atoms.constraints += [FixAtoms(mask=[tag == 0 for tag in tags])]

        adsorbate_kwargs = select_adsorbate_kwargs(
            argparse.Namespace(adsorbate_id=adsorbate_id, smiles=smiles),
            metadata,
        )
        adsorbate = Adsorbate(adsorbate_db_path=str(db_path), **adsorbate_kwargs)
        bulk = Bulk(bulk_atoms=slab_atoms.copy())
        bulk.set_source_dataset_id(sid)
        slab = Slab(bulk=bulk, slab_atoms=slab_atoms, millers=(0, 0, 1), shift=0.0, top=True)
        config = AdsorbateSlabConfig(
            slab=slab,
            adsorbate=adsorbate,
            num_sites=num_sites,
            num_augmentations_per_site=num_augmentations_per_site,
            interstitial_gap=interstitial_gap,
            mode=mode,
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        candidates = []
        for index, atoms in enumerate(config.atoms_list):
            candidate_path = output_dir / f"candidate_{index:04d}.vasp"
            ase.io.write(str(candidate_path), atoms, format="vasp", direct=True, sort=False, vasp5=True)
            artifacts.append({"path": str(candidate_path), "kind": "candidate_poscar"})
            candidates.append(
                {
                    "index": index,
                    "path": str(candidate_path),
                    "site": json_safe(config.metadata_list[index]["site"]),
                    "xyz_angles": json_safe(config.metadata_list[index]["xyz_angles"]),
                }
            )

        if lmdb_output is not None:
            write_lmdb(config.atoms_list, lmdb_output, sid=sid)
            artifacts.append({"path": str(lmdb_output), "kind": "candidate_lmdb"})

        data = {
            "prepared_poscar": str(prepared_poscar),
            "metadata": str(metadata_path),
            "adsorbate": str(adsorbate),
            "mode": mode,
            "num_sites": num_sites,
            "num_augmentations_per_site": num_augmentations_per_site,
            "interstitial_gap": interstitial_gap,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "lmdb_output": str(lmdb_output) if lmdb_output else None,
        }
    except ModuleNotFoundError as exc:
        errors.append(
            {
                "type": "MissingDependency",
                "message": f"Candidate placement requires the AdsorbDiff environment dependency: {exc.name}",
            }
        )
    except Exception as exc:  # noqa: BLE001
        errors.append({"type": type(exc).__name__, "message": str(exc)})

    return {
        "status": "failure" if errors else "success",
        "task_id": TASK_ID,
        "skill": "adsorbdiff_place_candidates",
        "data": data,
        "artifacts": artifacts,
        "messages": messages,
        "errors": errors,
        "provenance": {
            "inputs": [str(prepared_poscar), str(metadata_path), str(db_path)],
            "generated_files": [item["path"] for item in artifacts],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "next_action": {
            "recommendation": "install_adsorbdiff_env" if errors else "run_adsorbdiff_sampling",
            "reason": "Candidate placement failed." if errors else "Candidate structures are available.",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-poscar", type=Path, required=False)
    parser.add_argument("--metadata", type=Path, required=False)
    parser.add_argument("--output-dir", type=Path, default=Path("adsorbdiff_candidates"))
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--adsorbate-id", type=int)
    parser.add_argument("--smiles")
    parser.add_argument("--mode", choices=["random", "heuristic", "random_site_heuristic_placement"], default="random_site_heuristic_placement")
    parser.add_argument("--num-sites", type=int, default=4)
    parser.add_argument("--num-augmentations-per-site", type=int, default=1)
    parser.add_argument("--interstitial-gap", type=float, default=0.1)
    parser.add_argument("--lmdb-output", type=Path)
    parser.add_argument("--sid", default="mesa_poscar")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        print("self-test passed")
        return 0
    if args.prepared_poscar is None or args.metadata is None:
        raise SystemExit("--prepared-poscar and --metadata are required")
    result = place_candidates(
        prepared_poscar=args.prepared_poscar.resolve(),
        metadata_path=args.metadata.resolve(),
        output_dir=args.output_dir.resolve(),
        repo=args.repo.resolve(),
        db_path=args.db_path.resolve(),
        adsorbate_id=args.adsorbate_id,
        smiles=args.smiles,
        mode=args.mode,
        num_sites=args.num_sites,
        num_augmentations_per_site=args.num_augmentations_per_site,
        interstitial_gap=args.interstitial_gap,
        lmdb_output=args.lmdb_output.resolve() if args.lmdb_output else None,
        sid=args.sid,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(json_safe(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(json_safe(result), indent=2, sort_keys=True))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
