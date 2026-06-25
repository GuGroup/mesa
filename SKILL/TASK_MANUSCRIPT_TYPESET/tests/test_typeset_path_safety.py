from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_support import EXPORT_SCRIPT, copy_fixture


class TestTypesetPathSafety(unittest.TestCase):
    def test_rejects_traversal_section_path_without_exporting_outside_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper = copy_fixture(Path(tmp))
            outside = paper.parent / "outside.md"
            outside.write_text("outside paper secret\n", encoding="utf-8")
            section_contract = paper / "manuscript" / "section-contracts.yaml"
            section_contract.write_text(
                section_contract.read_text(encoding="utf-8").replace(
                    "path: paper/manuscript/sections/results.md",
                    "path: paper/../outside.md",
                    1,
                ),
                encoding="utf-8",
            )
            out = Path(tmp) / "out"

            completed = subprocess.run(
                [sys.executable, str(EXPORT_SCRIPT), "--paper", str(paper), "--out", str(out), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("path escapes paper root", completed.stderr)
            manuscript = out / "manuscript.md"
            if manuscript.exists():
                self.assertNotIn("outside paper secret", manuscript.read_text(encoding="utf-8"))

    def test_rejects_symlink_section_path_without_exporting_outside_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper = copy_fixture(Path(tmp))
            outside_dir = paper.parent / "outside-dir"
            outside_dir.mkdir()
            outside = outside_dir / "outside.md"
            outside.write_text("outside symlink secret\n", encoding="utf-8")
            symlink = paper / "linked"
            symlink.symlink_to(outside_dir, target_is_directory=True)
            section_contract = paper / "manuscript" / "section-contracts.yaml"
            section_contract.write_text(
                section_contract.read_text(encoding="utf-8").replace(
                    "path: paper/manuscript/sections/results.md",
                    "path: paper/linked/outside.md",
                    1,
                ),
                encoding="utf-8",
            )
            out = Path(tmp) / "out"

            completed = subprocess.run(
                [sys.executable, str(EXPORT_SCRIPT), "--paper", str(paper), "--out", str(out), "--check-only"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("path escapes paper root", completed.stderr)
            manuscript = out / "manuscript.md"
            if manuscript.exists():
                self.assertNotIn("outside symlink secret", manuscript.read_text(encoding="utf-8"))

    def test_rejects_absolute_section_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paper = copy_fixture(Path(tmp))
            outside = paper.parent / "outside.md"
            outside.write_text("outside absolute secret\n", encoding="utf-8")
            section_contract = paper / "manuscript" / "section-contracts.yaml"
            section_contract.write_text(
                section_contract.read_text(encoding="utf-8").replace(
                    "path: paper/manuscript/sections/results.md",
                    f"path: {outside}",
                    1,
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(EXPORT_SCRIPT),
                    "--paper",
                    str(paper),
                    "--out",
                    str(Path(tmp) / "docx"),
                    "--check-only",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("path must be paper-relative", completed.stderr)


if __name__ == "__main__":
    unittest.main()
