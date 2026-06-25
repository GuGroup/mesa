import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TASK_ROOT = Path(__file__).resolve().parents[1]
INIT_SCRIPT = TASK_ROOT / "scripts" / "init_paper_workspace.py"


class WorkspaceInitTests(unittest.TestCase):
    def test_creates_paper_contract_when_root_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = subprocess.run(
                [sys.executable, str(INIT_SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            paper = root / "paper"
            self.assertTrue((paper / "inputs" / "results").is_dir())
            self.assertTrue((paper / "inputs" / "structures").is_dir())
            self.assertTrue((paper / "logic" / "claim-matrix.yaml").is_file())
            self.assertTrue((paper / "logic" / "figure-map.yaml").is_file())
            self.assertTrue((paper / "revisions" / "README.md").is_file())
            self.assertTrue((paper / "manuscript" / "sections" / "results.md").is_file())
            self.assertIn("stage: intake", (paper / "state" / "current-stage.yaml").read_text())

    def test_is_idempotent_and_preserves_nonempty_files_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run([sys.executable, str(INIT_SCRIPT), "--root", str(root)], check=True)
            claim_matrix = root / "paper" / "logic" / "claim-matrix.yaml"
            claim_matrix.write_text("custom: keep me\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(INIT_SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(claim_matrix.read_text(encoding="utf-8"), "custom: keep me\n")

    def test_force_rewrites_seed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run([sys.executable, str(INIT_SCRIPT), "--root", str(root)], check=True)
            stage = root / "paper" / "state" / "current-stage.yaml"
            stage.write_text("stage: stale\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(INIT_SCRIPT), "--root", str(root), "--force"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("stage: intake", stage.read_text(encoding="utf-8"))
            self.assertNotIn("stale", stage.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
