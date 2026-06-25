from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TASK_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = TASK_ROOT / "scripts"
FIXTURE = TASK_ROOT / "examples" / "fixture_project"
PAPER = FIXTURE / "paper"
BAD = FIXTURE / "bad"


def run_validator(name: str, *args: str | Path) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPTS / name), *(str(arg) for arg in args)]
    return subprocess.run(command, text=True, capture_output=True, check=False)


class ValidatorCliTests(unittest.TestCase):
    def test_claim_matrix_passes_when_fixture_is_supported(self) -> None:
        # Given: the coherent fixture claim matrix.
        claim_matrix = PAPER / "logic" / "claim-matrix.yaml"

        # When: the validator runs through its CLI.
        result = run_validator("validate_claim_matrix.py", claim_matrix)

        # Then: the gate accepts the matrix.
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_claim_matrix_rejects_unsupported_claim_when_status_is_invalid(self) -> None:
        # Given: a claim matrix with an unsupported claim status.
        claim_matrix = BAD / "claim-matrix-unsupported.yaml"

        # When: the validator runs through its CLI.
        result = run_validator("validate_claim_matrix.py", claim_matrix)

        # Then: the gate rejects the unsupported claim.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported", result.stderr)

    def test_claim_matrix_rejects_empty_yaml(self) -> None:
        # Given: an empty claim matrix file.
        claim_matrix = BAD / "claim-matrix-empty.yaml"

        # When: the validator runs through its CLI.
        result = run_validator("validate_claim_matrix.py", claim_matrix)

        # Then: empty input is not treated as a valid matrix.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("empty", result.stderr.lower())

    def test_claim_matrix_rejects_traversal_evidence_path(self) -> None:
        # Given: a claim matrix with a prefix-matching evidence path that escapes paper/.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paper = root / "paper"
            (paper / "inputs").mkdir(parents=True)
            (paper / "logic").mkdir(parents=True)
            (root / "outside_claim.txt").write_text("outside", encoding="utf-8")
            claim_matrix = paper / "logic" / "claim-matrix.yaml"
            claim_matrix.write_text(
                """
{
  "claims": [
    {
      "id": "C1",
      "level": "main",
      "statement": "Claim one.",
      "status": "supported",
      "evidence": [
        {
          "id": "E1",
          "source_id": "S1",
          "path": "paper/inputs/../../outside_claim.txt",
          "relation": "direct",
          "summary": "Escaped source."
        }
      ],
      "figures": [],
      "assumptions": [],
      "caveats": [],
      "risks": [],
      "allowed_sections": []
    }
  ]
}
""",
                encoding="utf-8",
            )

            # When: the claim validator runs through its CLI.
            result = run_validator("validate_claim_matrix.py", claim_matrix)

        # Then: the traversal-shaped path is rejected.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("escapes paper root", result.stderr)

    def test_figure_map_passes_when_fixture_references_known_claims(self) -> None:
        # Given: the coherent fixture figure map and claim matrix.
        figure_map = PAPER / "logic" / "figure-map.yaml"
        claim_matrix = PAPER / "logic" / "claim-matrix.yaml"

        # When: the validator runs through its CLI.
        result = run_validator("validate_figure_map.py", figure_map, "--claims", claim_matrix)

        # Then: all figure references are accepted.
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_figure_map_rejects_stale_claim_and_panel_reference(self) -> None:
        # Given: a figure map that points at a missing claim and an invalid panel.
        figure_map = BAD / "figure-map-stale-panel.yaml"
        claim_matrix = PAPER / "logic" / "claim-matrix.yaml"

        # When: the validator runs through its CLI.
        result = run_validator("validate_figure_map.py", figure_map, "--claims", claim_matrix)

        # Then: stale claim and panel mapping errors fail the gate.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("C404", result.stderr)
        self.assertIn("panel", result.stderr)

    def test_figure_map_rejects_traversal_source_path(self) -> None:
        # Given: a figure map with a prefix-matching source path that escapes paper/.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paper = root / "paper"
            (paper / "figures" / "source").mkdir(parents=True)
            (paper / "logic").mkdir(parents=True)
            (root / "outside_figure.spec.yaml").write_text("outside", encoding="utf-8")
            claim_matrix = paper / "logic" / "claim-matrix.yaml"
            claim_matrix.write_text(
                '{"claims": [{"id": "C1", "level": "main", "statement": "Claim one.", '
                '"status": "supported", "evidence": [{"id": "E1", "source_id": "S1", '
                '"path": "paper/logic/claim-matrix.yaml", "relation": "direct", '
                '"summary": "Source."}], "figures": [], "assumptions": [], "caveats": [], '
                '"risks": [], "allowed_sections": []}]}',
                encoding="utf-8",
            )
            figure_map = paper / "logic" / "figure-map.yaml"
            figure_map.write_text(
                """
{
  "figures": [
    {
      "id": "F1",
      "label": "Figure 1",
      "role": "main",
      "title": "Figure one",
      "claim_ids": ["C1"],
      "source_files": ["paper/figures/source/../../../outside_figure.spec.yaml"],
      "exported_files": [],
      "qa_files": [],
      "status": "generated",
      "blockers": []
    }
  ]
}
""",
                encoding="utf-8",
            )

            # When: the figure validator runs through its CLI.
            result = run_validator("validate_figure_map.py", figure_map, "--claims", claim_matrix)

        # Then: the traversal-shaped path is rejected.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("escapes paper root", result.stderr)

    def test_reviewer_issues_pass_when_no_blockers_are_open(self) -> None:
        # Given: the coherent fixture reviewer issue state.
        issues = PAPER / "state" / "reviewer-issues.yaml"

        # When: the validator runs through its CLI.
        result = run_validator("validate_reviewer_issues.py", issues)

        # Then: the reviewer gate accepts it.
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reviewer_issues_reject_open_blockers(self) -> None:
        # Given: reviewer issues with an unresolved blocker.
        issues = BAD / "reviewer-issues-blocker.yaml"

        # When: the validator runs through its CLI.
        result = run_validator("validate_reviewer_issues.py", issues)

        # Then: the reviewer gate blocks prose.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BLOCKER", result.stderr)

    def test_section_contracts_pass_when_claims_are_allowed(self) -> None:
        # Given: section contracts whose claim IDs exist in the claim matrix.
        contracts = PAPER / "manuscript" / "section-contracts.yaml"
        claim_matrix = PAPER / "logic" / "claim-matrix.yaml"

        # When: the validator runs through its CLI.
        result = run_validator("validate_section_contracts.py", contracts, "--claims", claim_matrix)

        # Then: the section contract gate accepts it.
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_section_contracts_reject_disallowed_claim_ids(self) -> None:
        # Given: a section contract that allows a claim absent from the matrix.
        contracts = BAD / "section-contracts-disallowed.yaml"
        claim_matrix = PAPER / "logic" / "claim-matrix.yaml"

        # When: the validator runs through its CLI.
        result = run_validator("validate_section_contracts.py", contracts, "--claims", claim_matrix)

        # Then: the section contract gate rejects the stale claim.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("C404", result.stderr)

    def test_section_contracts_reject_traversal_required_source_path(self) -> None:
        # Given: a section contract with a prefix-matching required source that escapes paper/.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paper = root / "paper"
            (paper / "inputs").mkdir(parents=True)
            (paper / "logic").mkdir(parents=True)
            (paper / "manuscript").mkdir(parents=True)
            (root / "outside_claim.txt").write_text("outside", encoding="utf-8")
            claim_matrix = paper / "logic" / "claim-matrix.yaml"
            claim_matrix.write_text(
                '{"claims": [{"id": "C1", "level": "main", "statement": "Claim one.", '
                '"status": "supported", "evidence": [{"id": "E1", "source_id": "S1", '
                '"path": "paper/logic/claim-matrix.yaml", "relation": "direct", '
                '"summary": "Source."}], "figures": [], "assumptions": [], "caveats": [], '
                '"risks": [], "allowed_sections": []}]}',
                encoding="utf-8",
            )
            contracts = paper / "manuscript" / "section-contracts.yaml"
            contracts.write_text(
                """
{
  "sections": [
    {
      "id": "intro",
      "path": "paper/manuscript/sections/intro.md",
      "status": "ready-to-draft",
      "allowed_claims": ["C1"],
      "required_figures": [],
      "required_sources": ["paper/inputs/../../outside_claim.txt"],
      "required_caveats": [],
      "blocked_by": [],
      "chunk_policy": "single"
    }
  ]
}
""",
                encoding="utf-8",
            )

            # When: the section validator runs through its CLI.
            result = run_validator("validate_section_contracts.py", contracts, "--claims", claim_matrix)

        # Then: the traversal-shaped path is rejected.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("escapes paper root", result.stderr)

    def test_section_contracts_reject_traversal_section_file_path(self) -> None:
        # Given: a section contract whose section file path escapes paper/.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paper = root / "paper"
            (paper / "logic").mkdir(parents=True)
            (paper / "manuscript").mkdir(parents=True)
            (paper / "manuscript" / "sections").mkdir(parents=True)
            (root / "outside_section.md").write_text("---\nclaims: [C1]\n---\nOutside", encoding="utf-8")
            claim_matrix = paper / "logic" / "claim-matrix.yaml"
            claim_matrix.write_text(
                '{"claims": [{"id": "C1", "level": "main", "statement": "Claim one.", '
                '"status": "supported", "evidence": [{"id": "E1", "source_id": "S1", '
                '"path": "paper/logic/claim-matrix.yaml", "relation": "direct", '
                '"summary": "Source."}], "figures": [], "assumptions": [], "caveats": [], '
                '"risks": [], "allowed_sections": []}]}',
                encoding="utf-8",
            )
            contracts = paper / "manuscript" / "section-contracts.yaml"
            contracts.write_text(
                """
{
  "sections": [
    {
      "id": "intro",
      "path": "paper/manuscript/sections/../../../outside_section.md",
      "status": "ready-to-draft",
      "allowed_claims": ["C1"],
      "required_figures": [],
      "required_sources": [],
      "required_caveats": [],
      "blocked_by": [],
      "chunk_policy": "single"
    }
  ]
}
""",
                encoding="utf-8",
            )

            # When: the section validator runs through its CLI.
            result = run_validator("validate_section_contracts.py", contracts, "--claims", claim_matrix)

        # Then: the traversal-shaped path is rejected before front matter is read.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("escapes paper root", result.stderr)

    def test_notation_lint_passes_when_sections_use_declared_notation(self) -> None:
        # Given: the coherent fixture notation contract and section directory.
        notation = PAPER / "logic" / "notation.yaml"
        sections = PAPER / "manuscript" / "sections"

        # When: the lint runs through its CLI.
        result = run_validator("notation_lint.py", notation, sections)

        # Then: notation definitions and section declarations are accepted.
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_notation_lint_rejects_missing_required_definition(self) -> None:
        # Given: a section requiring notation absent from notation.yaml.
        notation = BAD / "notation" / "notation.yaml"
        sections = BAD / "notation" / "sections"

        # When: the lint runs through its CLI.
        result = run_validator("notation_lint.py", notation, sections)

        # Then: missing notation definitions fail the lint.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DeltaG", result.stderr)


if __name__ == "__main__":
    unittest.main()
