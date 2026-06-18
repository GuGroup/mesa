from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


CONTROLLER_PATH = (
    Path(__file__).resolve().parents[1]
    / "MYSKILL"
    / "mlip_workflow_controller.py"
)


def load_controller():
    spec = importlib.util.spec_from_file_location("mlip_workflow_controller", CONTROLLER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_minimal_poscar(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "Si test",
                "1.0",
                "5.43 0.0 0.0",
                "0.0 5.43 0.0",
                "0.0 0.0 5.43",
                "Si",
                "2",
                "Direct",
                "0.0 0.0 0.0",
                "0.25 0.25 0.25",
                "",
            ]
        ),
        encoding="utf-8",
    )


class MlipWorkflowControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = load_controller()

    def test_dry_run_is_default_and_writes_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            poscar = workdir / "POSCAR"
            write_minimal_poscar(poscar)

            result = self.controller.run({"poscar_path": "POSCAR"}, {"workdir": str(workdir)})

            self.assertEqual(result["status"], "success")
            self.assertTrue(result["data"]["dry_run"])
            self.assertEqual(result["data"]["settings"]["model"], "uma-s-1p2")
            self.assertEqual(result["data"]["settings"]["task"], "omat")
            self.assertEqual(result["data"]["settings"]["device"], "cuda")
            self.assertEqual(result["data"]["settings"]["relax_type"], "geometry")
            self.assertEqual(result["data"]["settings"]["fmax"], 0.05)
            self.assertEqual(result["data"]["settings"]["steps"], 300)
            self.assertEqual(result["data"]["qsub_command"][0], "qsub")
            self.assertTrue((workdir / "results" / "mlip_uncertainty_report.json").exists())
            self.assertTrue((workdir / "results" / "dft_handoff_summary.json").exists())

            handoff = json.loads(
                (workdir / "results" / "dft_handoff_summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(handoff["status"], "not_ready")
            self.assertIsNone(handoff["recommended_next_skill"])

    def test_missing_poscar_fails_structure_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)

            result = self.controller.run({"poscar_path": "missing.POSCAR"}, {"workdir": str(workdir)})

            self.assertEqual(result["status"], "failure")
            self.assertEqual(result["next_action"]["recommendation"], "needs_human_review")
            self.assertTrue(any(error["code"] == "poscar_not_found" for error in result["errors"]))

    def test_qsub_submission_is_mockable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            poscar = workdir / "POSCAR"
            write_minimal_poscar(poscar)
            completed = subprocess.CompletedProcess(
                args=["qsub"],
                returncode=0,
                stdout="12345.server\n",
                stderr="",
            )

            with mock.patch.object(self.controller.subprocess, "run", return_value=completed) as run_mock:
                result = self.controller.run(
                    {"poscar_path": str(poscar), "execution_mode": "qsub"},
                    {"workdir": str(workdir)},
                )

            self.assertEqual(result["status"], "partial")
            self.assertFalse(result["data"]["dry_run"])
            self.assertEqual(result["data"]["qsub_job_id"], "12345.server")
            run_mock.assert_called_once()
            command = run_mock.call_args.args[0]
            self.assertEqual(command[0], "qsub")
            self.assertIn("run_mlip_dft_handoff.qsub.sh", command[1])
            self.assertEqual(command[4], "uma-s-1p2")
            self.assertEqual(command[5], "omat")
            self.assertEqual(command[6], "cuda")
            self.assertEqual(command[7], "geometry")
            self.assertEqual(command[8], "0.05")
            self.assertEqual(command[9], "300")
            self.assertTrue((workdir / "logs" / "qsub_submission.log").exists())

    def test_top_level_settings_are_not_controller_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            poscar = workdir / "POSCAR"
            write_minimal_poscar(poscar)

            result = self.controller.run(
                {
                    "poscar_path": "POSCAR",
                    "model": "not-used",
                    "task": "not-used",
                    "device": "not-used",
                    "relax_type": "surface",
                    "fmax": 99,
                    "steps": 1,
                },
                {"workdir": str(workdir)},
            )

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["data"]["settings"]["model"], "uma-s-1p2")
            self.assertEqual(result["data"]["settings"]["task"], "omat")
            self.assertEqual(result["data"]["settings"]["device"], "cuda")
            self.assertEqual(result["data"]["settings"]["relax_type"], "geometry")
            self.assertEqual(result["data"]["settings"]["fmax"], 0.05)
            self.assertEqual(result["data"]["settings"]["steps"], 300)

    def test_local_runner_inputs_use_nested_settings_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            poscar = workdir / "POSCAR"
            write_minimal_poscar(poscar)
            completed = subprocess.CompletedProcess(args=["runner"], returncode=0, stdout="", stderr="")

            with mock.patch.object(self.controller.subprocess, "run", return_value=completed):
                result = self.controller.run(
                    {
                        "poscar_path": str(poscar),
                        "execution_mode": "local",
                        "mlip_settings": {
                            "model": "uma-s-1p2",
                            "task": "omat",
                            "device": "cpu",
                        },
                        "relaxation_settings": {
                            "relax_type": "geometry",
                            "fmax": 0.07,
                            "steps": 12,
                        },
                    },
                    {"workdir": str(workdir)},
                )

            self.assertEqual(result["status"], "partial")
            singlepoint_input = json.loads(
                (workdir / "results" / "uma_singlepoint.input.json").read_text(encoding="utf-8")
            )
            relaxation_input = json.loads(
                (workdir / "results" / "uma_relaxation.input.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("model", singlepoint_input)
            self.assertEqual(singlepoint_input["mlip_settings"]["device"], "cpu")
            self.assertNotIn("relax_type", relaxation_input)
            self.assertEqual(relaxation_input["mlip_settings"]["task"], "omat")
            self.assertEqual(relaxation_input["relaxation_settings"]["fmax"], 0.07)


if __name__ == "__main__":
    unittest.main()
