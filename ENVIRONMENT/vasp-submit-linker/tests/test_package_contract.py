from __future__ import annotations

import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TEMPLATES = {
    "vasp_submit/templates/sge/preset48gam.sh",
    "vasp_submit/templates/sge/preset48std.sh",
    "vasp_submit/templates/sge/preset64gam.sh",
    "vasp_submit/templates/sge/preset64std.sh",
    "vasp_submit/templates/sge/presetg018gam.sh",
    "vasp_submit/templates/sge/presetg018std.sh",
    "vasp_submit/templates/sge/presetg01gam.sh",
    "vasp_submit/templates/sge/presetg01std.sh",
}


class PackageContractTest(unittest.TestCase):
    def test_wheel_contains_runtime_submit_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                ["uv", "build", "--wheel", "--out-dir", tmp],
                cwd=PACKAGE_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            wheel = next(Path(tmp).glob("*.whl"))
            with zipfile.ZipFile(wheel) as archive:
                names = set(archive.namelist())

        self.assertTrue(EXPECTED_TEMPLATES.issubset(names))


if __name__ == "__main__":
    unittest.main()
