#!/usr/bin/env python3
"""No-op external tool wrapper for evaluate-energy-diagram.

The current implementation uses only the Python standard library.  This module
keeps the MESA skill layout extensible for future VASP parsers, databases, or
literature/ontology services.
"""

from __future__ import annotations

from typing import Any


def run(input_data: dict, context: dict | None = None) -> dict[str, Any]:
    return {
        "status": "success",
        "external_tool": "none",
        "data": {},
        "messages": ["No external tools are required for the current implementation."],
        "provenance": {"external_calls": []},
    }
