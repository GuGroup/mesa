from __future__ import annotations

import re
from pathlib import Path

from paper_search.models import SurfaceClaim
from paper_search.utils import read_json, write_json


# Parenthesized Miller-index-like token: a digit, then digits / signs (-, −) /
# bar marks (macron, combining overline) / spaces, ending in a digit or bar.
# Matches (110), (1-10), (0001), (1̄10), (10 -10); kept intentionally permissive
# (block-level surface-keyword gating below filters out unrelated parentheses).
_MILLER_BODY = r"[0-9](?:[0-9\-−¯̄̅\s]{0,15}[0-9¯̄̅])?"
SURFACE_RE = re.compile(
    r"(?:(?:surface|facet|plane|termination|exposed)\s+)?"
    r"(\(\s*" + _MILLER_BODY + r"\s*\))",
    re.I,
)
VALUE_RE = re.compile(
    r"(?P<value>[+-]?\d+(?:\.\d+)?)\s*"
    r"(?P<unit>eV|mV|V|mA\s*cm[- ]?2|A\s*g[- ]?1|kJ\s*mol[- ]?1)",
    re.I,
)


REACTION_ALIASES = {
    "HER": ["HER", "hydrogen evolution", "hydrogen evolution reaction"],
    "ORR": ["ORR", "oxygen reduction", "oxygen reduction reaction"],
    "OER": ["OER", "oxygen evolution", "oxygen evolution reaction"],
    "CO2RR": ["CO2RR", "CO2 reduction", "carbon dioxide reduction"],
    "NRR": ["NRR", "nitrogen reduction", "nitrogen reduction reaction"],
}


def extract_surface_claims(
    blocks_path: Path,
    material: str,
    reaction: str,
    output_dir: Path,
) -> list[SurfaceClaim]:
    blocks = read_json(blocks_path)
    material_terms = _material_terms(material)
    reaction_terms = [term.lower() for term in REACTION_ALIASES.get(reaction.upper(), [reaction])]
    claims: list[SurfaceClaim] = []
    for block in blocks:
        text = block.get("text") or ""
        lowered = text.lower()
        if not any(term.lower() in lowered for term in material_terms):
            continue
        if not any(term in lowered for term in reaction_terms):
            continue
        if not _surface_context_present(lowered):
            continue
        for match in SURFACE_RE.finditer(text):
            evidence = _sentence_window(text, match.start(), match.end())
            value_match = VALUE_RE.search(evidence)
            claims.append(
                SurfaceClaim(
                    paper_id=block["paper_id"],
                    material=material,
                    reaction=reaction,
                    surface_text=_normalize_surface(match.group(1)),
                    evidence_text=evidence,
                    claim_type=_claim_type(evidence),
                    section=block.get("section"),
                    figure_or_table=block.get("figure_or_table"),
                    confidence=_confidence(evidence, block.get("block_type")),
                    value=value_match.group("value") if value_match else None,
                    unit=_clean_unit(value_match.group("unit")) if value_match else None,
                )
            )
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "surface_claims.json", [claim.to_dict() for claim in claims])
    return claims


def _material_terms(material: str) -> list[str]:
    compact = material.replace(" ", "")
    return sorted({material, compact, compact.lower()}, key=len, reverse=True)


def _surface_context_present(text: str) -> bool:
    return bool(
        SURFACE_RE.search(text)
        and any(
            term in text
            for term in (
                "surface",
                "facet",
                "plane",
                "miller",
                "termination",
                "exposed",
                "slab",
            )
        )
    )


def _sentence_window(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind(";", 0, start), text.rfind("\n", 0, start))
    right_candidates = [
        index for index in (text.find(".", end), text.find(";", end), text.find("\n", end)) if index != -1
    ]
    right = min(right_candidates) if right_candidates else min(len(text), end + 350)
    return re.sub(r"\s+", " ", text[left + 1 : right + 1]).strip()


def _normalize_surface(surface: str) -> str:
    return re.sub(r"\s+", "", surface.replace("¯", "-").replace("bar", "-"))


def _claim_type(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("delta_g", "free energy", "binding energy", "adsorption")):
        return "descriptor"
    if any(term in lowered for term in ("overpotential", "current density", "tafel", "activity")):
        return "activity"
    if any(term in lowered for term in ("stable", "stability", "dissolution", "degradation")):
        return "stability"
    if any(term in lowered for term in ("selectivity", "faradaic")):
        return "selectivity"
    if any(term in lowered for term in ("synthesized", "prepared", "exposed")):
        return "synthesis_or_morphology"
    return "surface_mention"


def _confidence(text: str, block_type: str | None) -> float:
    score = 0.45
    lowered = text.lower()
    if any(term in lowered for term in ("surface", "facet", "plane", "miller")):
        score += 0.2
    if any(term in lowered for term in ("overpotential", "binding energy", "free energy", "activity")):
        score += 0.15
    if block_type in {"paragraph", "table", "figure_caption"}:
        score += 0.1
    return min(score, 0.9)


def _clean_unit(unit: str) -> str:
    return re.sub(r"\s+", " ", unit).strip()
