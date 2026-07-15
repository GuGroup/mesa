from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from vasp_submit.hpc_server import cli


class CliContractTest(unittest.TestCase):
    def test_submit_rejects_disabled_queue_without_preparing_or_submitting(self) -> None:
        spec = {"queue": {"submit": False}}
        with (
            patch.object(cli, "load_yaml", return_value={}),
            patch.object(cli, "read_spec_arg", return_value=(spec, "queue:\n  submit: false\n", Path.cwd())),
            patch.object(cli, "load_and_resolve_spec", return_value=spec),
            patch.object(cli, "prepare_job") as prepare,
            patch.object(cli, "submit_job") as submit,
        ):
            result = cli.main(["submit", "input.yml"])

        self.assertEqual(result, 2)
        prepare.assert_not_called()
        submit.assert_not_called()

    def test_submit_returns_nonzero_when_scheduler_rejects_job(self) -> None:
        spec = {"queue": {"submit": True}}
        directory = Path("/tmp/prepared-job")
        with (
            patch.object(cli, "load_yaml", return_value={}),
            patch.object(cli, "read_spec_arg", return_value=(spec, "queue:\n  submit: true\n", Path.cwd())),
            patch.object(cli, "load_and_resolve_spec", return_value=spec),
            patch.object(cli, "prepare_job", return_value=directory),
            patch.object(cli, "submit_job", return_value={"ok": False, "returncode": 1, "stderr": "denied"}),
        ):
            result = cli.main(["submit", "input.yml"])

        self.assertEqual(result, 2)


if __name__ == "__main__":
    unittest.main()
