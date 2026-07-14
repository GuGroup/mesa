from __future__ import annotations

import unittest
from pathlib import Path


class SgeTemplatesContractTests(unittest.TestCase):
    def test_bundled_templates_run_module_vasp_6_executables(self) -> None:
        template_root = Path(__file__).resolve().parents[1] / "templates" / "sge"

        for template in template_root.glob("*.sh"):
            content = template.read_text(encoding="utf-8")
            executable = "vasp_gam" if template.stem.endswith("gam") else "vasp_std"

            self.assertIn("module load vasp/6.3.2-vtst-vaspsol-beef-intel", content)
            self.assertIn(
                f"mpirun -machinefile $TMPDIR/machines -n $NSLOTS {executable}",
                content,
            )
            self.assertNotIn("vasp/5.", content)
            self.assertNotIn("VASP=", content)


if __name__ == "__main__":
    unittest.main()
