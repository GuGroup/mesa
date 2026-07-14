"""Orchestration layer for the modular reaction-energy evaluator."""

from __future__ import annotations

from typing import Any

from .comparison import compare_experiment, evaluate_competing_reactions
from .errors import MesaValidationError
from .evaluators import evaluate_generic, evaluate_her, evaluate_oer, evaluate_schema_reduction
from .experimental import extract_experimental_context
from .input_parsers import normalise_energy_input
from .llm_guidance import llm_guidance_payload
from .nomenclature import detect_reaction_type
from .output import standard_output
from .reporting import markdown_report
from .utils import resolve_path, safe_string


def evaluate_energy_table(input_data: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    step_column, steps, catalysts, values, input_record, warnings = normalise_energy_input(input_data, context)
    requested_type = safe_string(input_data.get("reaction_type") or input_data.get("reaction") or "auto")
    reaction_type, detect_warnings, reaction_metadata = detect_reaction_type(requested_type, steps)
    warnings.extend(detect_warnings)

    if reaction_type == "HER":
        evaluated, ranking, eval_warnings = evaluate_her(catalysts, steps, values, reaction_metadata)
    elif reaction_type == "OER":
        evaluated, ranking, eval_warnings = evaluate_oer(catalysts, steps, values, reaction_metadata, input_data)
    elif reaction_type in {"NO3RR", "NO2RR", "NRR", "CO2RR", "ORR"} or reaction_metadata.get("reaction_class") == "reduction":
        evaluated, ranking, eval_warnings = evaluate_schema_reduction(catalysts, steps, values, reaction_metadata)
    else:
        evaluated, ranking, eval_warnings = evaluate_generic(catalysts, steps, values, reaction_metadata)
    warnings.extend(eval_warnings)

    data = {
        "reaction_type": reaction_type,
        "reaction_metadata": reaction_metadata,
        "step_column": step_column,
        "steps": steps,
        "catalysts": catalysts,
        "values": values if input_data.get("include_values_in_output", False) else None,
        "ranking": ranking,
        "results": evaluated,
        "experiment_comparison": compare_experiment(evaluated, input_data.get("experiment"), reaction_type),
        "competing_reaction_summary": evaluate_competing_reactions(input_data, evaluated),
        "llm_guidance": llm_guidance_payload(),
        "warnings": warnings,
        "input_mode": input_record.get("type", "unknown"),
        "input_record": input_record,
    }
    if data["values"] is None:
        data.pop("values")
    data["markdown_report"] = markdown_report(data)
    return data


def run(input_data: dict, context: dict | None = None) -> dict:
    """Execute the integrated evaluate-energy-diagram skill.

    Energy input can be CSV-based (`csv_path` or `csv_text`) or dictionary-based
    (`energy_data`, `reaction_energies`, `steps` + `energies`, or catalyst->step
    mapping). The public `run()` entrypoint is intentionally stable even though
    the internal evaluator is modular.
    """
    result = standard_output()
    try:
        if not isinstance(input_data, dict):
            raise TypeError("input_data must be a dictionary.")

        experiment_context = extract_experimental_context(input_data)
        evaluation_data = evaluate_energy_table(input_data, context)
        evaluation_data["experiment_context"] = experiment_context
        # Rebuild report after attaching experiment context.
        evaluation_data["markdown_report"] = markdown_report(evaluation_data)

        result["data"] = evaluation_data
        result["messages"].append(
            f"Evaluated {len(evaluation_data['catalysts'])} catalyst(s) for {evaluation_data['reaction_type']}; "
            f"best catalyst: {evaluation_data['ranking'][0]['catalyst'] if evaluation_data['ranking'] else 'none'}."
        )
        result["messages"].append(
            f"Integrated experimental context extraction found {len(experiment_context['materials'])} material(s), "
            f"{len(experiment_context['measurements'])} measurement(s), and {len(experiment_context['hypotheses'])} hypothesis record(s)."
        )
        result["provenance"]["inputs"].append(evaluation_data["input_record"])
        result["provenance"]["inputs"].append({"type": "input_data", "keys": sorted(input_data.keys())})
        if context:
            result["provenance"]["inputs"].append({"type": "context", "keys": sorted(context.keys())})

        report_path = safe_string(input_data.get("report_path"))
        if report_path:
            output_path = resolve_path(report_path, context)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(evaluation_data["markdown_report"], encoding="utf-8")
            artifact = {"type": "markdown_report", "path": str(output_path)}
            result["artifacts"].append(artifact)
            result["provenance"]["generated_files"].append(artifact)

        if evaluation_data.get("warnings") or experiment_context.get("uncertainties"):
            result["status"] = "partial"
            result["next_action"] = {
                "recommendation": "continue",
                "reason": "Evaluation completed with warnings or incomplete experimental context.",
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
