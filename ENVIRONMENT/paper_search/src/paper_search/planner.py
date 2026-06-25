from __future__ import annotations

import re

from paper_search.config import ResearchConfig


STOPWORDS = {
    "about",
    "after",
    "also",
    "based",
    "between",
    "candidate",
    "collaboration",
    "compute",
    "could",
    "direction",
    "during",
    "focus",
    "from",
    "looking",
    "material",
    "materials",
    "need",
    "paper",
    "papers",
    "project",
    "research",
    "should",
    "study",
    "target",
    "their",
    "there",
    "these",
    "want",
    "where",
    "which",
    "with",
}


def build_queries(
    material: str,
    reaction: str,
    extra_terms: list[str] | None = None,
    research: ResearchConfig | None = None,
    field_scope: str = "off",
) -> list[str]:
    reaction_terms = _reaction_terms(reaction)
    surface_terms = [
        "surface",
        "facet",
        "Miller index",
        "exposed plane",
        "slab",
        "electrocatalyst",
    ]
    extras = extra_terms or []
    queries: list[str] = []
    for reaction_term in reaction_terms:
        queries.append(f"{material} {reaction_term} surface facet")
        queries.append(f"{material} {reaction_term} Miller index")
        queries.append(f"{material} {reaction_term} electrocatalyst surface")
    if extras:
        queries.append(" ".join([material, reaction, *surface_terms[:2], *extras]))
    research_terms = _research_terms(research)
    if research_terms:
        queries.append(" ".join([material, reaction, *research_terms[:6]]))
    queries.extend(_field_queries(reaction, field_scope))
    return _dedupe(queries)


def _field_queries(reaction: str, field_scope: str) -> list[str]:
    """Reaction-centric, material-agnostic queries (Tier B).

    Find transferable descriptor/method evidence for the same reaction on OTHER
    systems. ``off`` adds nothing; ``reaction`` adds descriptor/method-oriented
    field queries; ``reaction+family`` also broadens to catalyst families.
    """
    scope = (field_scope or "off").strip().lower()
    if scope in ("off", "none", "", "false"):
        return []
    term = _reaction_terms(reaction)[0]
    queries = [
        f"{term} adsorption free energy descriptor DFT",
        f"{term} activity descriptor volcano scaling relation",
        f"{term} d-band center electrocatalyst DFT",
        f"{term} surface facet descriptor computational screening",
    ]
    if scope in ("reaction+family", "family", "reaction_family"):
        for family in ("transition metal oxide", "metal alloy", "single atom catalyst"):
            queries.append(f"{family} {term} descriptor DFT slab")
    return queries


def _reaction_terms(reaction: str) -> list[str]:
    upper = reaction.upper()
    aliases = {
        "HER": ["HER", "hydrogen evolution reaction"],
        "ORR": ["ORR", "oxygen reduction reaction"],
        "OER": ["OER", "oxygen evolution reaction"],
        "CO2RR": ["CO2RR", "carbon dioxide reduction"],
        "NRR": ["NRR", "nitrogen reduction reaction"],
    }
    return aliases.get(upper, [reaction])


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _research_terms(research: ResearchConfig | None) -> list[str]:
    if research is None:
        return []
    text_parts = [
        research.prompt or "",
        research.collaboration_context or "",
        " ".join(research.decision_criteria),
        " ".join(research.target_properties),
        " ".join(research.constraints),
        " ".join(research.calculation_preferences),
    ]
    text = " ".join(text_parts).lower()
    terms = []
    for token in re.findall(r"[a-z][a-z0-9_+\-]{3,}", text):
        if token in STOPWORDS:
            continue
        if token not in terms:
            terms.append(token)
    return terms[:12]
