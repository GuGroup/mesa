#!/usr/bin/env python3
"""Compatibility wrapper for gas VASP input generation.

Preferred direct command:
  python scripts/make_vasp_inputs.py --calc-type gas --poscar POSCAR --outdir gas/NH3 --submit
"""
from __future__ import annotations

import sys
from make_vasp_inputs import main

if __name__ == "__main__":
    if "--calc-type" not in sys.argv:
        sys.argv[1:1] = ["--calc-type", "gas"]
    raise SystemExit(main())
