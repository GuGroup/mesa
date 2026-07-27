import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "decide_relaxation_revision.py"
)
SPEC = importlib.util.spec_from_file_location("decide_relaxation_revision", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def eligible_summary():
    return {
        "verdict": "fail",
        "convergence": {
            "converged": False,
            "nsw_reached": True,
            "warn_reasons": [],
        },
        "visual_validation": {
            "status": "completed",
            "review": {
                "verdict": "pass",
                "views_reviewed": ["top", "side_a", "side_b"],
            },
        },
        "anomalies": {
            "connectivity_changed": False,
            "dissociation_suspected": False,
            "new_bond_suspected": False,
            "desorption_suspected": False,
        },
    }


def base_config():
    return {
        "workdir": "/old/run",
        "input_poscar": "/old/run/POSCAR",
        "outputs": {"trajectory": "relax.traj"},
        "uma": {"model": "uma-s-1p1", "task_name": "omat", "device": "cuda"},
        "relaxation": {
            "fmax": 0.05,
            "steps": 300,
            "optimizer": "FIRE",
            "constraints": [{"type": "poscar_selective_dynamics"}],
        },
        "execution": {"mode": "qsub"},
    }


class RelaxationRevisionDecisionTests(unittest.TestCase):
    def test_clean_max_step_failure_is_eligible(self):
        eligible, reasons = MODULE.decide(eligible_summary(), base_config())
        self.assertTrue(eligible)
        self.assertEqual(reasons, [])

    def test_warning_anomaly_or_prior_retry_is_blocked(self):
        cases = []

        warning = eligible_summary()
        warning["convergence"]["warn_reasons"] = ["energy is not monotonic"]
        cases.append((warning, base_config()))

        anomaly = eligible_summary()
        anomaly["anomalies"]["desorption_suspected"] = True
        cases.append((anomaly, base_config()))

        retried = base_config()
        retried["diagnosis_revision"] = {"continuations_used": 1}
        cases.append((eligible_summary(), retried))

        for summary, config in cases:
            with self.subTest(summary=summary, config=config):
                eligible, reasons = MODULE.decide(summary, config)
                self.assertFalse(eligible)
                self.assertTrue(reasons)

    def test_malformed_summary_fails_closed(self):
        eligible, reasons = MODULE.decide(
            {"verdict": "fail", "convergence": None, "visual_validation": None},
            base_config(),
        )
        self.assertFalse(eligible)
        self.assertTrue(reasons)

    def test_retry_doubles_only_steps_among_scientific_settings(self):
        config = base_config()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            restart = root / "POSCAR"
            restart.touch()
            retry = MODULE.make_retry_config(
                config,
                restart_poscar=restart,
                retry_dir=root / "retry",
                summary_path=root / "analysis_summary.json",
                config_path=root / "resolved_uma_config.json",
            )

        self.assertEqual(retry["relaxation"]["steps"], 600)
        self.assertEqual(retry["relaxation"]["fmax"], 0.05)
        self.assertEqual(retry["relaxation"]["optimizer"], "FIRE")
        self.assertEqual(
            retry["relaxation"]["constraints"],
            config["relaxation"]["constraints"],
        )
        self.assertEqual(retry["uma"], config["uma"])
        self.assertEqual(retry["outputs"], config["outputs"])
        self.assertEqual(retry["diagnosis_revision"]["continuations_used"], 1)
        self.assertEqual(config["relaxation"]["steps"], 300)

    def test_cli_prepares_retry_without_running_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = root / "analysis_summary.json"
            config = root / "resolved_uma_config.json"
            restart = root / "POSCAR"
            retry_dir = root / "retry"
            summary.write_text(json.dumps(eligible_summary()), encoding="utf-8")
            config.write_text(json.dumps(base_config()), encoding="utf-8")
            restart.touch()

            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--summary",
                    str(summary),
                    "--config",
                    str(config),
                    "--restart-poscar",
                    str(restart),
                    "--retry-dir",
                    str(retry_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            decision = json.loads(completed.stdout)
            prepared = json.loads(
                (retry_dir / "resolved_uma_config.json").read_text(encoding="utf-8")
            )

        self.assertTrue(decision["eligible"])
        self.assertFalse(decision["executed"])
        self.assertEqual(prepared["relaxation"]["steps"], 600)


if __name__ == "__main__":
    unittest.main()
