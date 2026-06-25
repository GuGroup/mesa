from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

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
            manuscript = (out / "manuscript.md").read_text(encoding="utf-8")
            self.assertIn("Figure Captions", manuscript)
            self.assertIn("**Figure 1 |** Fixture adsorption-energy evidence map showing", manuscript)
            self.assertNotIn("fig1_energy_diagram.placeholder.svg", manuscript)
            self.assertNotIn("allowed_claims:", manuscript)
            self.assertIn('"mode": "docx"', (out / "docx-export-manifest.json").read_text(encoding="utf-8"))

    def test_export_removes_duplicate_section_self_heading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper = copy_fixture(Path(tmp))
            (paper / "manuscript" / "sections" / "results.md").write_text(
                "# Results\n\nCO binds in the fixture result.\n",
                encoding="utf-8",
            )
            out = Path(tmp) / "docx"

            completed = subprocess.run(
                [sys.executable, str(EXPORT_SCRIPT), "--paper", str(paper), "--out", str(out), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            manuscript = (out / "manuscript.md").read_text(encoding="utf-8")
            self.assertIn("## Results and Discussion\n\nCO binds in the fixture result.", manuscript)
            self.assertNotIn("## Results and Discussion\n\n# Results", manuscript)

    def test_export_uses_manuscript_display_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "docx"

            completed = subprocess.run(
                [sys.executable, str(EXPORT_SCRIPT), "--paper", str(FIXTURE_PAPER), "--out", str(out), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            manuscript = (out / "manuscript.md").read_text(encoding="utf-8")
            abstract_at = manuscript.index("## Abstract")
            results_at = manuscript.index("## Results and Discussion")
            methods_at = manuscript.index("## Computational Methods")
            self.assertLess(abstract_at, results_at)
            self.assertLess(results_at, methods_at)

    def test_word_style_postprocess_sets_requested_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / "minimal.docx"
            styles = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
                '<w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="Caption"/><w:rPr><w:i/></w:rPr></w:style>'
                '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>'
                "</w:styles>"
            )
            document = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body>"
                "<w:p><w:r><w:t>Figure 1 evidence check | This is discussion text.</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>Figure 1 | Fixture adsorption-energy evidence map</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>Body text.</w:t></w:r></w:p>"
                "</w:body>"
                "</w:document>"
            )
            with ZipFile(docx, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/styles.xml", styles)
                archive.writestr("word/document.xml", document)

            completed = subprocess.run(
                [sys.executable, str(EXPORT_SCRIPT.parent / "word_styles.py"), str(docx)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            with ZipFile(docx) as archive:
                patched = archive.read("word/styles.xml").decode("utf-8")
            self.assertIn('w:ascii="Times New Roman"', patched)
            self.assertIn('w:styleId="Normal"', patched)
            self.assertIn('w:line="360"', patched)
            self.assertIn('w:styleId="Caption"', patched)
            self.assertIn('w:sz w:val="22"', patched)
            self.assertIn('w:i w:val="0"', patched)
            self.assertIn('w:line="240"', patched)
            self.assertIn('w:styleId="Heading1"', patched)
            with ZipFile(docx) as archive:
                patched_document = archive.read("word/document.xml").decode("utf-8")
            self.assertIn('w:pStyle w:val="Caption"', patched_document)
            self.assertEqual(patched_document.count('w:pStyle w:val="Caption"'), 1)

    def test_export_bolds_figure_caption_label_in_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "docx"

            completed = subprocess.run(
                [sys.executable, str(EXPORT_SCRIPT), "--paper", str(FIXTURE_PAPER), "--out", str(out), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            manuscript = (out / "manuscript.md").read_text(encoding="utf-8")
            self.assertRegex(manuscript, r"\*\*Figure 1 \|\*\* [^\n]+")

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
