#!/usr/bin/env python3
"""Standard-library tests for compute_no3rr_corrections.py."""

from __future__ import annotations

import copy
import importlib.util
import json
import math
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MODULE_PATH = HERE / "compute_no3rr_corrections.py"
SPEC = importlib.util.spec_from_file_location("compute_no3rr_corrections", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class NO3RRBookkeepingTests(unittest.TestCase):
    def load_example(self) -> dict:
        return json.loads((ROOT / "assets" / "example_no3rr_input.json").read_text(encoding="utf-8"))

    def standard_pH0(self) -> dict:
        payload = self.load_example()
        payload["conditions"]["pH"] = 0.0
        payload["conditions"]["potential_v"] = 0.0
        payload["conditions"]["reference_electrode"] = "RHE"
        return payload

    def test_calle_vallejo_shift_is_reproduced(self) -> None:
        result = MODULE.compute_bookkeeping(self.standard_pH0())
        row = result["nitrate_adsorption_diagnostics"][0]
        self.assertAlmostEqual(row["raw_electronic_adsorption_eV"], 1.0, places=12)
        self.assertAlmostEqual(row["corrected_gas_scale_adsorption_eV"], 0.021, places=12)
        self.assertAlmostEqual(row["electrochemical_adsorption_zero_potential_eV"], 0.413, places=12)
        self.assertAlmostEqual(row["raw_electronic_to_electrochemical_shift_zero_potential_eV"], -0.587, places=12)

    def test_closure_and_electron_count(self) -> None:
        result = MODULE.compute_bookkeeping(self.standard_pH0())
        self.assertEqual(result["summary"]["closure_failure_count"], 0)
        for row in result["pathway_descriptors"]:
            self.assertEqual(row["net_electrons_consumed_overall"], 8)
            self.assertAlmostEqual(row["closure_residual_eV"], 0.0, places=12)

    def test_hno3_correction_cancels_from_internal_steps(self) -> None:
        base = self.standard_pH0()
        changed = copy.deepcopy(base)
        changed["reference_policy"]["hno3_molecular_correction_eV"] = 0.50
        result_a = MODULE.compute_bookkeeping(base)
        result_b = MODULE.compute_bookkeeping(changed)
        steps_a = [row for row in result_a["step_table"] if row["pathway_id"] == "NHO_path"]
        steps_b = [row for row in result_b["step_table"] if row["pathway_id"] == "NHO_path"]
        self.assertNotAlmostEqual(steps_a[0]["delta_g_zero_potential_eV"], steps_b[0]["delta_g_zero_potential_eV"])
        for step_a, step_b in zip(steps_a[1:], steps_b[1:]):
            self.assertAlmostEqual(step_a["delta_g_zero_potential_eV"], step_b["delta_g_zero_potential_eV"], places=12)

    def test_rhe_pH_changes_feed_offset_not_internal_pcet_steps(self) -> None:
        p0 = self.standard_pH0()
        p14 = copy.deepcopy(p0)
        p14["conditions"]["pH"] = 14.0
        result0 = MODULE.compute_bookkeeping(p0)
        result14 = MODULE.compute_bookkeeping(p14)
        steps0 = [row for row in result0["step_table"] if row["pathway_id"] == "NHO_path"]
        steps14 = [row for row in result14["step_table"] if row["pathway_id"] == "NHO_path"]
        self.assertNotAlmostEqual(steps0[0]["delta_g_zero_potential_eV"], steps14[0]["delta_g_zero_potential_eV"])
        for step0, step14 in zip(steps0[1:], steps14[1:]):
            self.assertAlmostEqual(step0["delta_g_zero_potential_eV"], step14["delta_g_zero_potential_eV"], places=12)

    def test_she_pH_shifts_each_pcet_step(self) -> None:
        p0 = self.standard_pH0()
        p7 = copy.deepcopy(p0)
        p7["conditions"]["reference_electrode"] = "SHE"
        p7["conditions"]["pH"] = 7.0
        result0 = MODULE.compute_bookkeeping(p0)
        result7 = MODULE.compute_bookkeeping(p7)
        ph_shift = MODULE.KB_EV_PER_K * 298.15 * math.log(10.0) * 7.0
        steps0 = [row for row in result0["step_table"] if row["pathway_id"] == "NHO_path"]
        steps7 = [row for row in result7["step_table"] if row["pathway_id"] == "NHO_path"]
        self.assertAlmostEqual(steps0[0]["delta_g_zero_potential_eV"], steps7[0]["delta_g_zero_potential_eV"], places=12)
        for step0, step7 in zip(steps0[1:-1], steps7[1:-1]):
            expected = step0["delta_g_zero_potential_eV"] + step7["delta_net_electrons_consumed"] * ph_shift
            self.assertAlmostEqual(step7["delta_g_zero_potential_eV"], expected, places=12)

    def test_path_without_nho_is_supported(self) -> None:
        result = MODULE.compute_bookkeeping(self.standard_pH0())
        row = next(item for item in result["pathway_descriptors"] if item["pathway_id"] == "NHO_bypass_path")
        self.assertNotIn("NHO", row["state_order"])
        bypass = next(
            item for item in result["step_table"]
            if item["pathway_id"] == "NHO_bypass_path" and item["from_state"] == "NO" and item["to_state"] == "NH2O"
        )
        self.assertEqual(bypass["delta_net_electrons_consumed"], 2)

    def test_global_nox_correction_is_rejected(self) -> None:
        payload = self.standard_pH0()
        payload["reference_policy"]["global_nox_correction_eV"] = 1.12
        with self.assertRaises(MODULE.NO3RRInputError):
            MODULE.compute_bookkeeping(payload)

    def test_failed_evidence_is_excluded_from_ranking(self) -> None:
        payload = self.standard_pH0()
        payload["motifs"][0]["states"]["NO"]["evidence_acceptance_state"] = "failed"
        result = MODULE.compute_bookkeeping(payload)
        self.assertEqual(result["pathway_ranking"], [])
        self.assertTrue(all(not row["ranking_eligible"] for row in result["pathway_descriptors"]))
        self.assertGreater(result["summary"]["blocking_warning_count"], 0)

    def test_nh3_phase_must_be_declared(self) -> None:
        payload = self.standard_pH0()
        payload["references"]["NH3"].pop("phase")
        result = MODULE.compute_bookkeeping(payload)
        codes = {row["code"] for row in result["warnings"]}
        self.assertIn("NH3_PHASE_UNSPECIFIED", codes)
        self.assertGreater(result["summary"]["blocking_warning_count"], 0)

    def test_hno3_correction_is_not_inserted_automatically(self) -> None:
        payload = self.standard_pH0()
        payload["reference_policy"].pop("hno3_molecular_correction_eV")
        result = MODULE.compute_bookkeeping(payload)
        self.assertAlmostEqual(result["reference_policy"]["hno3_molecular_correction_eV"], 0.0, places=12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
