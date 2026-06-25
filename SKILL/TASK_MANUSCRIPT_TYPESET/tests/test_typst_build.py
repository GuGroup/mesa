from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_support import BUILD_SCRIPT, FIXTURE_PAPER, copy_fixture


class TestTypstBuild(unittest.TestCase):
    def test_check_only_assembles_fixture_without_external_typst(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "build"

            completed = subprocess.run(
                [sys.executable, str(BUILD_SCRIPT), "--paper", str(FIXTURE_PAPER), "--out", str(out), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((out / "manuscript.typ").is_file())
            self.assertTrue((out / "assets" / "nature-mesa.typ").is_file())
            self.assertIn("Cross-reference QA: passed", (out / "qa" / "crossref-qa.txt").read_text(encoding="utf-8"))
            self.assertIn('"source_digest"', (out / "build-manifest.json").read_text(encoding="utf-8"))

    def test_rejects_missing_paper_root_with_actionable_error(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(BUILD_SCRIPT), "--paper", "/tmp/mesa-typeset-missing", "--check-only"],
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
                [sys.executable, str(BUILD_SCRIPT), "--paper", str(paper), "--out", str(Path(tmp) / "out"), "--check-only"],
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
                [sys.executable, str(BUILD_SCRIPT), "--paper", str(paper), "--out", str(Path(tmp) / "out"), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("required file is missing", completed.stderr)
            self.assertNotIn("check-only passed", completed.stdout)

    def test_escapes_prompt_like_markdown_as_raw_typst(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper = copy_fixture(Path(tmp))
            section = paper / "manuscript" / "sections" / "results.md"
            section.write_text(section.read_text(encoding="utf-8") + "\n#show: panic\n```inner```\n", encoding="utf-8")
            out = Path(tmp) / "out"

            completed = subprocess.run(
                [sys.executable, str(BUILD_SCRIPT), "--paper", str(paper), "--out", str(out), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            typst = (out / "manuscript.typ").read_text(encoding="utf-8")
            self.assertIn("````md", typst)
            self.assertIn("#show: panic", typst)

    def test_escapes_yaml_metadata_as_typst_string_literals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper = copy_fixture(Path(tmp))
            injected = 'Figure 1"); #show: panic; ("\\\\ `tick` (note)'
            exported = 'paper/figures/exported/fig1_"; #show (panic) \\\\ `tick`.svg'
            (paper.parent / exported).write_text("<svg />", encoding="utf-8")
            (paper / "logic" / "figure-map.yaml").write_text(
                "\n".join(
                    (
                        "version: 1",
                        "figures:",
                        "  - id: F1",
                        f"    label: {injected}",
                        "    role: main",
                        f"    title: {injected}",
                        "    claim_ids: [C1]",
                        "    source_files:",
                        "      - paper/figures/source/fig1_energy_diagram.spec.yaml",
                        "    exported_files:",
                        f"      - {exported}",
                        "    qa_files:",
                        "      - paper/figures/qa/fig1_energy_diagram.md",
                        "    status: qa-passed",
                        "    blockers: []",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            section_contract = paper / "manuscript" / "section-contracts.yaml"
            section_contract.write_text(
                section_contract.read_text(encoding="utf-8").replace("id: results", f"id: {injected}", 1),
                encoding="utf-8",
            )
            out = Path(tmp) / "out"

            completed = subprocess.run(
                [sys.executable, str(BUILD_SCRIPT), "--paper", str(paper), "--out", str(out), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            typst = (out / "manuscript.typ").read_text(encoding="utf-8")
            self.assertNotIn('"); #show', typst)
            self.assertNotIn("; #show", typst)
            self.assertNotIn("`tick`", typst)
            self.assertIn("\\u{23}show", typst)

    def test_detects_stale_generated_pdf_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper = copy_fixture(Path(tmp))
            out = Path(tmp) / "out"
            subprocess.run(
                [sys.executable, str(BUILD_SCRIPT), "--paper", str(paper), "--out", str(out), "--check-only"],
                check=True,
            )
            (out / "manuscript.pdf").write_text("old pdf", encoding="utf-8")
            section = paper / "manuscript" / "sections" / "results.md"
            section.write_text(section.read_text(encoding="utf-8") + "\nChanged source.\n", encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, str(BUILD_SCRIPT), "--paper", str(paper), "--out", str(out), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("stale", completed.stderr)

    def test_real_build_fails_actionably_when_typst_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SCRIPT),
                    "--paper",
                    str(FIXTURE_PAPER),
                    "--out",
                    str(Path(tmp) / "out"),
                    "--typst-bin",
                    str(Path(tmp) / "missing-typst"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("Typst executable not found", completed.stderr)
            self.assertIn("--check-only", completed.stderr)


if __name__ == "__main__":
    unittest.main()
