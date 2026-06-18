#!/usr/bin/env python3
"""Compatibility wrapper for the new HPC helper CLI."""

from vasp_submit.hpc_server.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
