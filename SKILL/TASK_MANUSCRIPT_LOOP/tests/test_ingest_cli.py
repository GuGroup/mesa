import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TASK_ROOT = Path(__file__).resolve().parents[1]
INIT_SCRIPT = TASK_ROOT / "scripts" / "init_paper_workspace.py"
INGEST_SCRIPT = TASK_ROOT / "scripts" / "ingest_mesa_outputs.py"
FIXTURE_OUTPUTS = TASK_ROOT / "examples" / "fixture_project" / "mesa_outputs"
TYPESET_SCRIPT = TASK_ROOT.parents[0] / "TASK_MANUSCRIPT_TYPESET" / "scripts" / "export_docx.py"
VALIDATORS = (
    ("validate_claim_matrix.py", "logic/claim-matrix.yaml"),
    ("validate_figure_map.py", "logic/figure-map.yaml"),
    ("validate_reviewer_issues.py", "state/reviewer-issues.yaml"),
    ("validate_section_contracts.py", "manuscript/section-contracts.yaml"),
)


class MesaIngestCliTests(unittest.TestCase):
    def test_ingests_fixture_outputs_into_manifest_and_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run([sys.executable, str(INIT_SCRIPT), "--root", str(root)], check=True)
            paper = root / "paper"

            result = subprocess.run(
                [
                    sys.executable,
                    str(INGEST_SCRIPT),
                    "--paper",
                    str(paper),
                    "--input",
                    str(FIXTURE_OUTPUTS),
                    "--out",
                    str(paper / "inputs" / "manifest.yaml"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = (paper / "inputs" / "manifest.yaml").read_text(encoding="utf-8")
            inventory = (paper / "logic" / "result-inventory.md").read_text(encoding="utf-8")
            self.assertIn("id: result-co-pt111-energy", manifest)
            self.assertIn("kind: structure", manifest)
            self.assertIn("claim_role: candidate-evidence", manifest)
            self.assertIn("result-co-pt111-energy", inventory)
            self.assertTrue((paper / "inputs" / "results" / "co_pt111_energy.yaml").is_file())
            self.assertTrue((paper / "inputs" / "structures" / "CO_on_Pt111_POSCAR").is_file())
            self.assertTrue((paper / "inputs" / "tables" / "energy_summary.csv").is_file())

    def test_fresh_ingest_generates_valid_minimum_gate_files_for_e2e(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run([sys.executable, str(INIT_SCRIPT), "--root", str(root)], check=True)
            paper = root / "paper"

            result = subprocess.run(
                [
                    sys.executable,
                    str(INGEST_SCRIPT),
                    "--paper",
                    str(paper),
                    "--input",
                    str(FIXTURE_OUTPUTS),
                    "--out",
                    str(paper / "inputs" / "manifest.yaml"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            for script_name, rel_path in VALIDATORS:
                validation = subprocess.run(
                    [
                        sys.executable,
                        str(TASK_ROOT / "scripts" / script_name),
                        str(paper / rel_path),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(validation.returncode, 0, validation.stderr)
            notation = subprocess.run(
                [
                    sys.executable,
                    str(TASK_ROOT / "scripts" / "notation_lint.py"),
                    str(paper / "logic" / "notation.yaml"),
                    str(paper / "manuscript" / "sections"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(notation.returncode, 0, notation.stderr)
            typeset = subprocess.run(
                [
                    sys.executable,
                    str(TYPESET_SCRIPT),
                    "--paper",
                    str(paper),
                    "--out",
                    str(root / "typeset"),
                    "--check-only",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(typeset.returncode, 0, typeset.stderr)
            self.assertIn("claims:", (paper / "logic" / "claim-matrix.yaml").read_text(encoding="utf-8"))
            self.assertTrue((paper / "figures" / "exported" / "fig1_energy_diagram.placeholder.svg").is_file())

    def test_rejects_missing_input_with_clear_nonzero_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run([sys.executable, str(INIT_SCRIPT), "--root", str(root)], check=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(INGEST_SCRIPT),
                    "--paper",
                    str(root / "paper"),
                    "--input",
                    str(root / "does-not-exist"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("input path does not exist", result.stderr)

    def test_rejects_malformed_envelope_with_clear_nonzero_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "mesa_outputs" / "task_envelopes"
            source.mkdir(parents=True)
            (source / "bad.json").write_text('{"status": "success", "data": {}}', encoding="utf-8")
            subprocess.run([sys.executable, str(INIT_SCRIPT), "--root", str(root)], check=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(INGEST_SCRIPT),
                    "--paper",
                    str(root / "paper"),
                    "--input",
                    str(root / "mesa_outputs"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing required envelope field", result.stderr)

    def test_rejects_selected_frames_path_outside_input_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outputs = root / "mesa_outputs"
            shutil.copytree(FIXTURE_OUTPUTS, outputs)
            outside = root / "outside_selected_frames.extxyz"
            outside.write_text("1\nProperties=species:S:1:pos:R:3\nX 9.0 9.0 9.0\n", encoding="utf-8")
            summary = outputs / "analyzer_runs" / "run-co-pt111" / "analysis_summary.json"
            data = json.loads(summary.read_text(encoding="utf-8"))
            data["output_paths"]["selected_frames"] = "../../../outside_selected_frames.extxyz"
            summary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            subprocess.run([sys.executable, str(INIT_SCRIPT), "--root", str(root)], check=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(INGEST_SCRIPT),
                    "--paper",
                    str(root / "paper"),
                    "--input",
                    str(outputs),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("selected_frames path escapes input root", result.stderr)


if __name__ == "__main__":
    unittest.main()
