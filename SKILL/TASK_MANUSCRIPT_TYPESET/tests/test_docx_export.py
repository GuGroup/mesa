from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_support import EXPORT_SCRIPT, FIXTURE_PAPER, copy_fixture


class TestDocxExport(unittest.TestCase):
    def test_check_only_assembles_pandoc_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "docx"

            completed = subprocess.run(
                [sys.executable, str(EXPORT_SCRIPT), "--paper", str(FIXTURE_PAPER), "--out", str(out), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((out / "manuscript.md").is_file())
            self.assertIn("Figure Inventory", (out / "manuscript.md").read_text(encoding="utf-8"))
            self.assertIn('"mode": "docx"', (out / "docx-export-manifest.json").read_text(encoding="utf-8"))

    def test_rejects_missing_paper_root_with_actionable_error(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(EXPORT_SCRIPT), "--paper", "/tmp/mesa-typeset-missing", "--check-only"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("paper root does not exist", completed.stderr)

    def test_rejects_malformed_section_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper = copy_fixture(Path(tmp))
            (paper / "manuscript" / "section-contracts.yaml").write_text("sections:\n  - id: results\n", encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, str(EXPORT_SCRIPT), "--paper", str(paper), "--out", str(Path(tmp) / "out"), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("missing supported version header", completed.stderr)

    def test_rejects_missing_figure_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper = copy_fixture(Path(tmp))
            (paper / "figures" / "exported" / "fig1_energy_diagram.placeholder.svg").unlink()

            completed = subprocess.run(
                [sys.executable, str(EXPORT_SCRIPT), "--paper", str(paper), "--out", str(Path(tmp) / "out"), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("required file is missing", completed.stderr)
            self.assertNotIn("check-only passed", completed.stdout)

    def test_rejects_missing_reference_doc_before_pandoc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(EXPORT_SCRIPT),
                    "--paper",
                    str(FIXTURE_PAPER),
                    "--out",
                    str(Path(tmp) / "docx"),
                    "--pandoc-bin",
                    sys.executable,
                    "--reference-doc",
                    str(Path(tmp) / "missing-reference.docx"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("reference DOCX does not exist", completed.stderr)

    def test_real_export_fails_actionably_when_pandoc_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(EXPORT_SCRIPT),
                    "--paper",
                    str(FIXTURE_PAPER),
                    "--out",
                    str(Path(tmp) / "docx"),
                    "--pandoc-bin",
                    str(Path(tmp) / "missing-pandoc"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("Pandoc executable not found", completed.stderr)
            self.assertIn("--check-only", completed.stderr)


if __name__ == "__main__":
    unittest.main()
