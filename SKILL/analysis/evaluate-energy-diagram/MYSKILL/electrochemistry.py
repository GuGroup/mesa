"""Electrochemical reaction-coordinate utilities."""

from __future__ import annotations

from typing import Any, Sequence

from .chemistry import canonical_label, hydrogen_count, oxygen_count, species_core

ELECTROCHEMICAL_REFERENCE_PATH = "MYSKILL/electrochemical.md"
ELECTROCHEMICAL_REFERENCE_RULE = (
    "If an LLM contributes interpretation, reaction classification, selectivity discussion, "
    "or overpotential/PDS wording, it must read and follow MYSKILL/electrochemical.md first. "
    "In particular, do not classify pure adsorption/desorption energy as overpotential."
)

ELECTROCHEMICAL_PDS_CLASSES = {"electrochemical", "unknown"}
CHEMICAL_ONLY_CLASSES = {
    "adsorption",
    "desorption",
    "adsorption_or_surface_formation",
    "desorption_or_surface_cleanup",
}


def classify_transition(start: str, end: str) -> str:
    """Classify an elementary step from labels only.

    This conservative label-based classifier is intended to prevent a common
    error: reporting pure adsorption/desorption steps as electrochemical
    overpotential. It cannot replace a fully specified elementary equation.
    """
    start = canonical_label(start)
    end = canonical_label(end)
    if start == end:
        return "duplicate"
    if start == "*" and end.startswith("*"):
        return "adsorption_or_surface_formation"
    if start.startswith("*") and end == "*":
        return "desorption_or_surface_cleanup"
    if not start.startswith("*") and end.startswith("*") and species_core(start) == species_core(end):
        return "adsorption"
    if start.startswith("*") and not end.startswith("*") and species_core(start) == species_core(end):
        return "desorption"
    if hydrogen_count(end) != hydrogen_count(start) or oxygen_count(end) != oxygen_count(start):
        return "electrochemical"
    return "unknown"


def transitions(steps: list[str], series: list[float]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index in range(1, len(steps)):
        start = steps[index - 1]
        end = steps[index]
        label = f"{start} -> {end}"
        delta_g = series[index] - series[index - 1]
        classification = classify_transition(start, end)
        output.append(
            {
                "label": label,
                "start": start,
                "end": end,
                "delta_g_ev": delta_g,
                # Backward-compatible alias used by the original TASK2 script.
                "delta_g": delta_g,
                "classification": classification,
                "included_for_pds": classification in ELECTROCHEMICAL_PDS_CLASSES,
            }
        )
    return output


def find_step_index(steps: Sequence[str], *candidate_labels: str) -> int | None:
    candidate_set = {canonical_label(label) for label in candidate_labels}
    for index, step in enumerate(steps):
        if canonical_label(step) in candidate_set:
            return index
    return None


def series_value(series: Sequence[float], steps: Sequence[str], *labels: str) -> float | None:
    index = find_step_index(steps, *labels)
    if index is None:
        return None
    return float(series[index])


def largest_positive_transition(
    transition_rows: Sequence[dict[str, Any]],
    include_classifications: set[str] | None = None,
) -> dict[str, Any] | None:
    if include_classifications is None:
        candidates = [transition for transition in transition_rows if transition["delta_g_ev"] > 0]
    else:
        candidates = [
            transition
            for transition in transition_rows
            if transition["delta_g_ev"] > 0 and transition.get("classification") in include_classifications
        ]
    return max(candidates, key=lambda item: item["delta_g_ev"], default=None)


def llm_reference_notice() -> dict[str, str]:
    return {
        "must_read_first": ELECTROCHEMICAL_REFERENCE_PATH,
        "rule": ELECTROCHEMICAL_REFERENCE_RULE,
    }
