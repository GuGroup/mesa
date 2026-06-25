from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_support import EXPORT_SCRIPT, FIXTURE_PAPER


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
