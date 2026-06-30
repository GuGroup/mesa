"""Standard MESA output helpers."""

from __future__ import annotations

from typing import Any

from .constants import SKILL_NAME, TASK_ID


def standard_output(status: str = "success") -> dict[str, Any]:
    return {
        "status": status,
        "task_id": TASK_ID,
        "skill": SKILL_NAME,
        "data": {},
        "artifacts": [],
        "messages": [],
        "errors": [],
        "provenance": {
            "inputs": [],
            "external_calls": [],
            "generated_files": [],
        },
        "next_action": {
            "recommendation": "continue",
            "reason": "Reaction energy evaluation completed.",
        },
    }
