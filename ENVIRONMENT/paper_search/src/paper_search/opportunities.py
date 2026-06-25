from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from typing import Any

from paper_search.config import ResearchConfig
from paper_search.models import SurfaceClaim


BASE_COVERAGE_TYPES = ("descriptor", "activity", "stability")
SELECTIVITY_REACTIONS = {"CO2RR", "NRR", "ORR"}


def build_opportunity_report(
    claims: list[SurfaceClaim],
    material: str,
    reaction: str,
    research: ResearchConfig | None = None,
) -> dict[str, Any]:
    desired_types = _desired_claim_types(reaction, research)
    grouped: dict[str, list[SurfaceClaim]] = defaultdict(list)
    coverage_counter: Counter[str] = Counter()
    for claim in claims:
        grouped[claim.surface_text].append(claim)
        coverage_counter[claim.claim_type] += 1

    surfaces = []
    suggestions = []
    for surface_text, surface_claims in grouped.items():
        claim_types = sorted({claim.claim_type for claim in surface_claims})
        missing_types = [claim_type for claim_type in desired_types if claim_type not in claim_types]
        value_count = sum(1 for claim in surface_claims if claim.value and claim.unit)
        max_confidence = max((claim.confidence for claim in surface_claims), default=0.0)
        evidence_density_score = _evidence_density_score(
            claim_count=len(surface_claims),
            claim_type_count=len(claim_types),
            value_count=value_count,
            missing_count=len(missing_types),
            max_confidence=max_confidence,
        )
        status = _surface_status(claim_types)
        surface_record = {
            "material": material,
            "reaction": reaction,
            "surface": surface_text,
            "status": status,
            "claim_count": len(surface_claims),
            "claim_types": claim_types,
            "missing_claim_types": missing_types,
            "value_count": value_count,
            "evidence_density_score": evidence_density_score,
            "paper_ids": sorted({claim.paper_id for claim in surface_claims}),
        }
        surfaces.append(surface_record)
        suggestions.extend(
            _calculation_suggestions(
                material=material,
                reaction=reaction,
                surface=surface_text,
                status=status,
                claim_types=claim_types,
                missing_types=missing_types,
                research=research,
            )
        )

    surfaces.sort(
        key=lambda item: (
            item["evidence_density_score"],
            item["claim_count"],
            item["surface"],
        ),
        reverse=True,
    )
    suggestions = _dedupe_suggestions(suggestions)
    return {
        "material": material,
        "reaction": reaction,
        "research_context": _research_context_dict(research),
        "prioritization_basis": _prioritization_basis(research),
        "surface_count": len(surfaces),
        "claim_count": len(claims),
        "claim_type_coverage": dict(sorted(coverage_counter.items())),
        "candidate_surfaces": surfaces,
        "calculation_suggestions": suggestions,
        "run_level_gaps": _run_level_gaps(claims, surfaces),
    }


def _desired_claim_types(
    reaction: str,
    research: ResearchConfig | None = None,
) -> list[str]:
    desired = list(BASE_COVERAGE_TYPES)
    research_text = _research_text(research)
    if reaction.upper() in SELECTIVITY_REACTIONS or "selectivity" in research_text:
        desired.append("selectivity")
    if any(term in research_text for term in ("durability", "stable", "stability")):
        if "stability" not in desired:
            desired.append("stability")
    return desired


def _evidence_density_score(
    claim_count: int,
    claim_type_count: int,
    value_count: int,
    missing_count: int,
    max_confidence: float,
) -> float:
    score = (
        0.35 * claim_count
        + 0.8 * claim_type_count
        + 0.5 * value_count
        + max_confidence
        - 0.2 * missing_count
    )
    return round(max(score, 0.0), 3)


def _surface_status(claim_types: list[str]) -> str:
    types = set(claim_types)
    if {"activity", "descriptor"}.issubset(types):
        return "activity_and_descriptor_evidence"
    if "activity" in types:
        return "activity_evidence_descriptor_gap"
    if "descriptor" in types:
        return "descriptor_evidence_activity_gap"
    if types.intersection({"stability", "selectivity"}):
        return "specialized_evidence_gap"
    return "surface_mention_only"


