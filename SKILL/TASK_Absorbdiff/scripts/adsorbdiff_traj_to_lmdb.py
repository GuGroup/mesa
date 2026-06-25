#!/usr/bin/env python3
"""Convert AdsorbDiff sampled trajectories into a relaxation LMDB."""

from __future__ import annotations

import argparse
import json
import pickle
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


def read_atoms(path: Path, final_frame: bool = True):
    import ase.io

    fmt = "traj" if path.suffix == ".traj" else None
    if final_frame:
        return ase.io.read(str(path), index=-1, format=fmt)
    return ase.io.read(str(path), format=fmt)


def convert_to_lmdb(
    input_dir: Path,
    output_lmdb: Path,
    pattern: str,
    repo: Path,
    sid_prefix: str,
    fixed_tag: int,
    max_neighbors: int,
    radius: float,
    overwrite: bool,
) -> dict[str, Any]:
    import lmdb
    import sys
    import torch
    from ase.constraints import FixAtoms

    sys.path.insert(0, str(repo))
    from adsorbdiff.utils.atoms_to_graphs import AtomsToGraphs

    paths = sorted(input_dir.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"no input structures matched {input_dir / pattern}")

    if output_lmdb.exists():
        if not overwrite:
            raise FileExistsError(f"output already exists: {output_lmdb}")
        shutil.rmtree(output_lmdb)
    output_lmdb.mkdir(parents=True, exist_ok=True)

    db_path = output_lmdb / "data.0000.lmdb"
    db = lmdb.open(
        str(db_path),
        map_size=1099511627776,
        subdir=False,
        meminit=False,
        map_async=True,
    )
    a2g = AtomsToGraphs(
        max_neigh=max_neighbors,
        radius=radius,
        r_energy=False,
        r_forces=False,
        r_fixed=True,
        r_distances=False,
    )

    entries: list[dict[str, Any]] = []
    try:
        for index, path in enumerate(paths):
            atoms = read_atoms(path, final_frame=True)
            tags = np.array(atoms.get_tags(), dtype=int)
            if len(tags) != len(atoms):
                raise ValueError(f"tag count mismatch for {path}")
            atoms.set_constraint(FixAtoms(mask=(tags == fixed_tag).tolist()))
            image = a2g.convert(atoms)
            image.sid = f"{sid_prefix}_{index}"
            image.fid = index
            image.tags = torch.tensor(tags, dtype=torch.long)
            txn = db.begin(write=True)
            txn.put(f"{index}".encode("ascii"), pickle.dumps(image, protocol=-1))
            txn.commit()
            entries.append(
                {
                    "index": index,
                    "sid": image.sid,
                    "source": str(path),
                    "num_atoms": len(atoms),
                    "formula": atoms.get_chemical_formula(),
                    "tag_counts": {
                        str(tag): int((tags == tag).sum())
                        for tag in sorted(set(tags.tolist()))
                    },
                }
            )
        txn = db.begin(write=True)
        txn.put("length".encode("ascii"), pickle.dumps(len(entries), protocol=-1))
        txn.commit()
    finally:
        db.sync()
        db.close()

    summary = {
        "status": "success",
        "input_dir": str(input_dir),
        "output_lmdb": str(output_lmdb),
        "db_path": str(db_path),
        "count": len(entries),
        "entries": entries,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-lmdb", type=Path, required=True)
    parser.add_argument("--pattern", default="*.traj")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "assets" / "AdsorbDiff",
    )
    parser.add_argument("--sid-prefix", default="adsorbdiff_gemnet")
    parser.add_argument("--fixed-tag", type=int, default=0)
    parser.add_argument("--max-neighbors", type=int, default=50)
    parser.add_argument("--radius", type=float, default=6.0)
    parser.add_argument("--num-workers", type=int, default=1, help="Accepted for workflow compatibility; conversion is serial.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--summary", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = convert_to_lmdb(
        input_dir=args.input_dir.resolve(),
        output_lmdb=args.output_lmdb.resolve(),
        pattern=args.pattern,
        repo=args.repo.resolve(),
        sid_prefix=args.sid_prefix,
        fixed_tag=args.fixed_tag,
        max_neighbors=args.max_neighbors,
        radius=args.radius,
        overwrite=args.overwrite,
    )
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
