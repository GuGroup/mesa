#!/usr/bin/env python3
"""Standard-library tests for compute_oer_corrections.py."""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MODULE_PATH = HERE / "compute_oer_corrections.py"
SPEC = importlib.util.spec_from_file_location("compute_oer_corrections", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class OERBookkeepingTests(unittest.TestCase):
    def load_example(self) -> dict:
        return json.loads((ROOT / "assets" / "example_oer_input.json").read_text(encoding="utf-8"))

    def test_cycle_closure_and_ranking(self) -> None:
        result = MODULE.compute_bookkeeping(self.load_example())
        self.assertEqual(result["summary"]["closure_failure_count"], 0)
        self.assertEqual(result["activity_ranking"][0]["motif"], "balanced_site")
        balanced = next(row for row in result["descriptors"] if row["motif"] == "balanced_site")
        self.assertAlmostEqual(sum(balanced["step_free_energies_zero_potential_eV"]), 4.92, places=12)
        self.assertAlmostEqual(balanced["thermodynamic_limiting_potential_V"], 1.25, places=12)
        self.assertAlmostEqual(balanced["thermodynamic_overpotential_V"], 0.02, places=12)

    def test_requested_rhe_potential_shifts_each_step(self) -> None:
        payload = self.load_example()
        payload["conditions"]["potential_v"] = 0.30
        result = MODULE.compute_bookkeeping(payload)
        row = result["descriptors"][0]
        for zero, requested in zip(
            row["step_free_energies_zero_potential_eV"],
            row["step_free_energies_requested_potential_eV"],
        ):
            self.assertAlmostEqual(requested, zero - 0.30, places=12)

    def test_she_pH_shift(self) -> None:
        payload = self.load_example()
        payload["conditions"]["reference_electrode"] = "SHE"
        payload["conditions"]["pH"] = 7.0
        result = MODULE.compute_bookkeeping(payload)
        ph_shift = MODULE.KB_EV_PER_K * 298.15 * math.log(10.0) * 7.0
        self.assertAlmostEqual(
            result["reference_policy"]["equilibrium_potential_selected_scale_V"],
            1.23 - ph_shift,
            places=12,
        )

    def test_double_counting_is_rejected(self) -> None:
        payload = self.load_example()
        payload["references"]["H2"] = {
            "free_energy_ev": 0.0,
            "electronic_energy_ev": 0.0,
            "corrections_ev": {"zpe": 0.1}
        }
        with self.assertRaises(MODULE.OERInputError):
            MODULE.compute_bookkeeping(payload)

    def test_mesa_records_schema(self) -> None:
        payload = self.load_example()
        records = []
        for species, record in payload["references"].items():
            records.append({"kind": "gas" if species == "H2" else "liquid", "species": species, **record})
        motif = payload["motifs"][0]
        for state, record in motif["states"].items():
            records.append({"kind": "surface", "motif": motif["motif"], "state": state, **record})
        mesa = {
            "conditions": payload["conditions"],
            "reference_policy": payload["reference_policy"],
            "free_energy_records": records,
        }
        result = MODULE.compute_bookkeeping(mesa)
        self.assertEqual(result["summary"]["motif_count"], 1)
        self.assertEqual(result["summary"]["closure_failure_count"], 0)

    def test_failed_evidence_is_excluded_from_ranking(self) -> None:
        payload = self.load_example()
        payload["motifs"][0]["states"]["O"]["evidence_acceptance_state"] = "failed"
        result = MODULE.compute_bookkeeping(payload)
        failed = next(row for row in result["descriptors"] if row["motif"] == "balanced_site")
        self.assertFalse(failed["ranking_eligible"])
        self.assertNotIn("balanced_site", [row["motif"] for row in result["activity_ranking"]])
        self.assertGreater(result["summary"]["blocking_warning_count"], 0)

    def test_external_h2o_phase_correction_double_count_is_rejected(self) -> None:
        payload = self.load_example()
        payload["reference_policy"]["h2o_reference_correction_eV"] = -0.088
        payload["references"]["H2O"] = {
            "electronic_energy_ev": 0.0,
            "corrections_ev": {"gas_to_liquid": -0.088},
            "phase": "gas",
        }
        with self.assertRaises(MODULE.OERInputError):
            MODULE.compute_bookkeeping(payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
