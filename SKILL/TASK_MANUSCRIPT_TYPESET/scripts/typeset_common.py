#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
# --- How to run ---
# python3 -c "import typeset_common"
from __future__ import annotations

import argparse

from models import TypesetError
from renderers import assemble_docx_markdown

__all__ = ("TypesetError", "assemble_docx_markdown")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Small public import surface for TASK_MANUSCRIPT_TYPESET scripts. Import "
            "TypesetError and assemble_docx_markdown from this module; use "
            "export_docx.py for command-line exports."
        )
    )
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
