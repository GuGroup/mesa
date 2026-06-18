from __future__ import annotations

import copy
import unittest

from helpers import base_spec, hpc_config, spec_with

from vasp_submit.common.schema import JOB_SPEC_SCHEMA
from vasp_submit.common.spec import merge_common_spec, normalize_spec


class NormalizeSpecContractTests(unittest.TestCase):
    def test_hpc_normalization_applies_server_defaults(self) -> None:
        normalized = normalize_spec(base_spec(), hpc_config())

        self.assertEqual(normalized["schema_version"], 1)
        self.assertEqual(normalized["queue"]["scheduler"], "sge")
        self.assertEqual(normalized["queue"]["preset"], "auto")
        self.assertEqual(normalized["project"]["root"], "/tmp/vasp-submit-test")

    def test_local_normalization_does_not_inject_hpc_only_scheduler(self) -> None:
        normalized = normalize_spec(base_spec(), {}, require_root=False)

        self.assertNotIn("scheduler", normalized["queue"])
        self.assertEqual(normalized["queue"]["preset"], "auto")

    def test_common_spec_merge_is_recursive_and_spec_wins(self) -> None:
        common = {
            "project": "screening",
            "vasp": {
                "xc": "PBE",
                "parameters": {
                    "encut": 520,
                    "ediff": 1.0e-5,
                },
            },
            "queue": {"preset": "auto", "submit": True},
        }
        spec = {
            "job_name": "si_relax_001",
            "structure": {"format": "poscar", "content": "Si\n1.0\n"},
            "vasp": {"parameters": {"encut": 600}},
        }

        merged = merge_common_spec(common, spec)

        self.assertEqual(merged["vasp"]["xc"], "PBE")
        self.assertEqual(merged["vasp"]["parameters"]["encut"], 600)
        self.assertEqual(merged["vasp"]["parameters"]["ediff"], 1.0e-5)

    def test_schema_exposes_only_current_user_fields(self) -> None:
        top_level_fields = JOB_SPEC_SCHEMA["properties"]
        project_fields = top_level_fields["project"]["oneOf"][2]["properties"]
        queue_fields = top_level_fields["queue"]["properties"]

        self.assertNotIn("name", top_level_fields)
        self.assertNotIn("potcar", top_level_fields)
        self.assertNotIn("root", project_fields)
        self.assertNotIn("workdir", project_fields)
        structure_fields = top_level_fields["structure"]["properties"]

        self.assertEqual(set(queue_fields), {"preset", "submit"})
        self.assertEqual(set(structure_fields), {"format", "content", "path"})
        self.assertEqual(JOB_SPEC_SCHEMA["required"], ["job_name", "structure"])

    def test_rejects_fields_documentation_says_not_to_send(self) -> None:
        cases = [
            ({"name": "old_alias"}, "unsupported job spec field"),
            ({"potcar": {"functional": "PBE"}}, "top-level potcar"),
            ({"queue": {"preset": "auto", "pe": "mpi_48"}}, "queue.pe"),
            ({"queue": {"preset": "auto", "slots": 48}}, "queue.slots"),
            ({"queue": {"preset": "auto", "vasp_command": "vasp_std"}}, "queue.vasp_command"),
            ({"project": {"workdir": "old_alias"}}, "unsupported project field"),
            ({"project": {"root": "/tmp/escape"}}, "project.root"),
            ({"project": {"root": ""}}, "project.root"),
        ]
        for update, expected in cases:
            with self.subTest(update=update):
                with self.assertRaisesRegex(ValueError, expected):
                    normalize_spec(spec_with(**update), hpc_config())

    def test_rejects_schema_type_and_value_errors(self) -> None:
        cases = [
            ({"schema_version": 2}, "schema_version must be 1"),
            ({"job_name": 123}, "job_name must be a string"),
            ({"job_name": "bad name"}, "job_name must contain only"),
            ({"job_dir": "../bad"}, "job_dir must not be '.' or '..'"),
            ({"overwrite": "yes"}, "overwrite must be a boolean"),
            ({"queue": {"preset": "bad"}}, "queue.preset must be one of"),
            ({"queue": {"submit": "false"}}, "queue.submit must be a boolean"),
            ({"structure": {"format": "cif", "content": "data"}}, "structure.format must be poscar"),
            ({"structure": {"format": "poscar"}}, "structure must set exactly one of content or path"),
            ({"structure": {"format": "poscar", "content": "Si", "path": "POSCAR"}}, "structure must set exactly one of content or path"),
            ({"structure": {"format": "poscar", "content": 123}}, "structure.content must be a string"),
            ({"structure": {"format": "poscar", "path": 123}}, "structure.path must be a string"),
            ({"structure": {"format": "poscar", "path": "../POSCAR"}}, "structure.path must not be '.' or '..'"),
            ({"vasp": {"kpts": [1, 2]}}, "vasp.kpts must be an integer array of length 3"),
            ({"vasp": {"gamma": "true"}}, "vasp.gamma must be a boolean"),
            ({"vasp": {"parameters": []}}, "vasp.parameters must be a mapping"),
            ({"collection": {"fetch_on_finish": ["OUTCAR"]}}, "unsupported job spec field"),
        ]
        for update, expected in cases:
            payload = copy.deepcopy(base_spec())
            payload.update(update)
            with self.subTest(update=update):
                with self.assertRaisesRegex(ValueError, expected):
                    normalize_spec(payload, hpc_config())

    def test_task_is_optional_and_enum_validated(self) -> None:
        without_task = copy.deepcopy(base_spec())
        without_task.pop("task", None)
        normalize_spec(without_task, hpc_config())  # no raise — task is optional

        bad_task = copy.deepcopy(base_spec())
        bad_task["task"] = "phonon"
        with self.assertRaisesRegex(ValueError, "task must be one of"):
            normalize_spec(bad_task, hpc_config())

    def test_vasp_parameters_pass_through_unchanged(self) -> None:
        payload = copy.deepcopy(base_spec())
        payload["vasp"] = {"parameters": {"encut": 400, "ismear": 1, "ispin": 2, "ibrion": 2}}
        params = normalize_spec(payload, hpc_config())["vasp"]["parameters"]
        # no server defaults injected, no merge, no ispin->magmom enforcement
        self.assertEqual(params, {"encut": 400, "ismear": 1, "ispin": 2, "ibrion": 2})


if __name__ == "__main__":
    unittest.main()
