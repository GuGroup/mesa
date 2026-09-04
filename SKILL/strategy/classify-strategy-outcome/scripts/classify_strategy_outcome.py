#!/usr/bin/env python3
"""Classify one assembled strategy outcome with an outer LLM."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


API_URL = "https://api.openai.com/v1/responses"
FALLBACK_API_URL = os.environ.get(
    "OPENAI_FALLBACK_API_URL", "http://127.0.0.1:10531/v1/responses"
)
FALLBACK_API_KEY = os.environ.get("OPENAI_FALLBACK_API_KEY", "openai-oauth-local")
RETRYABLE_STATUS_CODES = {408, 500, 502, 503, 504}
DEFAULT_MODEL = "gpt-5.6-sol"
CLASSES = {
    "manuscript_ready",
    "extend_strategy",
    "prerequisite",
    "replace_strategy",
    "blocked",
}
OUTPUT_KEYS = {
    "schema_version",
    "strategy_id",
    "classification",
    "reason",
    "evidence_sources",
    "next_run",
    "blocker",
}


class ClassificationError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_env() -> None:
    for path in (Path(".env"), Path("DEPENDENCY/.env")):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ClassificationError(f"File does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ClassificationError(f"Invalid JSON in {path}: {exc}") from exc


def require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ClassificationError(f"{label} must be an object")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ClassificationError(f"{label} must be a list")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClassificationError(f"{label} must be a non-empty string")
    return value


def validate_input(data: Any) -> dict[str, Any]:
    root = require_dict(data, "input")
    if root.get("schema_version") != "1.0":
        raise ClassificationError("input.schema_version must be 1.0")
    current = require_string(root.get("current_strategy_id"), "current_strategy_id")
    sources = require_dict(root.get("sources"), "sources")
    strategy_source = require_string(
        sources.get("strategy_artifact"), "sources.strategy_artifact"
    )
    context = require_dict(root.get("strategy_context"), "strategy_context")
    strategies = require_list(context.get("strategies"), "strategy_context.strategies")
    strategy_ids = {
        require_string(
            require_dict(item, f"strategy_context.strategies[{index}]").get(
                "strategy_id"
            ),
            f"strategy_context.strategies[{index}].strategy_id",
        )
        for index, item in enumerate(strategies)
    }
    if current not in strategy_ids:
        raise ClassificationError("current_strategy_id is absent from strategy_context")

    diagnoses = require_list(root.get("procedure_diagnoses"), "procedure_diagnoses")
    procedure_ids: set[str] = set()
    diagnosis_sources: set[str] = set()
    for index, item in enumerate(diagnoses):
        diagnosis = require_dict(item, f"procedure_diagnoses[{index}]")
        procedure_id = require_string(
            diagnosis.get("procedure_id"),
            f"procedure_diagnoses[{index}].procedure_id",
        )
        source = require_string(
            diagnosis.get("source"), f"procedure_diagnoses[{index}].source"
        )
        if procedure_id in procedure_ids:
            raise ClassificationError(f"Duplicate procedure diagnosis: {procedure_id}")
        procedure_ids.add(procedure_id)
        diagnosis_sources.add(source)
        gaps = require_list(
            diagnosis.get("execution_gaps"),
            f"procedure_diagnoses[{index}].execution_gaps",
        )

    scientific_sources = collect_sources(
        require_list(root.get("scientific_outputs"), "scientific_outputs"),
        "scientific_outputs",
    )
    missing_sources = collect_sources(
        require_list(root.get("missing_evidence"), "missing_evidence"),
        "missing_evidence",
    )
    return {
        "current": current,
        "strategy_ids": strategy_ids,
        "strategy_source": strategy_source,
        "scientific_sources": scientific_sources,
        "result_sources": scientific_sources | missing_sources,
        "allowed_sources": {
            strategy_source,
            *diagnosis_sources,
            *scientific_sources,
            *missing_sources,
        },
    }


def collect_sources(items: list[Any], label: str) -> set[str]:
    sources = set()
    for index, item in enumerate(items):
        source = require_string(
            require_dict(item, f"{label}[{index}]").get("source"),
            f"{label}[{index}].source",
        )
        if source in sources:
            raise ClassificationError(f"Duplicate source in {label}: {source}")
        sources.add(source)
    return sources


def build_prompt(data: dict[str, Any]) -> str:
    contract = {
        "task": "Classify one completed computational strategy outcome.",
        "epistemic_gate": (
            "Choose blocked only when external conditions or insufficient records "
            "prevent a reliable judgment. A negative scientific result is not blocked."
        ),
        "ordered_rules_after_gate": [
            {
                "class": "manuscript_ready",
                "criterion": (
                    "Scientific outputs resolve the current strategy's decision_target in the "
                    "expected direction and realize a mechanisitic support to the author-reported "
                    "claim. Full support of the complete author-reported claim is not required."
                ),
            },
            {
                "class": "extend_strategy",
                "criterion": (
                    "Execution is complete and the strategy's central hypothesis and "
                    "direction remain valid, but one bounded additional computational "
                    "procedure can close a localized scientific evidence gap."
                ),
            },
            {
                "class": "prerequisite",
                "criterion": (
                    "Actual scientific outputs materially enable another generated "
                    "strategy, and prioritization.rationale supports that relationship."
                ),
            },
            {
                "class": "replace_strategy",
                "criterion": (
                    "The result is negative or unpromising, or recovery requires "
                    "changing the strategy's central hypothesis or direction. The "
                    "workflow must continue toward a positive result."
                ),
            },
        ],
        "evidence_rules": [
            "Use only the supplied input.",
            "Cite exact source strings present in the input.",
            "Do not invent facts, sources, strategy IDs, or unsupported findings.",
            "For manuscript_ready, cite the strategy artifact and scientific output.",
            "For prerequisite, cite the strategy artifact and scientific output.",
            "For replace_strategy, cite the strategy artifact and scientific output.",
            (
                "For extend_strategy, cite the strategy artifact and at least one "
                "scientific output or missing-evidence record."
            ),
            (
                "For extend_strategy, next_run.report must contain exactly three "
                "sentences beginning Evidence gap:, Additional procedure:, and "
                "Expected evidence:."
            ),
            (
                "For prerequisite, next_run.report must contain two or three sentences "
                "beginning Inherited value:, Run objective:, and optionally Constraint:."
            ),
            (
                "For replace_strategy, next_run.report must contain exactly six "
                "sentences beginning Failed expectation:, Observed evidence:, "
                "Replacement implication:, Replacement hypothesis:, Procedure:, "
                "and Expected evidence:."
            ),
        ],
        "output_schema": {
            "schema_version": "1.0",
            "strategy_id": "<current_strategy_id>",
            "classification": (
                "manuscript_ready | extend_strategy | prerequisite | "
                "replace_strategy | blocked"
            ),
            "reason": "<one concise evidence-based reason>",
            "support_strength": "strong | moderate | weak",
            "evidence_sources": ["<exact supplied source>"],
            "next_run": {
                "mode": "extend_strategy | prerequisite | replace_strategy",
                "target_strategy_id": "<current, referenced, or null>",
                "input_sources": ["<exact evidence source to carry forward>"],
                "report": ["<one complete sentence>", "<up to six total>"],
            },
            "blocker": "<external condition or insufficient record>",
        },
        "null_rules": [
            (
                "next_run is an object only for extend_strategy, prerequisite, or "
                "replace_strategy; otherwise null."
            ),
            (
                "target_strategy_id is current for extend_strategy, another existing "
                "strategy for prerequisite, and null for replace_strategy."
            ),
            "blocker is a string only for blocked; otherwise null.",
        ],
        "response_rule": "Return exactly one JSON object and no Markdown.",
    }
    return json.dumps(
        {"contract": contract, "strategy_outcome_input": data},
        indent=2,
        ensure_ascii=False,
    )


def build_payload(data: dict[str, Any], model: str) -> dict[str, Any]:
    return {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": build_prompt(data)}],
            }
        ],
    }


def call_openai(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    for api_url, endpoint_key in (
        (API_URL, api_key),
        (
            os.environ.get("OPENAI_FALLBACK_API_URL", FALLBACK_API_URL),
            os.environ.get("OPENAI_FALLBACK_API_KEY", FALLBACK_API_KEY),
        ),
    ):
        request = urllib.request.Request(
            api_url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {endpoint_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if api_url == API_URL and exc.code in RETRYABLE_STATUS_CODES:
                continue
            detail = exc.read().decode("utf-8", errors="replace")
            raise ClassificationError(f"OpenAI API HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if api_url == API_URL:
                continue
            raise ClassificationError(f"OpenAI API request failed: {exc}") from exc
    raise ClassificationError("OpenAI API request failed: all endpoints unavailable")


def output_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    chunks = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)


def parse_output(response: dict[str, Any]) -> dict[str, Any]:
    text = output_text(response).strip()
    if not text:
        raise ClassificationError("No text output found in API response")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return require_dict(json.loads(text), "LLM output")
    except json.JSONDecodeError as exc:
        raise ClassificationError(f"LLM output is not valid JSON: {exc}") from exc


def validate_classification(
    result: Any, input_data: dict[str, Any]
) -> dict[str, Any]:
    metadata = validate_input(input_data)
    output = require_dict(result, "classification")
    if set(output) != OUTPUT_KEYS:
        raise ClassificationError(
            f"Classification keys must be exactly {sorted(OUTPUT_KEYS)}"
        )
    if output.get("schema_version") != "1.0":
        raise ClassificationError("classification.schema_version must be 1.0")
    if output.get("strategy_id") != metadata["current"]:
        raise ClassificationError("classification.strategy_id does not match input")
    classification = output.get("classification")
    if classification not in CLASSES:
        raise ClassificationError(f"Unknown classification: {classification!r}")
    require_string(output.get("reason"), "classification.reason")

    evidence_sources = [
        require_string(item, f"classification.evidence_sources[{index}]")
        for index, item in enumerate(
            require_list(output.get("evidence_sources"), "classification.evidence_sources")
        )
    ]
    if not evidence_sources or len(evidence_sources) != len(set(evidence_sources)):
        raise ClassificationError(
            "classification.evidence_sources must be non-empty and unique"
        )
    invented = sorted(set(evidence_sources) - metadata["allowed_sources"])
    if invented:
        raise ClassificationError(f"Invented evidence sources: {invented}")

    validate_next_run(output, classification, metadata, evidence_sources)
    validate_blocker(output, classification)

    if classification in {
        "manuscript_ready",
        "prerequisite",
        "replace_strategy",
    }:
        if metadata["strategy_source"] not in evidence_sources:
            raise ClassificationError(
                f"{classification} must cite the strategy artifact"
            )
        if not set(evidence_sources) & metadata["scientific_sources"]:
            raise ClassificationError(
                f"{classification} must cite at least one scientific output"
            )
    if classification == "extend_strategy":
        if metadata["strategy_source"] not in evidence_sources:
            raise ClassificationError(
                "extend_strategy must cite the strategy artifact"
            )
        if not set(evidence_sources) & metadata["result_sources"]:
            raise ClassificationError(
                "extend_strategy must cite scientific output or missing evidence"
            )
    return output


def validate_next_run(
    output: dict[str, Any],
    classification: str,
    metadata: dict[str, Any],
    evidence_sources: list[str],
) -> None:
    next_run = output.get("next_run")
    active_classes = {"extend_strategy", "prerequisite", "replace_strategy"}
    if classification not in active_classes:
        if next_run is not None:
            raise ClassificationError("next_run must be null for this class")
        return
    next_run = require_dict(next_run, "classification.next_run")
    expected_keys = {"mode", "target_strategy_id", "input_sources", "report"}
    if set(next_run) != expected_keys:
        raise ClassificationError(
            f"next_run keys must be exactly {sorted(expected_keys)}"
        )
    if next_run.get("mode") != classification:
        raise ClassificationError("next_run.mode must match classification")

    target = next_run.get("target_strategy_id")
    if classification == "extend_strategy":
        if target != metadata["current"]:
            raise ClassificationError(
                "extend_strategy must target the current strategy"
            )
    elif classification == "prerequisite":
        valid_targets = metadata["strategy_ids"] - {metadata["current"]}
        if target not in valid_targets:
            raise ClassificationError(
                "prerequisite must target another generated strategy"
            )
    elif target is not None:
        raise ClassificationError(
            "replace_strategy target_strategy_id must be null"
        )

    input_sources = [
        require_string(item, f"classification.next_run.input_sources[{index}]")
        for index, item in enumerate(
            require_list(
                next_run.get("input_sources"),
                "classification.next_run.input_sources",
            )
        )
    ]
    if not input_sources or len(input_sources) != len(set(input_sources)):
        raise ClassificationError("next_run.input_sources must be non-empty and unique")
    invalid_sources = sorted(set(input_sources) - set(evidence_sources))
    if invalid_sources:
        raise ClassificationError(
            f"next_run.input_sources are not cited evidence: {invalid_sources}"
        )
    required_run_sources = (
        metadata["result_sources"]
        if classification == "extend_strategy"
        else metadata["scientific_sources"]
    )
    if not set(input_sources) & required_run_sources:
        raise ClassificationError(
            f"next_run.input_sources lack result evidence for {classification}"
        )

    report = [
        require_string(item, f"classification.next_run.report[{index}]")
        for index, item in enumerate(
            require_list(next_run.get("report"), "classification.next_run.report")
        )
    ]
    if not report or len(report) > 6:
        raise ClassificationError(
            "next_run.report must contain between one and six sentences"
        )
    if any(
        len(re.findall(r"[.!?]+(?=\s|$)", sentence.strip())) != 1
        for sentence in report
    ):
        raise ClassificationError(
            "Each next_run.report item must be one complete sentence"
        )
    expected_prefixes = {
        "extend_strategy": [
            "Evidence gap:",
            "Additional procedure:",
            "Expected evidence:",
        ],
        "prerequisite": ["Inherited value:", "Run objective:"],
        "replace_strategy": [
            "Failed expectation:",
            "Observed evidence:",
            "Replacement implication:",
            "Replacement hypothesis:",
            "Procedure:",
            "Expected evidence:",
        ],
    }
    prefixes = expected_prefixes[classification]
    if len(report) != len(prefixes) and not (
        classification == "prerequisite" and len(report) == 3
    ):
        raise ClassificationError(
            f"next_run.report has the wrong length for {classification}"
        )
    if any(
        not sentence.startswith(prefix)
        for sentence, prefix in zip(report, prefixes)
    ):
        raise ClassificationError(
            f"next_run.report has invalid ordering for {classification}"
        )
    if classification == "prerequisite" and len(report) == 3:
        if not report[2].startswith("Constraint:"):
            raise ClassificationError(
                "The optional prerequisite sentence must begin Constraint:"
            )


def validate_blocker(output: dict[str, Any], classification: str) -> None:
    blocker = output.get("blocker")
    if classification == "blocked":
        require_string(blocker, "classification.blocker")
    elif blocker is not None:
        raise ClassificationError("blocker must be null for this class")


def main() -> int:
    args = parse_args()
    try:
        input_data = require_dict(load_json(args.input), "input")
        validate_input(input_data)
        if args.dry_run:
            print(
                json.dumps(
                    {
                        "input": str(args.input),
                        "output": str(args.output),
                        "model": args.model,
                        "will_call_api": False,
                    },
                    indent=2,
                )
            )
            return 0
        load_env()
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ClassificationError(
                "OPENAI_API_KEY is not set in the environment, .env, or DEPENDENCY/.env"
            )
        response = call_openai(build_payload(input_data, args.model), api_key)
        result = validate_classification(parse_output(response), input_data)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except ClassificationError as exc:
        raise SystemExit(str(exc)) from exc
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
