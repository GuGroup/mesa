#!/usr/bin/env python3
"""Compatibility wrapper for slab+adsorbate VASP input generation."""
from __future__ import annotations

import sys
from make_vasp_inputs import main

if __name__ == "__main__":
    if "--calc-type" not in sys.argv:
        sys.argv[1:1] = ["--calc-type", "ads"]
    raise SystemExit(main())
