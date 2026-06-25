from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_support import EXPORT_SCRIPT, copy_fixture


class TestDocxExportValidation(unittest.TestCase):
    def test_rejects_math_inside_code_span(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper = copy_fixture(Path(tmp))
            (paper / "manuscript" / "sections" / "results.md").write_text(
                "The fixture result is `$E_{\\mathrm{ads}} = -1.42$ eV` and should fail export.\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(EXPORT_SCRIPT), "--paper", str(paper), "--out", str(Path(tmp) / "out"), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("math expression is inside a code span", completed.stderr)

    def test_allows_inline_italics_inside_figure_caption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper = copy_fixture(Path(tmp))
            figure_map = paper / "logic" / "figure-map.yaml"
            figure_map.write_text(
                figure_map.read_text(encoding="utf-8").replace(
                    "caption: Fixture adsorption-energy evidence map showing",
                    "caption: Fixture *ab initio* adsorption-energy evidence map showing",
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(EXPORT_SCRIPT), "--paper", str(paper), "--out", str(Path(tmp) / "out"), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            manuscript = (Path(tmp) / "out" / "manuscript.md").read_text(encoding="utf-8")
            self.assertIn("Fixture *ab initio* adsorption-energy evidence map", manuscript)

    def test_allows_latin_italics_in_manuscript_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper = copy_fixture(Path(tmp))
            (paper / "manuscript" / "sections" / "results.md").write_text(
                "This body paragraph uses *ab initio* as accepted prose styling.\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(EXPORT_SCRIPT), "--paper", str(paper), "--out", str(Path(tmp) / "out"), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_rejects_pipe_lead_in_results_and_discussion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper = copy_fixture(Path(tmp))
            (paper / "manuscript" / "sections" / "results.md").write_text(
                "**Fixture result** | This pipe form belongs in SI, not Results and Discussion.\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(EXPORT_SCRIPT), "--paper", str(paper), "--out", str(Path(tmp) / "out"), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("Results and Discussion topic leads must not use '|'", completed.stderr)

    def test_rejects_soft_break_after_results_and_discussion_lead(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper = copy_fixture(Path(tmp))
            (paper / "manuscript" / "sections" / "results.md").write_text(
                "**Fixture result**\nThis body starts too soon for a Word paragraph break.\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(EXPORT_SCRIPT), "--paper", str(paper), "--out", str(Path(tmp) / "out"), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("topic leads must be followed by a blank line", completed.stderr)

    def test_allows_blank_line_after_results_and_discussion_lead(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper = copy_fixture(Path(tmp))
            (paper / "manuscript" / "sections" / "results.md").write_text(
                "**Fixture result**\n\nThis body starts after a real paragraph break.\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(EXPORT_SCRIPT), "--paper", str(paper), "--out", str(Path(tmp) / "out"), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_allows_pipe_lead_in_supplementary_information(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper = copy_fixture(Path(tmp))
            section_contract = paper / "manuscript" / "section-contracts.yaml"
            section_contract.write_text(
                section_contract.read_text(encoding="utf-8")
                + "  - id: si\n"
                + "    path: paper/manuscript/sections/si.md\n"
                + "    status: ready-to-draft\n"
                + "    allowed_claims: []\n"
                + "    required_figures: []\n"
                + "    required_sources: []\n"
                + "    required_caveats: []\n"
                + "    blocked_by: []\n"
                + "    chunk_policy:\n"
                + "      unit: si-block\n"
                + "      locked_chunks: []\n",
                encoding="utf-8",
            )
            (paper / "manuscript" / "sections" / "si.md").write_text(
                "**Computational setup** | This compact SI block keeps the pipe form.\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(EXPORT_SCRIPT), "--paper", str(paper), "--out", str(Path(tmp) / "out"), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            manuscript = (Path(tmp) / "out" / "manuscript.md").read_text(encoding="utf-8")
            self.assertIn("## Supplementary Information", manuscript)
            self.assertIn("**Computational setup** | This compact SI block keeps the pipe form.", manuscript)


if __name__ == "__main__":
    unittest.main()
