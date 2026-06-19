#!/usr/bin/env python3
"""TASK1 deterministic experimental information extractor."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


TASK_ID = "TASK1"
SKILL_NAME = "experimental_information_extraction"

FORMULA_PATTERN = re.compile(r"\b(?:[A-Z][a-z]?\d*){2,}\b")
MEASUREMENT_PATTERN = re.compile(
    r"(?P<value>[+-]?\d+(?:\.\d+)?)\s*(?P<unit>mV|V|eV|K|C|M|mol/L|mA/cm2|mA cm-2|%)\b",
    re.IGNORECASE,
)
KEYWORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9+\-*/]{2,}")


def _standard_output(status: str = "success") -> dict[str, Any]:
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
            "reason": "Experimental context extracted for downstream MESA tasks.",
        },
    }


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _safe_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _deduplicate_records(records: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for record in records:
        marker = _safe_string(record.get(key)).lower()
        if not marker or marker in seen:
            continue
        seen.add(marker)
        unique.append(record)
    return unique


def _extract_materials(input_data: dict[str, Any], raw_text: str) -> list[dict[str, Any]]:
    materials: list[dict[str, Any]] = []
    for item in _as_list(input_data.get("materials")):
        if isinstance(item, dict):
            label = _safe_string(item.get("label") or item.get("name") or item.get("formula"))
            record = dict(item)
            record["label"] = label
            record.setdefault("source", "input.materials")
        else:
            record = {"label": _safe_string(item), "source": "input.materials"}
        if record["label"]:
            materials.append(record)

    for match in FORMULA_PATTERN.finditer(raw_text):
        materials.append({"label": match.group(0), "source": "raw_text.pattern"})

    return _deduplicate_records(materials, "label")


def _extract_measurements(input_data: dict[str, Any], raw_text: str) -> list[dict[str, Any]]:
    measurements: list[dict[str, Any]] = []
    for index, item in enumerate(_as_list(input_data.get("measurements")), start=1):
        if isinstance(item, dict):
            record = dict(item)
        else:
            record = {"description": _safe_string(item)}
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


def _extract_hypotheses(input_data: dict[str, Any]) -> list[dict[str, Any]]:
    hypotheses: list[dict[str, Any]] = []
    for index, item in enumerate(_as_list(input_data.get("hypotheses")), start=1):
        if isinstance(item, dict):
            statement = _safe_string(item.get("statement") or item.get("hypothesis"))
            record = dict(item)
            record["statement"] = statement
        else:
            record = {"statement": _safe_string(item)}
        if not record["statement"]:
            continue
        record.setdefault("hypothesis_id", f"hypothesis_{index}")
        record.setdefault("source", "input.hypotheses")
        record.setdefault("status", "unverified")
        hypotheses.append(record)
    return hypotheses


def _extract_keywords(raw_text: str, materials: list[dict[str, Any]], targets: list[str]) -> list[str]:
    stopwords = {
        "and",
        "for",
        "the",
        "with",
        "from",
        "that",
        "this",
        "were",
        "was",
        "showed",
        "using",
    }
    keywords = {record["label"] for record in materials if record.get("label")}
    keywords.update(targets)
    for match in KEYWORD_PATTERN.finditer(raw_text):
        token = match.group(0)
        if token.lower() not in stopwords:
            keywords.add(token)
    return sorted(keywords, key=lambda item: item.lower())


def _summarize_text(raw_text: str, max_length: int = 240) -> str:
    collapsed = " ".join(raw_text.split())
    if len(collapsed) <= max_length:
        return collapsed
    return collapsed[: max_length - 3].rstrip() + "..."


def _extraction_quality(raw_text: str, materials: list[dict[str, Any]], measurements: list[dict[str, Any]], hypotheses: list[dict[str, Any]]) -> dict[str, Any]:
    populated = sum(bool(value) for value in [raw_text, materials, measurements, hypotheses])
    score = populated / 4
    return {
        "score": round(score, 2),
        "has_raw_text": bool(raw_text),
        "material_count": len(materials),
        "measurement_count": len(measurements),
        "hypothesis_count": len(hypotheses),
    }


def _build_uncertainties(raw_text: str, materials: list[dict[str, Any]], measurements: list[dict[str, Any]], hypotheses: list[dict[str, Any]]) -> list[dict[str, str]]:
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


def run(input_data: dict, context: dict | None = None) -> dict:
    """
    Execute this skill.

    Parameters
    ----------
    input_data:
        JSON-serializable input dictionary.
    context:
        Optional runtime context such as project root, working directory,
        dry-run flag, external service configuration, runtime metadata,
        or previous task information.

    Returns
    -------
    dict
        JSON-serializable output dictionary following the standard MESA
        skill output format.
    """
    result = _standard_output()
    try:
        if not isinstance(input_data, dict):
            result["status"] = "failure"
            result["errors"].append(
                {"type": "ValidationError", "message": "input_data must be a dictionary."}
            )
            result["next_action"] = {
                "recommendation": "needs_human_review",
                "reason": "TASK1 requires dictionary input.",
            }
            return result

        raw_text = _safe_string(input_data.get("raw_text") or input_data.get("text"))
        materials = _extract_materials(input_data, raw_text)
        measurements = _extract_measurements(input_data, raw_text)
        hypotheses = _extract_hypotheses(input_data)
        conditions = input_data.get("conditions") if isinstance(input_data.get("conditions"), dict) else {}
        targets = [_safe_string(item) for item in _as_list(input_data.get("targets")) if _safe_string(item)]
        uncertainties = _build_uncertainties(raw_text, materials, measurements, hypotheses)

        result["data"] = {
            "experiment_id": _safe_string(input_data.get("experiment_id")) or None,
            "raw_text_summary": _summarize_text(raw_text),
            "materials": materials,
            "measurements": measurements,
            "conditions": conditions,
            "hypotheses": hypotheses,
            "targets": targets,
            "keywords": _extract_keywords(raw_text, materials, targets),
            "uncertainties": uncertainties,
            "extraction_quality": _extraction_quality(raw_text, materials, measurements, hypotheses),
        }
        result["messages"].append(
            f"Extracted {len(materials)} material(s), {len(measurements)} measurement(s), and {len(hypotheses)} hypothesis record(s)."
        )
        if uncertainties:
            result["status"] = "partial"
            result["next_action"] = {
                "recommendation": "continue",
                "reason": "Extraction completed with missing or ambiguous fields recorded as uncertainties.",
            }
        result["provenance"]["inputs"].append({"type": "input_data", "keys": sorted(input_data.keys())})
        if context:
            result["provenance"]["inputs"].append({"type": "context", "keys": sorted(context.keys())})
        return result
    except Exception as exc:
        result["status"] = "failure"
        result["errors"].append({"type": exc.__class__.__name__, "message": str(exc)})
        result["next_action"] = {
            "recommendation": "needs_human_review",
            "reason": "Unexpected error during experimental information extraction.",
        }
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TASK1 experimental information extraction.")
    parser.add_argument("--input", required=True, type=Path, help="Path to input JSON file.")
    parser.add_argument("--output", required=True, type=Path, help="Path to output JSON file.")
    parser.add_argument("--workdir", type=Path, default=None, help="Optional working directory.")
    parser.add_argument("--dry-run", action="store_true", help="Do not perform external execution.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed logs.")
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8") as handle:
        input_data = json.load(handle)

    context = {
        "workdir": str(args.workdir) if args.workdir else None,
        "dry_run": args.dry_run,
    }
    result = run(input_data, context)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
    if args.verbose:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

