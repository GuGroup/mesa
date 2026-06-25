import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TASK_ROOT = Path(__file__).resolve().parents[1]
INIT_SCRIPT = TASK_ROOT / "scripts" / "init_paper_workspace.py"
INGEST_SCRIPT = TASK_ROOT / "scripts" / "ingest_mesa_outputs.py"
FIXTURE_OUTPUTS = TASK_ROOT / "examples" / "fixture_project" / "mesa_outputs"


class MesaIngestPreservationTests(unittest.TestCase):
    def test_preserves_user_authored_claim_matrix_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run([sys.executable, str(INIT_SCRIPT), "--root", str(root)], check=True)
            paper = root / "paper"
            claim_matrix = paper / "logic" / "claim-matrix.yaml"
            custom = "custom: keep me\n"
            claim_matrix.write_text(custom, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(INGEST_SCRIPT),
                    "--paper",
                    str(paper),
                    "--input",
                    str(FIXTURE_OUTPUTS),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("preserved=paper/logic/claim-matrix.yaml", result.stdout)
            self.assertEqual(claim_matrix.read_text(encoding="utf-8"), custom)

    def test_does_not_copy_sibling_paper_support_files(self) -> None:
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
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((paper / "inputs" / "prior-notes" / "project-context.md").exists())
            exported = paper / "figures" / "exported" / "fig1_energy_diagram.placeholder.svg"
            self.assertTrue(exported.exists())
            self.assertTrue(exported.read_text(encoding="utf-8").startswith("<!-- generated-by: ingest_mesa_outputs.py -->"))

    def test_force_rewrites_generated_manifest_and_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run([sys.executable, str(INIT_SCRIPT), "--root", str(root)], check=True)
            paper = root / "paper"
            manifest = paper / "inputs" / "manifest.yaml"
            inventory = paper / "logic" / "result-inventory.md"
            manifest.write_text("custom manifest\n", encoding="utf-8")
            inventory.write_text("custom inventory\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(INGEST_SCRIPT),
                    "--paper",
                    str(paper),
                    "--input",
                    str(FIXTURE_OUTPUTS),
                    "--force",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("id: result-co-pt111-energy", manifest.read_text(encoding="utf-8"))
            self.assertIn("result-co-pt111-energy", inventory.read_text(encoding="utf-8"))

    def test_force_rewrites_generated_gate_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run([sys.executable, str(INIT_SCRIPT), "--root", str(root)], check=True)
            paper = root / "paper"
            claim_matrix = paper / "logic" / "claim-matrix.yaml"
            claim_matrix.write_text(
                "# generated-by: ingest_mesa_outputs.py\nversion: 1\ntarget: nature-family\nclaims: []\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(INGEST_SCRIPT),
                    "--paper",
                    str(paper),
                    "--input",
                    str(FIXTURE_OUTPUTS),
                    "--force",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("id: C1", claim_matrix.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
