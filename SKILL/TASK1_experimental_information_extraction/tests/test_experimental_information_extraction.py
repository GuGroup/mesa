import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = TASK_ROOT / "MYSKILL" / "experimental_information_extraction.py"


def load_module():
    spec = importlib.util.spec_from_file_location("experimental_information_extraction", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ExperimentalInformationExtractionTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_run_returns_standard_success_output(self):
        result = self.module.run(
            {
                "experiment_id": "EXP-1",
                "raw_text": "NiCoO2 showed 0.20 V overpotential compared with NiO.",
                "hypotheses": ["Bimetallic sites improve activity."],
            }
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["task_id"], "TASK1")
        self.assertEqual(result["skill"], "experimental_information_extraction")
        self.assertEqual(result["next_action"]["recommendation"], "continue")
        self.assertIn("data", result)
        self.assertIn("errors", result)
        self.assertEqual(result["errors"], [])
        labels = {item["label"] for item in result["data"]["materials"]}
        self.assertIn("NiCoO2", labels)
        self.assertIn("NiO", labels)
        self.assertGreaterEqual(len(result["data"]["measurements"]), 1)

    def test_missing_fields_returns_partial_with_uncertainties(self):
        result = self.module.run({"raw_text": "Catalyst sample was prepared."})

        self.assertEqual(result["status"], "partial")
        uncertainty_fields = {item["field"] for item in result["data"]["uncertainties"]}
        self.assertIn("materials", uncertainty_fields)
        self.assertIn("measurements", uncertainty_fields)
        self.assertIn("hypotheses", uncertainty_fields)

    def test_invalid_input_returns_failure(self):
        result = self.module.run(["not", "a", "dict"])

        self.assertEqual(result["status"], "failure")
        self.assertEqual(result["next_action"]["recommendation"], "needs_human_review")
        self.assertEqual(result["errors"][0]["type"], "ValidationError")

    def test_cli_writes_output_file(self):
        temp_root = TASK_ROOT / "tests" / ".tmp"
        temp_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.json"
            output_path = temp_path / "output.json"
            input_path.write_text(
                json.dumps(
                    {
                        "raw_text": "NiCoO2 showed 0.20 V overpotential.",
                        "hypotheses": ["Ni-Co synergy improves activity."],
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--dry-run",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0)
            output = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertIn(output["status"], {"success", "partial"})
            self.assertEqual(output["task_id"], "TASK1")


if __name__ == "__main__":
    unittest.main()
