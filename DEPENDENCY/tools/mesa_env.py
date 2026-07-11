#!/usr/bin/env python3
"""Bootstrap and preflight helper for MESA runtime environments.

This file is intentionally a thin CLI entry point. Implementation lives in
`mesa_env_support/` so bootstrap, runtime checks, non-deterministic analysis,
status notifications, and runtime plan execution stay independently readable.
"""

from __future__ import annotations

from mesa_env_support.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
