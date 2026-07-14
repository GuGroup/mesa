from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
GATE = REPO_ROOT / "SKILL/orchestration/validate-recipe-execution/scripts/check_recipe_execution.py"
RECORDER = REPO_ROOT / "SKILL/orchestration/record-missing-evidence/scripts/record_missing_evidence.py"


class GateContractTest(unittest.TestCase):
    def test_empty_recipe_tree_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recipe_root = root / "S1_explicit_recipe"
            recipe_root.mkdir()
            result = subprocess.run(
                [
                    sys.executable,
                    str(GATE),
                    "--recipe-root",
                    str(recipe_root),
                    "--project-root",
                    str(root),
                    "--outdir",
                    str(root / "gate"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            report = json.loads((root / "gate/recipe_execution_gate_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["path_issues"][0]["code"], "no_calculations")

    def test_missing_evidence_manifest_passes_the_recipe_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calc = root / "S1_explicit_recipe/P001_analysis/calculations/C001_charge"
            execution = calc / "execution"
            execution.mkdir(parents=True)
            recipe = calc / "recipe.json"
            recipe.write_text(json.dumps({"procedure_id": "P001"}), encoding="utf-8")
            spec = root / "missing_evidence_spec.json"
            spec.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "strategy_id": "S1",
                        "procedure_id": "P001",
                        "source_recipe": str(recipe.relative_to(root)),
                        "status": "unresolved",
                        "reason": "Charge density was not generated.",
                        "not_substituted_with_proxy": True,
                        "requirements": [
                            {
                                "calculation_id": "C001",
                                "label": "charge analysis",
                                "status": "unresolved",
                                "missing_artifacts": ["charge_density"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            recorded = subprocess.run(
                [
                    sys.executable,
                    str(RECORDER),
                    "--input",
                    str(spec),
                    "--outdir",
                    str(execution),
                    "--project-root",
                    str(root),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)

            checked = subprocess.run(
                [
                    sys.executable,
                    str(GATE),
                    "--recipe-root",
                    str(root / "S1_explicit_recipe"),
                    "--project-root",
                    str(root),
                    "--outdir",
                    str(root / "gate"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            report = json.loads((root / "gate/recipe_execution_gate_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["manifest_count"], 1)


if __name__ == "__main__":
    unittest.main()
