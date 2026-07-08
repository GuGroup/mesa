"""Guidance for optional LLM-assisted interpretation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .electrochemistry import ELECTROCHEMICAL_REFERENCE_PATH, ELECTROCHEMICAL_REFERENCE_RULE


def llm_guidance_payload() -> dict[str, Any]:
    """Return machine-readable guidance for any LLM interpretation layer.

    The deterministic evaluator does not call an LLM. This payload is included
    in outputs and SKILL instructions so that any future LLM-assisted layer
    consults electrochemical.md before making electrochemical judgments.
    """
    return {
        "llm_interpretation_allowed": "optional_downstream_only",
        "must_read_reference_before_interpretation": ELECTROCHEMICAL_REFERENCE_PATH,
        "priority_rule": ELECTROCHEMICAL_REFERENCE_RULE,
        "forbidden_overclaim": "Do not label pure adsorption/desorption or other non-electrochemical step energies as overpotential.",
    }


def read_electrochemical_reference(skill_root: Path | None = None) -> str:
    """Load electrochemical.md for a caller that explicitly performs LLM review."""
    if skill_root is None:
        skill_root = Path(__file__).resolve().parents[1]
    path = skill_root / ELECTROCHEMICAL_REFERENCE_PATH
    return path.read_text(encoding="utf-8")
