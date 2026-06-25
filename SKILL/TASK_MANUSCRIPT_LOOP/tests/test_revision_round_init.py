from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TASK_ROOT = Path(__file__).resolve().parents[1]
INIT_WORKSPACE_SCRIPT = TASK_ROOT / "scripts" / "init_paper_workspace.py"
INIT_ROUND_SCRIPT = TASK_ROOT / "scripts" / "init_revision_round.py"


class RevisionRoundInitTests(unittest.TestCase):
    def test_creates_revision_round_audit_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run([sys.executable, str(INIT_WORKSPACE_SCRIPT), "--root", str(root)], check=True)
            paper = root / "paper"

            result = subprocess.run(
                [sys.executable, str(INIT_ROUND_SCRIPT), "--paper", str(paper), "--round", "1"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            round_dir = paper / "revisions" / "round-001"
            self.assertTrue((round_dir / "reviewer-comments.raw").is_dir())
            self.assertTrue((round_dir / "patches").is_dir())
            self.assertTrue((round_dir / "author-response.yaml").is_file())
            self.assertTrue((round_dir / "change-plan.yaml").is_file())
            self.assertTrue((round_dir / "changed-files.md").is_file())
            self.assertTrue((round_dir / "verification.md").is_file())

    def test_preserves_nonempty_round_files_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run([sys.executable, str(INIT_WORKSPACE_SCRIPT), "--root", str(root)], check=True)
            paper = root / "paper"
            subprocess.run([sys.executable, str(INIT_ROUND_SCRIPT), "--paper", str(paper), "--round", "round-002"], check=True)
            response = paper / "revisions" / "round-002" / "author-response.yaml"
            response.write_text("custom: keep me\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(INIT_ROUND_SCRIPT), "--paper", str(paper), "--round", "2"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(response.read_text(encoding="utf-8"), "custom: keep me\n")

    def test_rejects_invalid_round_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run([sys.executable, str(INIT_WORKSPACE_SCRIPT), "--root", str(root)], check=True)

            result = subprocess.run(
                [sys.executable, str(INIT_ROUND_SCRIPT), "--paper", str(root / "paper"), "--round", "../bad"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("round must be an integer", result.stderr)


if __name__ == "__main__":
    unittest.main()
