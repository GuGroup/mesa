#!/usr/bin/env python3
"""Compatibility wrapper for slab VASP inputs.

Default mode is slab k-point convergence. For final slab or ENCUT convergence,
call make_vasp_inputs.py directly with --calc-type slab-final or slab-encut.
"""
from __future__ import annotations

import sys
from make_vasp_inputs import main

if __name__ == "__main__":
    if "--calc-type" not in sys.argv:
        sys.argv[1:1] = ["--calc-type", "slab-kconv"]
    raise SystemExit(main())
