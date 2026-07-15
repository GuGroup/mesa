from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from helpers import base_spec

from vasp_submit.hpc_server.renderer import (
    apply_vasp_ase_environment,
    generated_job_dir,
    prepare_job,
    render_template_submit_script,
    resolve_submit_template,
    submit_job,
    write_vasp_inputs_with_vasp_ase,
)


class HpcRendererContractTests(unittest.TestCase):
    def test_apply_vasp_ase_environment_maps_direct_pp_path_to_env(self) -> None:
        old_pp_path = os.environ.get("VASP_PP_PATH")
        old_pp_version = os.environ.get("VASP_PP_VERSION")
        old_extra = os.environ.get("ASE_VASP_VDW")
        try:
            os.environ.pop("VASP_PP_PATH", None)
            os.environ.pop("VASP_PP_VERSION", None)
            os.environ.pop("ASE_VASP_VDW", None)

            apply_vasp_ase_environment(
                base_spec(),
                {
                    "vasp_pp_path": "/opt/vasp",
                    "vasp_pp_version": "64",
                    "vasp_ase_env": {"ASE_VASP_VDW": "/opt/vdw"},
                },
            )

            self.assertEqual(os.environ["VASP_PP_PATH"], "/opt/vasp")
            self.assertEqual(os.environ["VASP_PP_VERSION"], "64")
            self.assertEqual(os.environ["ASE_VASP_VDW"], "/opt/vdw")
        finally:
            for key, value in {
                "VASP_PP_PATH": old_pp_path,
                "VASP_PP_VERSION": old_pp_version,
                "ASE_VASP_VDW": old_extra,
            }.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_write_vasp_inputs_uses_vasp_ase_write_input_contract(self) -> None:
        atoms = object()
        calls = {"vasp_calls": []}
        old_modules = {name: sys.modules.get(name) for name in ("ase", "ase.io", "vasp")}
        fake_ase = types.ModuleType("ase")
        fake_ase_io = types.ModuleType("ase.io")
        fake_vasp = types.ModuleType("vasp")

        def fake_read(path, format=None):
            calls["read"] = {"path": Path(path), "format": format}
            return atoms

        class FakeVasp:
            def __init__(self, *args, **kwargs):
                calls["vasp_calls"].append({"args": args, "kwargs": kwargs})

            def write_input(self, input_atoms):
                calls["write_input_atoms"] = input_atoms
                current_call = calls["vasp_calls"][-1]
                names = ["INCAR", "POTCAR"]
                if "kpts" in current_call["kwargs"] or "kspacing" not in current_call["kwargs"]:
                    names.append("KPOINTS")
                for name in names:
                    (Path(current_call["args"][0]) / name).write_text(name, encoding="utf-8")

        fake_ase_io.read = fake_read
        fake_vasp.Vasp = FakeVasp
        sys.modules["ase"] = fake_ase
        sys.modules["ase.io"] = fake_ase_io
        sys.modules["vasp"] = fake_vasp
        try:
            with TemporaryDirectory() as tmp:
                directory = Path(tmp)
                (directory / "POSCAR").write_text("Si\n1.0\n", encoding="utf-8")
                spec = base_spec()
                spec["vasp"]["parameters"] = {
                    "encut": 450,
                    "setups": {"Ru": "_pv"},
                    "kspacing": 0.3,
                    "kgamma": False,
                    "directory": "ignored",
                }

                write_vasp_inputs_with_vasp_ase(spec, {}, directory)

                self.assertEqual(calls["read"], {"path": directory / "POSCAR", "format": "vasp"})
                self.assertEqual(calls["vasp_calls"][0]["args"], (str(directory),))
                kwargs = calls["vasp_calls"][0]["kwargs"]
                self.assertIs(kwargs["atoms"], atoms)
                self.assertEqual(kwargs["xc"], "PBE")
                self.assertEqual(kwargs["kpts"], (4, 4, 4))
                self.assertIs(kwargs["gamma"], True)
                self.assertEqual(kwargs["encut"], 450)
                self.assertEqual(kwargs["setups"], {"Ru": "_pv"})
                self.assertEqual(kwargs["kspacing"], 0.3)
                self.assertIs(kwargs["kgamma"], False)
                self.assertNotIn("directory", kwargs)
                self.assertIs(calls["write_input_atoms"], atoms)

            with TemporaryDirectory() as tmp:
                directory = Path(tmp)
                (directory / "POSCAR").write_text("Si\n1.0\n", encoding="utf-8")
                spec = base_spec()
                spec["vasp"].pop("kpts")
                spec["vasp"].pop("gamma")
                spec["vasp"]["parameters"] = {"kspacing": 0.3, "kgamma": False}

                write_vasp_inputs_with_vasp_ase(spec, {}, directory)

                kwargs = calls["vasp_calls"][1]["kwargs"]
                self.assertEqual(calls["vasp_calls"][1]["args"], (str(directory),))
                self.assertEqual(kwargs["kspacing"], 0.3)
                self.assertIs(kwargs["kgamma"], False)
                self.assertNotIn("kpts", kwargs)
                self.assertNotIn("gamma", kwargs)
        finally:
            for name, module in old_modules.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

    def test_render_template_submit_script_resolves_auto_to_template(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = root / "preset64std.sh"
            template.write_text(
                "#$ -N {{ job_name }}\n"
                "echo preset={{ preset }}\n"
                "echo queue_submit={{ submit }}\n",
                encoding="utf-8",
            )
            spec = base_spec()
            spec["vasp"]["gamma"] = False
            spec["queue"] = {"preset": "auto", "submit": True}
            config = {
                "submit_templates": {"preset64std": str(template)},
                "auto_preset": {"prefer": [64, 48]},
            }

            with patch(
                "vasp_submit.hpc_server.auto_preset.queue_status_output",
                return_value="n31\n",
            ):
                rendered = render_template_submit_script(spec, config)

            self.assertIn("#$ -N si_relax_001", rendered)
            self.assertIn("preset=preset64std", rendered)
            self.assertIn("queue_submit=True", rendered)
            self.assertEqual(spec["queue"]["preset"], "preset64std")

    def test_submit_template_must_be_configured_for_preset(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown queue.preset"):
            resolve_submit_template({"submit_templates": {}}, "preset64std")

    def test_relative_bundled_template_resolves_when_cwd_is_not_repo(self) -> None:
        original_cwd = Path.cwd()
        with TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                template = resolve_submit_template(
                    {"submit_templates": {"preset64std": "templates/sge/preset64std.sh"}},
                    "preset64std",
                )
            finally:
                os.chdir(original_cwd)

        self.assertEqual(template.name, "preset64std.sh")
        self.assertTrue(template.exists())

    def test_bundled_submit_templates_do_not_call_external_notifier(self) -> None:
        template_root = Path(__file__).resolve().parents[1] / "templates" / "sge"
        for template in template_root.glob("*.sh"):
            content = template.read_text(encoding="utf-8")
            self.assertNotIn("Finished Job:", content)
            self.assertIn(".vasp_submit_finished", content)
            self.assertIn(".vasp_submit_exit_code", content)

    def test_prepare_job_persists_auto_selected_preset(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = root / "preset64std.sh"
            template.write_text("#$ -N {{ job_name }}\necho {{ preset }}\n", encoding="utf-8")
            spec = base_spec()
            spec["project"] = None
            spec["vasp"]["gamma"] = False
            spec["queue"] = {"preset": "auto", "submit": False}
            config = {
                "trusted_roots": [str(root)],
                "default_project_root": str(root),
                "job_dir_pattern": "{name}_fixed",
                "submit_templates": {"preset64std": str(template)},
                "auto_preset": {"prefer": [64]},
            }

            def fake_write_inputs(_spec, _config, directory):
                for name in ("INCAR", "KPOINTS", "POTCAR"):
                    (directory / name).write_text(name, encoding="utf-8")

            with (
                patch("vasp_submit.hpc_server.auto_preset.queue_status_output", return_value="n31\n"),
                patch("vasp_submit.hpc_server.renderer.write_vasp_inputs_with_vasp_ase", fake_write_inputs),
            ):
                directory = prepare_job(spec, config)

            input_yml = (directory / "input.yml").read_text(encoding="utf-8")
            script = (directory / "submit_vasp.sh").read_text(encoding="utf-8")
            metadata = (directory / ".vasp_submit_metadata.json").read_text(encoding="utf-8")
            self.assertIn("preset: preset64std", input_yml)
            self.assertIn("preset64std", script)
            self.assertIn("si_relax_001_fixed", metadata)


    def test_prepare_job_reads_structure_path_relative_to_spec_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_dir = root / "test"
            spec_dir.mkdir()
            (spec_dir / "POSCAR").write_text("Si from file\n1.0\n", encoding="utf-8")
            template = root / "preset64std.sh"
            template.write_text("#$ -N {{ job_name }}\necho {{ preset }}\n", encoding="utf-8")
            spec = base_spec()
            spec["project"] = None
            spec["job_dir"] = "path_case"
            spec["structure"] = {"format": "poscar", "path": "POSCAR"}
            spec["queue"] = {"preset": "preset64std", "submit": False}
            config = {
                "trusted_roots": [str(root)],
                "default_project_root": str(root),
                "submit_templates": {"preset64std": str(template)},
            }

            def fake_write_inputs(_spec, _config, directory):
                for name in ("INCAR", "KPOINTS", "POTCAR"):
                    (directory / name).write_text(name, encoding="utf-8")

            with patch("vasp_submit.hpc_server.renderer.write_vasp_inputs_with_vasp_ase", fake_write_inputs):
                directory = prepare_job(spec, config, spec_base_dir=spec_dir)

            self.assertEqual((directory / "POSCAR").read_text(encoding="utf-8"), "Si from file\n1.0\n")
            self.assertIn("path: POSCAR", (directory / "input.yml").read_text(encoding="utf-8"))

    def test_prepare_job_does_not_index_missing_structure(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = root / "preset64std.sh"
            template.write_text("#$ -N {{ job_name }}\n", encoding="utf-8")
            spec = base_spec()
            spec["project"] = None
            spec["job_dir"] = "missing_structure"
            spec["structure"] = {"format": "poscar", "path": "missing.POSCAR"}
            spec["queue"] = {"preset": "preset64std", "submit": False}
            config = {
                "trusted_roots": [str(root)],
                "default_project_root": str(root),
                "submit_templates": {"preset64std": str(template)},
            }

            with self.assertRaises(FileNotFoundError):
                prepare_job(spec, config, spec_base_dir=root)

            self.assertFalse((root / "job_index/missing_structure.json").exists())
            self.assertFalse((root / "missing_structure/.vasp_submit_metadata.json").exists())

    def test_submit_job_requires_scheduler_id(self) -> None:
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / ".vasp_submit_metadata.json").write_text("{}", encoding="utf-8")
            completed = types.SimpleNamespace(returncode=0, stdout="submitted\n", stderr="")

            with patch("vasp_submit.hpc_server.renderer.subprocess.run", return_value=completed):
                result = submit_job(directory)

            self.assertIs(result["ok"], False)
            self.assertIsNone(result["scheduler_id"])

    def test_generated_job_dir_defaults_to_hyphenless_uuid(self) -> None:
        job_dir = generated_job_dir("si_relax_001", {})
        self.assertEqual(len(job_dir), 10)
        self.assertNotIn("-", job_dir)
        self.assertRegex(job_dir, r"^[0-9a-f]{10}$")

    def test_generated_job_dir_respects_length_and_pattern(self) -> None:
        job_dir = generated_job_dir(
            "si_relax_001", {"job_uid_length": 8, "job_dir_pattern": "{name}_{uuid}"}
        )
        self.assertTrue(job_dir.startswith("si_relax_001_"))
        suffix = job_dir.rsplit("_", 1)[-1]
        self.assertEqual(len(suffix), 8)
        self.assertRegex(suffix, r"^[0-9a-f]{8}$")


if __name__ == "__main__":
    unittest.main()
