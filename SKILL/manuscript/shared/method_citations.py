"""Pure policy helpers for canonical Methods citation candidates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


METHODS_SECTION_IDS = frozenset(
    {
        "model_construction",
        "geometry_optimization",
        "vibrational_free_energy_corrections",
        "electrochemical_free_energy_formalism",
    }
)


def is_methods_section(section_id: str) -> bool:
    """Return whether a section belongs to the supported Methods workflow."""
    return section_id in METHODS_SECTION_IDS


def backend_allows_family(mode: str, family: str) -> bool:
    """Return whether a canonical reference family is allowed by a backend."""
    if family in {"", "general"}:
        return True
    if mode == "uma_mlip":
        return family != "dft"
    if mode == "dft":
        return family != "uma_mlip"
    return mode == "hybrid"


def eligible_canonical_records(
    records: Sequence[Mapping[str, Any]],
    backend_policy: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return backend-compatible canonical records without scoring them."""
    policy = backend_policy or {}
    mode = str(policy.get("mode") or "unknown")
    forbidden = {
        str(value)
        for value in policy.get("forbidden_citation_keys", [])
        if value is not None
    }
    eligible: list[dict[str, Any]] = []
    for record in records:
        if record.get("source_role") != "canonical_method_reference":
            continue
        key = str(record.get("citation_key") or "")
        family = str(record.get("backend_family") or "general")
        if not key or key in forbidden or not backend_allows_family(mode, family):
            continue
        eligible.append(dict(record))
    return eligible


def canonical_candidate(record: Mapping[str, Any]) -> dict[str, Any]:
    """Project one canonical record into the bounded LLM candidate contract."""
    return {
        "source_id": record.get("source_id"),
        "citation_key": record.get("citation_key"),
        "source_role": "canonical_method_reference",
        "candidate_kind": "canonical_method",
        "title": record.get("title"),
        "authors": list(record.get("authors", [])),
        "year": record.get("year"),
        "doi": record.get("doi"),
        "url": record.get("url"),
        "raw_reference": record.get("raw_reference"),
        "method_tags": list(record.get("method_tags", [])),
        "backend_family": record.get("backend_family", "general"),
        "citation_guidance": record.get("citation_guidance", ""),
        "evidence_snippet": record.get("title") or record.get("raw_reference") or "",
    }
