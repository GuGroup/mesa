"""Markdown report generation."""

from __future__ import annotations

from typing import Any


def markdown_report(data: dict[str, Any]) -> str:
    reaction_metadata = data["reaction_metadata"]
    lines = [
        f"# {reaction_metadata['abbreviation']} Reaction Energy Evaluation",
        "",
        f"Reaction name: **{reaction_metadata['canonical_name']}**",
        f"Step column: `{data['step_column']}`",
        f"Input mode: `{data['input_mode']}`",
        "",
        "## Catalyst Ranking",
        "",
    ]
    reaction_type = data["reaction_type"]
    if reaction_type == "HER":
        lines.extend(["| Rank | Catalyst | dG_H* (eV) | abs(dG_H*) |", "|---:|---|---:|---:|"])
        for index, row in enumerate(data["ranking"], start=1):
            lines.append(f"| {index} | {row['catalyst']} | {row['delta_g_h_ev']:.3f} | {row['score']:.3f} |")
    elif reaction_type == "OER":
        lines.extend(["| Rank | Catalyst | PDS | η_calc (V) | U_L (V) |", "|---:|---|---|---:|---:|"])
        for index, row in enumerate(data["ranking"], start=1):
            ul = row.get("limiting_potential_v")
            ul_text = f"{ul:.3f}" if isinstance(ul, (int, float)) else "n/a"
            lines.append(f"| {index} | {row['catalyst']} | {row.get('pds') or 'none'} | {row['score']:.3f} | {ul_text} |")
    else:
        lines.extend(["| Rank | Catalyst | Limiting step/PDS | Score | U_lim (V) |", "|---:|---|---|---:|---:|"])
        for index, row in enumerate(data["ranking"], start=1):
            ul = row.get("limiting_potential_v", -row["score"])
            ul_text = f"{ul:.3f}" if isinstance(ul, (int, float)) else "n/a"
            lines.append(
                f"| {index} | {row['catalyst']} | {row.get('pds') or row.get('limiting_step') or 'none'} | {row['score']:.3f} | {ul_text} |"
            )

    if data["ranking"]:
        best = data["ranking"][0]
        lines.extend(["", "## Best Catalyst", ""])
        if reaction_type == "HER":
            lines.append(f"`{best['catalyst']}` is best by the HER descriptor because `dG_H*` is closest to 0 eV.")
        elif reaction_type == "OER":
            lines.append(f"`{best['catalyst']}` has the lowest calculated OER overpotential descriptor in this input table.")
        else:
            lines.append(f"`{best['catalyst']}` has the lowest thermodynamic limiting-step score in this input table.")

    if data.get("experiment_context", {}).get("raw_text_summary"):
        lines.extend(["", "## Experimental Context Summary", "", data["experiment_context"]["raw_text_summary"]])

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

    if data.get("competing_reaction_summary"):
        lines.extend(["", "## Competing Reaction Notes", ""])
        lines.append("Competing reaction descriptors are selectivity warnings, not final selectivity predictions.")
        for reaction, mapping in data["competing_reaction_summary"].items():
            lines.append(f"- {reaction}: {len(mapping)} catalyst descriptor record(s).")

    if data.get("llm_guidance"):
        lines.extend(["", "## LLM Interpretation Rule", ""])
        lines.append(
            f"Any LLM-assisted interpretation must read `{data['llm_guidance']['must_read_reference_before_interpretation']}` before making electrochemical claims."
        )

    if data.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend([f"- {warning}" for warning in data["warnings"]])
    return "\n".join(lines) + "\n"
