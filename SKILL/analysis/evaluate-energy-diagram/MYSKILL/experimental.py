"""Deterministic experimental-context extraction utilities."""

from __future__ import annotations

from typing import Any

from .constants import FORMULA_PATTERN, KEYWORD_PATTERN, MEASUREMENT_PATTERN
from .output import standard_output
from .utils import as_list, safe_string


def deduplicate_records(records: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for record in records:
        marker = safe_string(record.get(key)).lower()
        if not marker or marker in seen:
            continue
        seen.add(marker)
        unique.append(record)
    return unique


def extract_materials(input_data: dict[str, Any], raw_text: str) -> list[dict[str, Any]]:
    materials: list[dict[str, Any]] = []
    for item in as_list(input_data.get("materials")):
        if isinstance(item, dict):
            label = safe_string(item.get("label") or item.get("name") or item.get("formula"))
            record = dict(item)
            record["label"] = label
            record.setdefault("source", "input.materials")
        else:
            record = {"label": safe_string(item), "source": "input.materials"}
        if record["label"]:
            materials.append(record)

    for match in FORMULA_PATTERN.finditer(raw_text):
        materials.append({"label": match.group(0), "source": "raw_text.pattern"})

    return deduplicate_records(materials, "label")


def extract_measurements(input_data: dict[str, Any], raw_text: str) -> list[dict[str, Any]]:
    measurements: list[dict[str, Any]] = []
    for index, item in enumerate(as_list(input_data.get("measurements")), start=1):
        if isinstance(item, dict):
            record = dict(item)
        else:
            record = {"description": safe_string(item)}
        record.setdefault("measurement_id", f"measurement_{index}")
        record.setdefault("source", "input.measurements")
        measurements.append(record)

    for index, match in enumerate(MEASUREMENT_PATTERN.finditer(raw_text), start=len(measurements) + 1):
        measurements.append(
            {
                "measurement_id": f"measurement_{index}",
                "value": float(match.group("value")),
                "unit": match.group("unit"),
                "source": "raw_text.pattern",
                "text_span": match.group(0),
            }
        )
    return measurements


def extract_hypotheses(input_data: dict[str, Any]) -> list[dict[str, Any]]:
    hypotheses: list[dict[str, Any]] = []
    for index, item in enumerate(as_list(input_data.get("hypotheses")), start=1):
        if isinstance(item, dict):
            statement = safe_string(item.get("statement") or item.get("hypothesis"))
            record = dict(item)
            record["statement"] = statement
        else:
            record = {"statement": safe_string(item)}
        if not record["statement"]:
            continue
        record.setdefault("hypothesis_id", f"hypothesis_{index}")
        record.setdefault("source", "input.hypotheses")
        record.setdefault("status", "unverified")
        hypotheses.append(record)
    return hypotheses


def extract_keywords(raw_text: str, materials: list[dict[str, Any]], targets: list[str]) -> list[str]:
    stopwords = {"and", "for", "the", "with", "from", "that", "this", "were", "was", "showed", "using"}
    keywords = {record["label"] for record in materials if record.get("label")}
    keywords.update(targets)
    for match in KEYWORD_PATTERN.finditer(raw_text):
        token = match.group(0)
        if token.lower() not in stopwords:
            keywords.add(token)
    return sorted(keywords, key=lambda item: item.lower())


def summarize_text(raw_text: str, max_length: int = 240) -> str:
    collapsed = " ".join(raw_text.split())
    if len(collapsed) <= max_length:
        return collapsed
    return collapsed[: max_length - 3].rstrip() + "..."


def extraction_quality(
    raw_text: str,
    materials: list[dict[str, Any]],
    measurements: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
) -> dict[str, Any]:
    populated = sum(bool(value) for value in [raw_text, materials, measurements, hypotheses])
    score = populated / 4
    return {
        "score": round(score, 2),
        "has_raw_text": bool(raw_text),
        "material_count": len(materials),
        "measurement_count": len(measurements),
        "hypothesis_count": len(hypotheses),
    }


def build_uncertainties(
    raw_text: str,
    materials: list[dict[str, Any]],
    measurements: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
) -> list[dict[str, str]]:
    uncertainties: list[dict[str, str]] = []
    if not raw_text:
        uncertainties.append({"field": "raw_text", "message": "No raw experimental text was provided."})
    if not materials:
        uncertainties.append({"field": "materials", "message": "No material labels were identified."})
    if not measurements:
        uncertainties.append({"field": "measurements", "message": "No measurements were provided or detected."})
    if not hypotheses:
        uncertainties.append({"field": "hypotheses", "message": "No researcher hypotheses were provided."})
    return uncertainties


def extract_experimental_context(input_data: dict[str, Any]) -> dict[str, Any]:
    raw_text = safe_string(input_data.get("raw_text") or input_data.get("text"))
    materials = extract_materials(input_data, raw_text)
    measurements = extract_measurements(input_data, raw_text)
    hypotheses = extract_hypotheses(input_data)
    conditions = input_data.get("conditions") if isinstance(input_data.get("conditions"), dict) else {}
    targets = [safe_string(item) for item in as_list(input_data.get("targets")) if safe_string(item)]
    uncertainties = build_uncertainties(raw_text, materials, measurements, hypotheses)
    return {
        "experiment_id": safe_string(input_data.get("experiment_id")) or None,
        "raw_text_summary": summarize_text(raw_text),
        "materials": materials,
        "measurements": measurements,
        "conditions": conditions,
        "hypotheses": hypotheses,
        "targets": targets,
        "keywords": extract_keywords(raw_text, materials, targets),
        "uncertainties": uncertainties,
        "extraction_quality": extraction_quality(raw_text, materials, measurements, hypotheses),
    }


def run_extraction(input_data: dict, context: dict | None = None) -> dict:
    """Standalone TASK1-compatible extraction entrypoint."""
    result = standard_output()
    result["skill"] = "experimental_information_extraction"
    try:
        if not isinstance(input_data, dict):
            result["status"] = "failure"
            result["errors"].append({"type": "ValidationError", "message": "input_data must be a dictionary."})
            result["next_action"] = {
                "recommendation": "needs_human_review",
                "reason": "Experimental extraction requires dictionary input.",
            }
            return result
        data = extract_experimental_context(input_data)
        result["data"] = data
        result["messages"].append(
            f"Extracted {len(data['materials'])} material(s), {len(data['measurements'])} measurement(s), "
            f"and {len(data['hypotheses'])} hypothesis record(s)."
        )
        result["provenance"]["inputs"].append({"type": "input_data", "keys": sorted(input_data.keys())})
        if context:
            result["provenance"]["inputs"].append({"type": "context", "keys": sorted(context.keys())})
        if data["uncertainties"]:
            result["status"] = "partial"
            result["next_action"] = {
                "recommendation": "continue",
                "reason": "Extraction completed with missing or ambiguous fields recorded as uncertainties.",
            }
        return result
    except Exception as exc:  # pragma: no cover - defensive MESA wrapper
        result["status"] = "failure"
        result["errors"].append({"type": exc.__class__.__name__, "message": str(exc)})
        result["next_action"] = {
            "recommendation": "needs_human_review",
            "reason": "Unexpected error during experimental information extraction.",
        }
        return result
