import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TASK_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TASK_ROOT.parents[1]
MODULE_PATH = TASK_ROOT / "MYSKILL" / "reaction_energy_evaluation.py"


def load_module():
    spec = importlib.util.spec_from_file_location("reaction_energy_evaluation", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ReactionEnergyEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_no3rr_csv_ranks_nicoo2_first(self):
        result = self.module.run(
            {
                "csv_path": "no3rr_diagram.csv",
                "reaction_type": "NO3RR",
                "experiment": {"NiCoO2": 0.2},
            },
            {"workdir": str(REPO_ROOT)},
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["task_id"], "TASK2")
        self.assertEqual(result["skill"], "reaction_energy_evaluation")
        self.assertEqual(result["data"]["ranking"][0]["catalyst"], "NiCoO2")
        self.assertEqual(result["data"]["ranking"][0]["pds"], "NO3- -> *NO3")
        self.assertAlmostEqual(result["data"]["ranking"][0]["eta_calc_v"], 0.239315395)
        self.assertAlmostEqual(
            result["data"]["experiment_comparison"]["NiCoO2"]["absolute_difference_mv"],
            39.315395,
            places=5,
        )

    def test_her_csv_uses_h_descriptor(self):
        result = self.module.run(
            {"csv_path": "HER.csv", "reaction_type": "HER"},
            {"workdir": str(REPO_ROOT)},
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["reaction_type"], "HER")
        self.assertEqual(result["data"]["ranking"][0]["catalyst"], "CoO")
        self.assertAlmostEqual(result["data"]["ranking"][0]["delta_g_h_ev"], 0.858184431)

    def test_invalid_input_returns_failure(self):
        result = self.module.run(["not", "a", "dict"])

        self.assertEqual(result["status"], "failure")
        self.assertEqual(result["next_action"]["recommendation"], "needs_human_review")
        self.assertEqual(result["errors"][0]["type"], "TypeError")

    def test_cli_writes_output_file(self):
        temp_root = TASK_ROOT / "tests" / ".tmp"
        temp_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.json"
            output_path = temp_path / "output.json"
            input_path.write_text(
                json.dumps({"csv_path": "HER.csv", "reaction_type": "HER"}),
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
                    "--workdir",
                    str(REPO_ROOT),
                    "--dry-run",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0)
            output = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(output["status"], "success")
            self.assertEqual(output["task_id"], "TASK2")
            self.assertEqual(output["data"]["reaction_type"], "HER")


if __name__ == "__main__":
    unittest.main()