def _calculation_suggestions(
    material: str,
    reaction: str,
    surface: str,
    status: str,
    claim_types: list[str],
    missing_types: list[str],
    research: ResearchConfig | None,
) -> list[dict[str, str]]:
    present = set(claim_types)
    suggestions: list[dict[str, str]] = []
    if "descriptor" in missing_types and "activity" in present:
        suggestions.append(
            _suggestion(
                material,
                reaction,
                surface,
                "descriptor_calculation",
                "Activity evidence exists, but descriptor evidence was not extracted.",
                "Compute adsorption/free-energy descriptors for the reported active surface.",
                _research_priority("high", research, {"descriptor", "adsorption", "dft"}),
            )
        )
    if "activity" in missing_types and "descriptor" in present:
        suggestions.append(
            _suggestion(
                material,
                reaction,
                surface,
                "activity_validation",
                "Descriptor evidence exists, but activity evidence was not extracted.",
                "Prioritize literature follow-up or microkinetic screening for this surface.",
                _research_priority("high", research, {"activity", "kinetic", "screening"}),
            )
        )
    if "stability" in missing_types and present.intersection({"activity", "descriptor"}):
        suggestions.append(
            _suggestion(
                material,
                reaction,
                surface,
                "surface_stability",
                "Catalytic evidence exists, but stability evidence was not extracted.",
                "Evaluate surface stability under reaction-relevant chemical potentials.",
                _research_priority(
                    "medium",
                    research,
                    {"durability", "stable", "stability", "dissolution"},
                ),
            )
        )
    if "selectivity" in missing_types and reaction.upper() in SELECTIVITY_REACTIONS:
        suggestions.append(
            _suggestion(
                material,
                reaction,
                surface,
                "selectivity_descriptor",
                "This reaction can have competing pathways, but selectivity evidence was not extracted.",
                "Compare competing adsorbates and pathway-limiting intermediates on this surface.",
                _research_priority("medium", research, {"selectivity", "pathway"}),
            )
        )
    if status == "surface_mention_only":
        suggestions.append(
            _suggestion(
                material,
                reaction,
                surface,
                "evidence_triage",
                "Only surface mentions were extracted.",
                "Review full-text blocks before spending computation on this surface.",
                "low",
            )
        )
    return suggestions


def _suggestion(
    material: str,
    reaction: str,
    surface: str,
    calculation_type: str,
    reason: str,
    suggested_next_step: str,
    priority: str,
) -> dict[str, str]:
    return {
        "material": material,
        "reaction": reaction,
        "surface": surface,
        "calculation_type": calculation_type,
        "reason": reason,
        "suggested_next_step": suggested_next_step,
        "priority": priority,
    }


def _dedupe_suggestions(items: list[dict[str, str]]) -> list[dict[str, str]]:
    output = []
    seen: set[tuple[str, str, str, str]] = set()
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    for item in sorted(items, key=lambda entry: priority_rank.get(entry["priority"], 9)):
        key = (
            item["material"],
            item["reaction"],
            item["surface"],
            item["calculation_type"],
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _run_level_gaps(
    claims: list[SurfaceClaim],
    surfaces: list[dict[str, Any]],
) -> list[dict[str, str]]:
    if not claims:
        return [
            {
                "gap_type": "no_surface_claims",
                "description": "No surface-level evidence was extracted from available full texts.",
                "suggested_next_step": "Broaden the query, add material aliases, or improve parser coverage.",
            }
        ]
    if not surfaces:
        return [
            {
                "gap_type": "no_candidate_surfaces",
                "description": "Claims were extracted, but no candidate surface records were produced.",
                "suggested_next_step": "Inspect claim normalization and surface parsing.",
            }
        ]
    return []


def _research_priority(
    default: str,
    research: ResearchConfig | None,
    keywords: set[str],
) -> str:
    if default == "high":
        return default
    text = _research_text(research)
    if any(keyword in text for keyword in keywords):
        return "high"
    return default


def _research_text(research: ResearchConfig | None) -> str:
    if research is None:
        return ""
    parts = [
        research.prompt or "",
        research.collaboration_context or "",
        " ".join(research.decision_criteria),
        " ".join(research.target_properties),
        " ".join(research.constraints),
        " ".join(research.calculation_preferences),
    ]
    return " ".join(parts).lower()


def _research_context_dict(research: ResearchConfig | None) -> dict[str, Any]:
    if research is None:
        return {}
    return {
        key: value
        for key, value in asdict(research).items()
        if value not in (None, "", [], {})
    }


def _prioritization_basis(research: ResearchConfig | None) -> list[str]:
    basis = [
        "evidence density across extracted surface claims",
        "missing descriptor/activity/stability/selectivity claim types",
    ]
    if _research_context_dict(research):
        basis.append("user-provided research direction and collaboration context")
    return basis
