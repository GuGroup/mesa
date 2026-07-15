#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import runpy


def main() -> None:
    repo_root = Path(__file__).resolve().parents[6]
    target = repo_root / "SKILL/modeling/build-slab-models/scripts/build_slab_model.py"
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
