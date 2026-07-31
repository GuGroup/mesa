import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "vasp_local_node_runner.py"
)
SPEC = importlib.util.spec_from_file_location("vasp_local_node_runner", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def write_prepared_job(path: Path, *, kspacing: bool = False) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "POSCAR").write_text("test\n1\n1 0 0\n0 1 0\n0 0 1\nH\n1\nDirect\n0 0 0\n", encoding="utf-8")
    incar = "ENCUT = 400\n"
    if kspacing:
        incar += "KSPACING = 0.3\n"
    (path / "INCAR").write_text(incar, encoding="utf-8")
    (path / "POTCAR").write_text("fake\n", encoding="utf-8")
    if not kspacing:
        (path / "KPOINTS").write_text("Gamma\n0\nGamma\n1 1 1\n0 0 0\n", encoding="utf-8")


class VaspLocalNodeRunnerTests(unittest.TestCase):
    def test_kpoints_not_required_when_incar_has_kspacing(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            write_prepared_job(job, kspacing=True)
            status = MODULE.input_status(job)
        self.assertTrue(status["ok"])
        self.assertNotIn("KPOINTS", status["required"])

    def test_dry_run_writes_state_and_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            write_prepared_job(job)
            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "run",
                    str(job),
                    "--dry-run",
                    "--min-cores",
                    "1",
                    "--cores",
                    "2",
                    "--launcher",
                    "none",
                    "--vasp-command",
                    "echo {cores} {executable}",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(completed.stdout)
            state = json.loads((job / ".mesa_vasp_local_state.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["state"], "dry_run")
        self.assertEqual(payload["command"], ["echo", "2", "vasp_std"])
        self.assertEqual(state["state"], "dry_run")

    def test_nsLots_48_defaults_to_40_vasp_ranks(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            write_prepared_job(job)
            env = {**os.environ, "NSLOTS": "48"}
            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "run",
                    str(job),
                    "--dry-run",
                    "--min-cores",
                    "40",
                    "--launcher",
                    "none",
                    "--vasp-command",
                    "echo {cores}",
                ],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            payload = json.loads(completed.stdout)

        self.assertEqual(payload["command"], ["echo", "40"])
        self.assertTrue(payload["core_policy"]["capped"])
        self.assertEqual(payload["core_policy"]["raw_cores"], 48)
        self.assertEqual(payload["core_policy"]["resolved_vasp_cores"], 40)

    def test_run_with_fake_command_writes_finished_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            write_prepared_job(job)
            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "run",
                    str(job),
                    "--min-cores",
                    "1",
                    "--cores",
                    "1",
                    "--launcher",
                    "none",
                    "--vasp-command",
                    "python3 -c 'from pathlib import Path; Path(\"CONTCAR\").write_text(\"ok\")'",
                    "--no-serial-allocation-lock",
                ],
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "MESA_ALLOW_LOCAL_VASP": "1"},
            )
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["state"], "finished")
            self.assertEqual((job / ".mesa_vasp_local_exit_code").read_text(encoding="utf-8").strip(), "0")
            self.assertEqual((job / ".vasp_submit_exit_code").read_text(encoding="utf-8").strip(), "0")
            self.assertTrue((job / "CONTCAR").exists())

    def test_run_without_allocation_is_blocked(self):
        # Regression test for the login-node execution guard: without
        # NSLOTS/SLURM_JOB_ID/a machinefile and without the explicit
        # MESA_ALLOW_LOCAL_VASP=1 opt-out, `run` must refuse to launch VASP
        # even if no --require-allocation-style flag is passed.
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            write_prepared_job(job)
            env = {
                k: v
                for k, v in os.environ.items()
                if k not in ("NSLOTS", "SLURM_JOB_ID", "PE_HOSTFILE", "MESA_ALLOW_LOCAL_VASP")
            }
            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "run",
                    str(job),
                    "--min-cores",
                    "1",
                    "--cores",
                    "1",
                    "--launcher",
                    "none",
                    "--vasp-command",
                    "echo should_not_run",
                    "--no-serial-allocation-lock",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            payload = json.loads(completed.stdout)

            self.assertEqual(completed.returncode, 2)
            self.assertEqual(payload["state"], "blocked")
            self.assertIn("REFUSING TO RUN", payload["error"])
            self.assertFalse((job / "CONTCAR").exists())

    def test_watch_without_allocation_is_blocked(self):
        # Same guard, exercised through `watch` (the path the SGE wrapper and
        # the mark-ready flow actually use) rather than a bare `run` call.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "job"
            write_prepared_job(job)
            subprocess.run(["python3", str(SCRIPT), "mark-ready", str(job)], check=True, capture_output=True, text=True)
            env = {
                k: v
                for k, v in os.environ.items()
                if k not in ("NSLOTS", "SLURM_JOB_ID", "PE_HOSTFILE", "MESA_ALLOW_LOCAL_VASP")
            }
            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "watch",
                    str(root),
                    "--once",
                    "--min-cores",
                    "1",
                    "--cores",
                    "1",
                    "--launcher",
                    "none",
                    "--vasp-command",
                    "python3 -c 'from pathlib import Path; Path(\"ran.txt\").write_text(\"yes\")'",
                    "--no-serial-allocation-lock",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            payload = json.loads(completed.stdout)

            self.assertEqual(completed.returncode, 1)
            self.assertEqual(payload["failures"], 1)
            self.assertFalse((job / "ran.txt").exists())

    def test_watch_once_runs_ready_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "job"
            write_prepared_job(job)
            subprocess.run(["python3", str(SCRIPT), "mark-ready", str(job)], check=True, capture_output=True, text=True)
            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "watch",
                    str(root),
                    "--once",
                    "--min-cores",
                    "1",
                    "--cores",
                    "1",
                    "--launcher",
                    "none",
                    "--vasp-command",
                    "python3 -c 'from pathlib import Path; Path(\"ran.txt\").write_text(\"yes\")'",
                    "--no-serial-allocation-lock",
                ],
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "MESA_ALLOW_LOCAL_VASP": "1"},
            )
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["processed_count"], 1)
            self.assertTrue((job / "ran.txt").exists())

    def test_active_serial_lock_blocks_second_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "job"
            lock_dir = root / "locks"
            lock_dir.mkdir()
            write_prepared_job(job)
            lock_path = lock_dir / f"{MODULE.socket.gethostname()}.serial.lock"
            lock_path.write_text(
                json.dumps(
                    {
                        "runner": "vasp_local_node_runner",
                        "hostname": MODULE.socket.gethostname(),
                        "pid": os.getpid(),
                    }
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "run",
                    str(job),
                    "--min-cores",
                    "1",
                    "--cores",
                    "1",
                    "--serial-lock-dir",
                    str(lock_dir),
                    "--launcher",
                    "none",
                    "--vasp-command",
                    "echo blocked",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "MESA_ALLOW_LOCAL_VASP": "1"},
            )
            payload = json.loads(completed.stdout)

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["state"], "blocked")
        self.assertIn("serial", payload["error"])


if __name__ == "__main__":
    unittest.main()
