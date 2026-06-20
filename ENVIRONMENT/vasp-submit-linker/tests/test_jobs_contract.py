from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import helpers  # noqa: F401  (inserts src/ on sys.path)

from vasp_submit.hpc_server.jobs import index_roots, list_jobs, show_job


def write_index_entry(root: Path, job_uid: str, **fields: object) -> None:
    index_dir = root / "job_index"
    index_dir.mkdir(parents=True, exist_ok=True)
    payload = {"job_uid": job_uid, "remote_dir": str(root / "jobs" / job_uid), **fields}
    (index_dir / f"{job_uid}.json").write_text(json.dumps(payload), encoding="utf-8")


class JobsContractTests(unittest.TestCase):
    def test_index_roots_dedupes_trusted_and_default_root(self) -> None:
        with TemporaryDirectory() as tmp:
            root = str(Path(tmp))
            roots = index_roots({"trusted_roots": [root], "default_project_root": root})
            self.assertEqual(len(roots), 1)
            self.assertEqual(roots[0].name, "job_index")

    def test_list_jobs_orders_recent_first_and_uses_compact_summary(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {"trusted_roots": [str(root)], "default_project_root": str(root)}
            write_index_entry(
                root, "old_job", job_name="old", state="submitted",
                created_at="2026-06-01T00:00:00+00:00", submitted_at="2026-06-01T00:01:00+00:00",
                scheduler_id="111", preset="preset64std", index_path="/x",
            )
            write_index_entry(
                root, "new_job", job_name="new", state="submitted",
                created_at="2026-06-10T00:00:00+00:00", submitted_at="2026-06-10T00:01:00+00:00",
                scheduler_id="222", preset="preset48gam", index_path="/y",
            )

            result = list_jobs(config, limit=10)

            self.assertTrue(result["ok"])
            self.assertEqual(result["count"], 2)
            self.assertEqual([job["job_uid"] for job in result["jobs"]], ["new_job", "old_job"])
            summary = result["jobs"][0]
            self.assertEqual(summary["job_name"], "new")
            self.assertEqual(summary["scheduler_id"], "222")
            self.assertEqual(summary["state"], "submitted")
            self.assertEqual(summary["task"], None)
            # verbose/bulky fields are not leaked into the default summary
            self.assertNotIn("preset", summary)
            self.assertNotIn("remote_dir", summary)
            self.assertNotIn("submitted_at", summary)
            self.assertNotIn("index_path", summary)
            self.assertNotIn("_sort_key", summary)

    def test_list_jobs_verbose_includes_detail_fields(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {"trusted_roots": [str(root)], "default_project_root": str(root)}
            write_index_entry(
                root, "run_job", job_name="run", state="submitted", task="slab",
                created_at="2026-06-10T00:00:00+00:00", submitted_at="2026-06-10T00:01:00+00:00",
                scheduler_id="222", preset="preset48gam", project="screening",
            )

            result = list_jobs(config, limit=10, verbose=True)

            summary = result["jobs"][0]
            self.assertEqual(summary["preset"], "preset48gam")
            self.assertEqual(summary["project"], "screening")
            self.assertEqual(summary["submitted_at"], "2026-06-10T00:01:00+00:00")
            self.assertIn("remote_dir", summary)

    def test_list_jobs_respects_limit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {"trusted_roots": [str(root)]}
            for i in range(5):
                write_index_entry(root, f"job_{i}", submitted_at=f"2026-06-0{i + 1}T00:00:00+00:00")
            result = list_jobs(config, limit=2)
            self.assertEqual(result["count"], 2)
            self.assertEqual(result["total"], 5)

    def test_show_job_prepared_but_not_submitted(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {"trusted_roots": [str(root)]}
            write_index_entry(root, "prep_job", job_name="prep", state="prepared", created_at="2026-06-09T00:00:00+00:00")

            result = show_job("prep_job", config)

            self.assertTrue(result["ok"])
            self.assertEqual(result["job_uid"], "prep_job")
            self.assertEqual(result["metadata"]["job_name"], "prep")
            self.assertEqual(result["status"]["state"], "prepared")
            self.assertFalse(result["status"]["finished"])

    def test_show_job_submitted_calls_status(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {"trusted_roots": [str(root)]}
            write_index_entry(root, "run_job", state="submitted", scheduler_id="424242")

            fake_status = {"ok": True, "state": "running", "running": True, "finished": False}
            with patch("vasp_submit.hpc_server.jobs.status_job", return_value=fake_status) as mocked:
                result = show_job("run_job", config)

            mocked.assert_called_once()
            self.assertEqual(mocked.call_args.args[0], "424242")
            self.assertEqual(result["status"]["state"], "running")

    def test_show_job_unknown_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            config = {"trusted_roots": [str(Path(tmp))]}
            with self.assertRaisesRegex(ValueError, "Unknown job_uid"):
                show_job("does_not_exist", config)


if __name__ == "__main__":
    unittest.main()
