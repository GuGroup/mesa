from __future__ import annotations

import types
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import base_spec

from vasp_submit.hpc_server.auto_preset import (
    auto_select_preset,
    parse_available_qq_nodes,
    queue_status_output,
)


class AutoPresetContractTests(unittest.TestCase):
    def test_parse_available_qq_nodes_uses_configured_core_ranges(self) -> None:
        available = parse_available_qq_nodes(
            "header\nn01\nn05\nn31\nbusy n32\nn40\n",
            {
                "auto_preset": {
                    "node_core_ranges": {
                        48: [[1, 30]],
                        64: [[31, 40]],
                    }
                }
            },
        )

        self.assertEqual(available[48], ["n01", "n05"])
        self.assertEqual(available[64], ["n31", "n40"])

    def test_queue_status_command_expands_leading_tilde(self) -> None:
        captured: dict[str, list[str]] = {}

        def fake_run(args, **kwargs):  # noqa: ANN001, ANN003
            captured["args"] = args
            return types.SimpleNamespace(returncode=0, stdout="n31\n", stderr="")

        with patch("vasp_submit.hpc_server.auto_preset.subprocess.run", side_effect=fake_run):
            queue_status_output({"queue_status_command": "~/runners/qq-wrapper"})
            self.assertEqual(captured["args"], [str(Path("~/runners/qq-wrapper").expanduser())])

            queue_status_output({"queue_status_command": "qq"})
            self.assertEqual(captured["args"], ["qq"])

    def test_auto_select_preset_uses_gam_only_for_explicit_one_point_gamma_mesh(self) -> None:
        config = {"auto_preset": {"prefer": [64, 48]}}

        with patch("vasp_submit.hpc_server.auto_preset.queue_status_output", return_value="n31\n"):
            multi_point = base_spec()
            multi_point["vasp"]["gamma"] = True
            multi_point["vasp"]["kpts"] = [4, 4, 4]
            self.assertEqual(auto_select_preset(multi_point, config), "preset64std")

            one_point = base_spec()
            one_point["vasp"]["gamma"] = True
            one_point["vasp"]["kpts"] = [1, 1, 1]
            self.assertEqual(auto_select_preset(one_point, config), "preset64gam")

    def test_auto_select_preset_uses_remaining_slots_when_preferred_queue_is_full(self) -> None:
        config = {
            "auto_preset": {
                "prefer": [64, 48],
                "node_core_ranges": {
                    48: [[1, 30]],
                    64: [[31, 40]],
                },
            }
        }
        spec = base_spec()
        spec["vasp"]["gamma"] = False

        with patch(
            "vasp_submit.hpc_server.auto_preset.queue_status_output",
            return_value="n31 remaining=0\nn01 remaining=12\n",
        ):
            self.assertEqual(auto_select_preset(spec, config), "preset48std")

    def test_auto_select_preset_defaults_to_48_core_when_all_nodes_are_full(self) -> None:
        config = {
            "auto_preset": {
                "prefer": [64, 48],
                "node_core_ranges": {
                    48: [[1, 30]],
                    64: [[31, 40]],
                },
            }
        }
        spec = base_spec()
        spec["vasp"]["gamma"] = False

        with patch(
            "vasp_submit.hpc_server.auto_preset.queue_status_output",
            return_value="n31 remaining=0\nn01 remaining=0\n",
        ):
            self.assertEqual(auto_select_preset(spec, config), "preset48std")


if __name__ == "__main__":
    unittest.main()
