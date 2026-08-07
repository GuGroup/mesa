#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WRITER = load_module(
    "write_methods_sections_security",
    "methods/write-methods-sections/scripts/write_methods_sections.py",
)


class FormalismGuideSecurityTests(unittest.TestCase):
    def test_bundled_guide_is_accepted(self) -> None:
        guide = WRITER.load_formalism_guide("")

        self.assertIn("Methods Formalism Guide", guide)

    def test_external_guide_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            external = Path(tempdir) / "secret.txt"
            external.write_text("not prompt material", encoding="utf-8")

            with self.assertRaises(WRITER.FormalismGuideError):
                WRITER.load_formalism_guide(str(external))

    def test_symlink_guide_is_rejected(self) -> None:
        guide_root = WRITER.default_formalism_guide().parent
        with tempfile.TemporaryDirectory() as tempdir:
            external = Path(tempdir) / "secret.txt"
            external.write_text("not prompt material", encoding="utf-8")
            with tempfile.TemporaryDirectory(dir=guide_root) as bundled_tempdir:
                link = Path(bundled_tempdir) / "linked-guide.md"
                link.symlink_to(external)

                with self.assertRaises(WRITER.FormalismGuideError):
                    WRITER.load_formalism_guide(str(link))

    def test_oversized_bundled_guide_is_rejected(self) -> None:
        guide_root = WRITER.default_formalism_guide().parent
        with tempfile.TemporaryDirectory(dir=guide_root) as bundled_tempdir:
            oversized = Path(bundled_tempdir) / "oversized-guide.md"
            oversized.write_text("x" * (WRITER.MAX_FORMALISM_GUIDE_BYTES + 1), encoding="utf-8")

            with self.assertRaises(WRITER.FormalismGuideError):
                WRITER.load_formalism_guide(str(oversized))


if __name__ == "__main__":
    unittest.main()
