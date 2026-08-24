#!/usr/bin/env python3
"""Compatibility wrapper for the uploaded Co/Ni oxide slab+adsorbate style.

This profile is marked as needing literature verification before publication use.
Use --allow-unverified-profile only when the user/lab explicitly wants the uploaded
Co/Ni LDA+U and magnetic-moment rules.
"""
from __future__ import annotations

import sys
from make_vasp_inputs import main

if __name__ == "__main__":
    if "--calc-type" not in sys.argv:
        sys.argv[1:1] = ["--calc-type", "oxide-ads", "--allow-unverified-profile"]
    if "--scan-poscars" not in sys.argv and "--poscar" not in sys.argv:
        sys.argv.extend(["--scan-poscars", "POSCAR*"])
    raise SystemExit(main())
