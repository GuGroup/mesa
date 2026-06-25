from __future__ import annotations

import argparse
from pathlib import Path
from xml.sax.saxutils import escape

from ingest_io import safe_write
from ingest_records import CANONICAL_STRUCTURE, GENERATED_MARKER, SVG_GENERATED_MARKER, ResultRecord, WriteContext


def generated(content: str) -> str:
    return GENERATED_MARKER + content


def claim_matrix_yaml(record: ResultRecord, has_structure: bool) -> str:
    method_claim = ""
    if has_structure:
        method_claim = """  - id: M1
    level: method
    statement: The endpoint structure passed the placeholder analyzer summary.
    status: qualified
    evidence:
      - id: E2
        source_id: structure-co-pt111-final
        path: paper/inputs/structures/CO_on_Pt111_POSCAR
        relation: context
        summary: Fixture POSCAR records the final endpoint structure.
    figures: []
    assumptions: []
    caveats:
      - Visual review image is represented by a placeholder text file.
    risks: []
    allowed_sections: [methods, results]
"""
    return generated(f"""version: 1
target: nature-family
claims:
  - id: C1
    level: main
    statement: {record.system_label} has a recorded {record.quantity_label} of {record.value} {record.units} under {record.method_label}.
    status: qualified
    evidence:
      - id: E1
        source_id: {record.source_id}
        path: {record.result_path}
        relation: direct
        summary: Fixture result is marked {record.status} and is used only as contract evidence.
    figures: [F1]
    assumptions:
      - Fixture method metadata are treated as already completed upstream.
    caveats:
      - Fixture values are not physical publication claims.
    risks: []
    allowed_sections: [results, discussion, abstract]
{method_claim}""")


def figure_map_yaml() -> str:
    return generated("""version: 1
figures:
  - id: F1
    label: Figure 1
    role: main
    title: Fixture adsorption-energy evidence map
    claim_ids: [C1]
    source_files:
      - paper/figures/source/fig1_energy_diagram.spec.yaml
    exported_files:
      - paper/figures/exported/fig1_energy_diagram.placeholder.svg
    qa_files:
      - paper/figures/qa/fig1_energy_diagram.md
    status: qa-passed
    blockers: []
""")


def reviewer_issues_yaml() -> str:
    return generated("version: 1\nissues: []\n")


def notation_yaml(record: ResultRecord) -> str:
    return generated(f"""version: 1
systems:
  - id: S1
    canonical: CO/Pt(111)
    aliases: [{record.system_id}]
methods:
  - id: {record.method_id}
    canonical: {record.method_label}
energies:
  - symbol: E_ads
    meaning: {record.quantity_label}
    units: {record.units}
figures:
  - id: F1
    label: Figure 1
abbreviations:
  - short: QA
    long: quality assurance
""")


def section_contracts_yaml(record: ResultRecord, has_structure: bool) -> str:
    method_claims = "[M1]" if has_structure else "[]"
    results_claims = "[C1, M1]" if has_structure else "[C1]"
    results_sources = f"      - {record.result_path}\n"
    if has_structure:
        results_sources += "      - paper/inputs/structures/CO_on_Pt111_POSCAR\n"
    return generated(f"""version: 1
sections:
  - id: results
    path: paper/manuscript/sections/results.md
    status: ready-to-draft
    allowed_claims: {results_claims}
    required_figures: [F1]
    required_sources:
{results_sources}    required_caveats:
      - Fixture values are not physical publication claims.
    blocked_by: []
    chunk_policy:
      unit: flow-sized-result-block
      locked_chunks: []
  - id: methods
    path: paper/manuscript/sections/methods.md
    status: ready-to-draft
    allowed_claims: {method_claims}
    required_figures: []
    required_sources:
      - paper/inputs/manifest.yaml
    required_caveats: []
    blocked_by: []
    chunk_policy:
      unit: method-block
      locked_chunks: []
  - id: abstract
    path: paper/manuscript/sections/abstract.md
    status: not-ready
    allowed_claims: [C1]
    required_figures: []
    required_sources:
      - paper/logic/claim-matrix.yaml
    required_caveats:
      - Draft last after Results and Discussion are locked.
    blocked_by: [results, discussion]
    chunk_policy:
      unit: abstract
      locked_chunks: []
""")


def figure_source_yaml(record: ResultRecord) -> str:
    return generated(f"""version: 1
figure_id: F1
kind: fixture-energy-diagram
data_sources:
  - {record.result_path}
notes: Deterministic placeholder spec generated from ingested MESA outputs.
""")


def exported_figure_svg(record: ResultRecord) -> str:
    system_label = escape(record.system_label)
    value = escape(record.value)
    units = escape(record.units)
    return SVG_GENERATED_MARKER + f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360" role="img" aria-label="Fixture adsorption energy diagram">
  <rect width="640" height="360" fill="#ffffff"/>
  <line x1="80" y1="250" x2="560" y2="250" stroke="#333333" stroke-width="2"/>
  <rect x="150" y="170" width="110" height="80" fill="#d6e8ff" stroke="#1f4e79"/>
  <rect x="380" y="90" width="110" height="160" fill="#f8d7da" stroke="#8a1f2d"/>
  <text x="205" y="285" text-anchor="middle" font-family="Arial" font-size="20">reference</text>
  <text x="435" y="285" text-anchor="middle" font-family="Arial" font-size="20">{system_label}</text>
  <text x="435" y="70" text-anchor="middle" font-family="Arial" font-size="22">{value} {units}</text>
</svg>
"""


def figure_qa_markdown(record: ResultRecord) -> str:
    return generated(f"""# Figure 1 QA

- Source result: {record.source_id}
- Status: qa-passed
- Scope: fixture placeholder for validation and build contracts only.
""")


def section_markdown(claims: str, figures: str) -> str:
    return generated(f"""---
status: ready-to-draft
allowed_claims: {claims}
required_figures: {figures}
---

Prose intentionally not drafted in the fixture. Later section-writing work may
expand this contract after heavy gates pass.
""")


def write_minimum_gate_files(paper: Path, records: list[ResultRecord], context: WriteContext) -> None:
    record = records[0]
    has_structure = (paper / CANONICAL_STRUCTURE.removeprefix("paper/")).is_file()
    safe_write(paper / "logic/claim-matrix.yaml", claim_matrix_yaml(record, has_structure), context)
    safe_write(paper / "logic/figure-map.yaml", figure_map_yaml(), context)
    safe_write(paper / "state/reviewer-issues.yaml", reviewer_issues_yaml(), context)
    safe_write(paper / "manuscript/section-contracts.yaml", section_contracts_yaml(record, has_structure), context)
    safe_write(paper / "logic/notation.yaml", notation_yaml(record), context)
    safe_write(paper / "figures/source/fig1_energy_diagram.spec.yaml", figure_source_yaml(record), context)
    safe_write(paper / "figures/exported/fig1_energy_diagram.placeholder.svg", exported_figure_svg(record), context)
    safe_write(paper / "figures/qa/fig1_energy_diagram.md", figure_qa_markdown(record), context)
    safe_write(paper / "manuscript/sections/results.md", section_markdown("[C1, M1]" if has_structure else "[C1]", "[F1]"), context)
    safe_write(paper / "manuscript/sections/methods.md", section_markdown("[M1]" if has_structure else "[]", "[]"), context)
    safe_write(paper / "manuscript/sections/abstract.md", section_markdown("[C1]", "[]"), context)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate minimum manuscript gate files during ingest. This helper is "
            "imported by ingest_mesa_outputs.py; run that CLI for normal use."
        )
    )
    parser.parse_args()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
