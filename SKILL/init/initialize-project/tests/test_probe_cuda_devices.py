from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "probe_cuda_devices.py"
SPEC = importlib.util.spec_from_file_location("probe_cuda_devices", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


SAMPLE = """0, GPU-aaaa, Example A, 24576
1, GPU-bbbb, Example B, 49152
"""


class ProbeCudaDevicesTests(unittest.TestCase):
    def test_inventory_contains_stable_fields(self) -> None:
        inventory = MODULE.build_inventory(SAMPLE, None)
        self.assertEqual(MODULE.QUERY_FIELDS, "index,uuid,name,memory.total")
        self.assertEqual(inventory["status"], "available")
        self.assertEqual(len(inventory["devices"]), 2)
        self.assertEqual(inventory["devices"][1]["memory_total_mib"], 49152)
        self.assertEqual(
            set(inventory["devices"][0]),
            {"index", "uuid", "name", "memory_total_mib", "visibility"},
        )
        self.assertEqual(inventory["devices"][0]["visibility"]["logical_index"], 0)

    def test_index_visibility_is_mapped_to_logical_order(self) -> None:
        inventory = MODULE.build_inventory(SAMPLE, "1,0")
        devices = {item["index"]: item for item in inventory["devices"]}
        self.assertEqual(devices[1]["visibility"]["logical_index"], 0)
        self.assertEqual(devices[0]["visibility"]["logical_index"], 1)

    def test_uuid_visibility_is_supported(self) -> None:
        inventory = MODULE.build_inventory(SAMPLE, "GPU-bbbb")
        self.assertFalse(inventory["devices"][0]["visibility"]["eligible"])
        self.assertTrue(inventory["devices"][1]["visibility"]["eligible"])

    def test_unresolved_token_is_reported(self) -> None:
        inventory = MODULE.build_inventory(SAMPLE, "9")
        self.assertEqual(inventory["unresolved_visibility_tokens"], ["9"])
        self.assertEqual(inventory["status"], "unavailable")
        self.assertFalse(any(item["visibility"]["eligible"] for item in inventory["devices"]))

    def test_unavailable_inventory_preserves_diagnostic(self) -> None:
        inventory = MODULE.unavailable_inventory("0", "nvidia-smi is unavailable")
        self.assertEqual(inventory["status"], "unavailable")
        self.assertEqual(inventory["devices"], [])
        self.assertEqual(inventory["diagnostics"], ["nvidia-smi is unavailable"])


if __name__ == "__main__":
    unittest.main()
