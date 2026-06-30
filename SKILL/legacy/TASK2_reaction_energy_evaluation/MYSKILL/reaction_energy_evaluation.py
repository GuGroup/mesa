#!/usr/bin/env python3
"""TASK2 reaction energy CSV evaluator."""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
from typing import Any


TASK_ID = "TASK2"
SKILL_NAME = "reaction_energy_evaluation"
NO3RR_EXCLUDED_PDS = {"*NH3 -> NH3"}


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
            "reason": "Reaction energy evaluation completed.",
        },
    }


def _safe_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _resolve_path(path_value: str, context: dict[str, Any] | None) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    if context and context.get("workdir"):
        return Path(str(context["workdir"])) / path
    return path


def _load_csv_text(input_data: dict[str, Any], context: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    if input_data.get("csv_text"):
        return str(input_data["csv_text"]), {"type": "csv_text"}
    csv_path = _safe_string(input_data.get("csv_path"))
    if not csv_path:
        raise ValueError("Provide either 'csv_path' or 'csv_text'.")
    resolved = _resolve_path(csv_path, context)
    return resolved.read_text(encoding="utf-8-sig"), {"type": "csv_path", "path": str(resolved)}


def _parse_csv(csv_text: str) -> tuple[str, list[str], list[str], dict[str, list[float]]]:
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    if not rows:
        raise ValueError("CSV input has no data rows.")

    columns = list(rows[0].keys())
    if len(columns) < 2:
        raise ValueError("CSV must contain one step column and at least one catalyst column.")

    step_column = columns[0]
    catalysts = columns[1:]
    steps = [_safe_string(row.get(step_column)) for row in rows]
    values: dict[str, list[float]] = {}

    for catalyst in catalysts:
        series: list[float] = []
        for row_index, row in enumerate(rows, start=2):
            raw = _safe_string(row.get(catalyst))
            try:
                series.append(float(raw))
            except ValueError as exc:
                raise ValueError(
                    f"Non-numeric value in column '{catalyst}', CSV row {row_index}: {raw!r}"
                ) from exc
        values[catalyst] = series
    return step_column, steps, catalysts, values


def _detect_reaction_type(requested: str, steps: list[str]) -> tuple[str, list[str]]:
    warnings: list[str] = []
    reaction_type = requested.upper() if requested else "AUTO"
    if reaction_type == "AUTO":
        if {"NO3-", "*NO3"}.issubset(set(steps)):
            reaction_type = "NO3RR"
        elif "H+" in steps and "*H" in steps:
            reaction_type = "HER"
        else:
            reaction_type = "GENERIC"
            warnings.append("Could not detect NO3RR or HER labels; using generic uphill-step ranking.")
    if reaction_type not in {"NO3RR", "HER", "GENERIC"}:
        raise ValueError(f"Unsupported reaction_type: {requested}")
    return reaction_type, warnings


def _transitions(steps: list[str], series: list[float]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index in range(1, len(steps)):
        label = f"{steps[index - 1]} -> {steps[index]}"
        output.append(
            {
                "label": label,
                "start": steps[index - 1],
                "end": steps[index],
                "delta_g": series[index] - series[index - 1],
            }
        )
    return output


def _evaluate_no3rr(catalysts: list[str], steps: list[str], values: dict[str, list[float]]) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    for required in ["NO3-", "*NO3", "*NH3", "NH3"]:
        if required not in steps:
            warnings.append(f"NO3RR expected label missing: {required}")

    results: dict[str, Any] = {}
    for catalyst in catalysts:
        transitions = _transitions(steps, values[catalyst])
        for transition in transitions:
            transition["included_for_pds"] = transition["label"] not in NO3RR_EXCLUDED_PDS
        candidates = [
            transition
            for transition in transitions
            if transition["included_for_pds"] and transition["delta_g"] > 0
        ]
        pds = max(candidates, key=lambda item: item["delta_g"], default=None)
        delta_pds = float(pds["delta_g"]) if pds else 0.0
        desorption = next((item for item in transitions if item["label"] == "*NH3 -> NH3"), None)
        results[catalyst] = {
            "mode": "NO3RR",
            "pds": pds["label"] if pds else None,
            "delta_g_pds_ev": delta_pds,
            "limiting_potential_v": -delta_pds,
            "eta_calc_v": delta_pds,
            "score": delta_pds,
            "nh3_desorption_delta_g_ev": desorption["delta_g"] if desorption else None,
            "transitions": transitions,
        }

    ranking = sorted(
        [
            {
                "catalyst": catalyst,
                "metric": "eta_calc_v",
                "score": results[catalyst]["score"],
                "pds": results[catalyst]["pds"],
                "eta_calc_v": results[catalyst]["eta_calc_v"],
                "limiting_potential_v": results[catalyst]["limiting_potential_v"],
            }
            for catalyst in catalysts
        ],
        key=lambda item: item["score"],
    )
    return results, ranking, warnings


def _evaluate_her(catalysts: list[str], steps: list[str], values: dict[str, list[float]]) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    if "H+" not in steps or "*H" not in steps:
        warnings.append("HER expected labels missing: H+ and/or *H")

    results: dict[str, Any] = {}
    for catalyst in catalysts:
        transitions = _transitions(steps, values[catalyst])
        h_transition = next((item for item in transitions if item["label"] == "H+ -> *H"), None)
        if h_transition is None and len(values[catalyst]) > 1:
            h_transition = transitions[0]
            warnings.append(f"{catalyst}: using first transition as HER descriptor fallback.")
        delta_h = float(h_transition["delta_g"]) if h_transition else 0.0
        results[catalyst] = {
            "mode": "HER",
            "descriptor": "dG_H*",
            "delta_g_h_ev": delta_h,
            "score": abs(delta_h),
            "interpretation": "closer_to_zero_is_better",
            "transitions": transitions,
        }

    ranking = sorted(
        [
            {
                "catalyst": catalyst,
                "metric": "abs_dG_H*",
                "score": results[catalyst]["score"],
                "delta_g_h_ev": results[catalyst]["delta_g_h_ev"],
            }
            for catalyst in catalysts
        ],
        key=lambda item: item["score"],
    )
    return results, ranking, warnings


def _evaluate_generic(catalysts: list[str], steps: list[str], values: dict[str, list[float]]) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    results: dict[str, Any] = {}
    for catalyst in catalysts:
        transitions = _transitions(steps, values[catalyst])
        uphill = [item for item in transitions if item["delta_g"] > 0]
        limiting = max(uphill, key=lambda item: item["delta_g"], default=None)
        score = float(limiting["delta_g"]) if limiting else 0.0
        results[catalyst] = {
            "mode": "GENERIC",
            "limiting_uphill_step": limiting["label"] if limiting else None,
            "max_uphill_delta_g_ev": score,
            "score": score,
            "transitions": transitions,
        }
    ranking = sorted(
        [
            {
                "catalyst": catalyst,
                "metric": "max_uphill_delta_g_ev",
                "score": results[catalyst]["score"],
                "limiting_step": results[catalyst]["limiting_uphill_step"],
            }
            for catalyst in catalysts
        ],
        key=lambda item: item["score"],
    )
    return results, ranking, []


def _compare_experiment(results: dict[str, Any], experiment: Any, reaction_type: str) -> dict[str, Any]:
    if not isinstance(experiment, dict):
        return {}
    comparison: dict[str, Any] = {}
    for catalyst, raw_value in experiment.items():
        if catalyst not in results:
            comparison[catalyst] = {"error": "catalyst not found"}
            continue
        experimental = float(raw_value)
        if reaction_type == "HER":
            calculated = results[catalyst]["delta_g_h_ev"]
        else:
            calculated = results[catalyst].get("eta_calc_v", results[catalyst].get("score", 0.0))
        comparison[catalyst] = {
            "calculated": calculated,
            "experimental": experimental,
            "difference": calculated - experimental,
            "absolute_difference_mv": abs(calculated - experimental) * 1000,
        }
    return comparison


def _markdown_report(data: dict[str, Any]) -> str:
    lines = [
        f"# {data['reaction_type']} Reaction Energy Evaluation",
        "",
        f"Step column: `{data['step_column']}`",
        "",
        "## Catalyst Ranking",
        "",
    ]
    if data["reaction_type"] == "HER":
        lines.extend(["| Rank | Catalyst | dG_H* (eV) | abs(dG_H*) |", "|---:|---|---:|---:|"])
        for index, row in enumerate(data["ranking"], start=1):
            lines.append(
                f"| {index} | {row['catalyst']} | {row['delta_g_h_ev']:.3f} | {row['score']:.3f} |"
            )
    else:
        lines.extend(["| Rank | Catalyst | PDS | eta_calc (V) | U_lim (V) |", "|---:|---|---|---:|---:|"])
        for index, row in enumerate(data["ranking"], start=1):
            lines.append(
                f"| {index} | {row['catalyst']} | {row.get('pds') or row.get('limiting_step') or 'none'} | {row['score']:.3f} | {row.get('limiting_potential_v', -row['score']):.3f} |"
            )

    if data["ranking"]:
        best = data["ranking"][0]
        lines.extend(["", "## Best Catalyst", ""])
        if data["reaction_type"] == "HER":
            lines.append(
                f"`{best['catalyst']}` is best by HER descriptor because `dG_H*` is closest to 0 eV."
            )
        else:
            lines.append(
                f"`{best['catalyst']}` is best by the lowest calculated limiting barrier/overpotential score."
            )
    if data.get("experiment_comparison"):
        lines.extend(["", "## Experiment Comparison", ""])
        lines.extend(["| Catalyst | Calculated | Experiment | Abs. difference (mV) |", "|---|---:|---:|---:|"])
        for catalyst, row in data["experiment_comparison"].items():
            if "error" in row:
                lines.append(f"| {catalyst} | n/a | n/a | n/a |")
            else:
                lines.append(
                    f"| {catalyst} | {row['calculated']:.3f} | {row['experimental']:.3f} | {row['absolute_difference_mv']:.1f} |"
                )
    if data.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend([f"- {warning}" for warning in data["warnings"]])
    return "\n".join(lines) + "\n"


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
            raise TypeError("input_data must be a dictionary.")

        csv_text, input_record = _load_csv_text(input_data, context)
        step_column, steps, catalysts, values = _parse_csv(csv_text)
        requested_type = _safe_string(input_data.get("reaction_type") or "auto")
        reaction_type, warnings = _detect_reaction_type(requested_type, steps)

        if reaction_type == "NO3RR":
            evaluated, ranking, eval_warnings = _evaluate_no3rr(catalysts, steps, values)
        elif reaction_type == "HER":
            evaluated, ranking, eval_warnings = _evaluate_her(catalysts, steps, values)
        else:
            evaluated, ranking, eval_warnings = _evaluate_generic(catalysts, steps, values)
        warnings.extend(eval_warnings)

        data = {
            "reaction_type": reaction_type,
            "step_column": step_column,
            "steps": steps,
            "catalysts": catalysts,
            "ranking": ranking,
            "results": evaluated,
            "experiment_comparison": _compare_experiment(evaluated, input_data.get("experiment"), reaction_type),
            "warnings": warnings,
        }
        data["markdown_report"] = _markdown_report(data)
        result["data"] = data
        result["messages"].append(
            f"Evaluated {len(catalysts)} catalyst(s) for {reaction_type}; best catalyst: {ranking[0]['catalyst'] if ranking else 'none'}."
        )
        result["provenance"]["inputs"].append(input_record)
        result["provenance"]["inputs"].append({"type": "input_data", "keys": sorted(input_data.keys())})

        report_path = _safe_string(input_data.get("report_path"))
        if report_path:
            output_path = _resolve_path(report_path, context)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(data["markdown_report"], encoding="utf-8")
            artifact = {"type": "markdown_report", "path": str(output_path)}
            result["artifacts"].append(artifact)
            result["provenance"]["generated_files"].append(artifact)

        if warnings:
            result["status"] = "partial"
            result["next_action"] = {
                "recommendation": "continue",
                "reason": "Reaction evaluation completed with warnings.",
            }
        return result
    except Exception as exc:
        result["status"] = "failure"
        result["errors"].append({"type": exc.__class__.__name__, "message": str(exc)})
        result["next_action"] = {
            "recommendation": "needs_human_review",
            "reason": "Reaction energy evaluation failed.",
        }
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TASK2 reaction energy evaluation.")
    parser.add_argument("--input", required=True, type=Path, help="Path to input JSON file.")
    parser.add_argument("--output", required=True, type=Path, help="Path to output JSON file.")
    parser.add_argument("--workdir", type=Path, default=None, help="Optional working directory.")
    parser.add_argument("--dry-run", action="store_true", help="Do not perform real external execution.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed logs.")
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8-sig") as handle:
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
