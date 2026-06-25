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
from renderers import assemble_docx_markdown, assemble_typst

__all__ = ("TypesetError", "assemble_docx_markdown", "assemble_typst")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Small public import surface for TASK_MANUSCRIPT_TYPESET scripts. Import "
            "TypesetError, assemble_typst, and assemble_docx_markdown from this module; "
            "use build_typst.py or export_docx.py for command-line builds."
        )
    )
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
