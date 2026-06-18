from __future__ import annotations

import copy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def base_spec() -> dict:
    return {
        "schema_version": 1,
        "job_name": "si_relax_001",
        "task": "slab",
        "project": "screening",
        "structure": {
            "format": "poscar",
            "content": "Si\n1.0\n",
        },
        "vasp": {
            "xc": "PBE",
            "kpts": [4, 4, 4],
            "gamma": True,
            "parameters": {
                "encut": 520,
                "ediff": 1.0e-5,
            },
        },
        "queue": {
            "preset": "auto",
            "submit": True,
        },
    }


def spec_with(**updates: object) -> dict:
    spec = copy.deepcopy(base_spec())
    spec.update(updates)
    return spec


def hpc_config(tmp_path: Path | None = None) -> dict:
    root = tmp_path / "hpc-root" if tmp_path else Path("/tmp/vasp-submit-test")
    return {
        "trusted_roots": [str(root)],
        "default_project_root": str(root),
        "default_queue": {
            "scheduler": "sge",
            "preset": "auto",
        },
        "vasp_pp_path": "/opt/vasp",
        "vasp_pp_version": None,
    }
