#!/usr/bin/env python3
"""Tests for the independent correct-dft-energy dispatcher."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MODULE_PATH = HERE / "run_correct_dft_energy.py"
SPEC = importlib.util.spec_from_file_location("run_correct_dft_energy", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class DispatchTests(unittest.TestCase):
    def test_detects_oer(self) -> None:
        payload = {
            "references": {"H2": {}, "H2O": {}, "O2": {}},
            "motifs": [{"states": {"clean": {}, "OH": {}, "O": {}, "OOH": {}}}],
        }
        self.assertEqual(MODULE.detect_mode(payload), "oer")

    def test_detects_no3rr(self) -> None:
        payload = {
            "references": {"HNO3": {}, "NH3": {}},
            "pathways": [{"states": []}],
        }
        self.assertEqual(MODULE.detect_mode(payload), "no3rr")

    def test_rejects_ambiguous_input(self) -> None:
        with self.assertRaises(MODULE.DispatchError):
            MODULE.detect_mode({"references": {}})

    def test_runs_oer_from_an_unrelated_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "oer_input.json"
            source.write_text(
                json.dumps(
                    {
                        "conditions": {
                            "temperature_K": 298.15,
                            "pH": 0.0,
                            "potential_v": 0.0,
                            "reference_electrode": "RHE",
                        },
                        "reference_policy": {
                            "o2_mode": "h2o_h2_cycle",
                            "o2_cycle_free_energy_eV": 4.92,
                            "o2_cycle_temperature_K": 298.15,
                            "o2_cycle_provenance": {"source": "synthetic test fixture"},
                        },
                        "references": {
                            "H2": {"free_energy_ev": 0.0, "phase": "gas"},
                            "H2O": {"free_energy_ev": 0.0, "phase": "liquid"},
                        },
                        "motifs": [
                            {
                                "motif": "test_site",
                                "states": {
                                    "clean": {"free_energy_ev": 0.0},
                                    "OH": {"free_energy_ev": 1.0},
                                    "O": {"free_energy_ev": 2.0},
                                    "OOH": {"free_energy_ev": 3.0},
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            outdir = Path(temporary) / "outputs"
            run = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--mode",
                    "auto",
                    "--input",
                    str(source),
                    "--outdir",
                    str(outdir),
                    "--strict",
                ],
                cwd=temporary,
                capture_output=True,
                text=True,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue((outdir / "oer_bookkeeping.json").is_file())
            dispatch = json.loads(run.stdout[: run.stdout.find("\n{", 1)])
            self.assertEqual(dispatch["selected_mode"], "oer")


if __name__ == "__main__":
    unittest.main()
