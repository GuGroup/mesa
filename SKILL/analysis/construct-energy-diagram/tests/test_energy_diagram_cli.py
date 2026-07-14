from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from MYSKILL.tools import calculate_vib, start


class _FakeAtoms:
    def __init__(self, energy: float) -> None:
        self._energy = energy

    def get_potential_energy(self) -> float:
        return self._energy


class EnergyDiagramCliTest(unittest.TestCase):
    def test_run_uses_supplied_artifacts_without_import_time_files(self) -> None:
        reaction = {
            "states": [
                {
                    "label": "initial",
                    "balanced_state": [
                        {"species": "H2", "phase": "GAS", "coefficient": 1.0}
                    ],
                    "slab_count": 0.0,
                },
                {
                    "label": "final",
                    "balanced_state": [
                        {"species": "H2", "phase": "GAS", "coefficient": 2.0}
                    ],
                    "slab_count": 0.0,
                },
            ]
        }
        mapping = {
            "entries": [
                {"species": "slab", "phase": "SLAB", "calc_mode": "static", "outcar": "slab.OUTCAR"},
                {"species": "H2", "phase": "GAS", "calc_mode": "static", "outcar": "h2.OUTCAR"},
            ]
        }

        with patch.object(start, "read", side_effect=[_FakeAtoms(10.0), _FakeAtoms(2.0), _FakeAtoms(2.0)]):
            result = start.run(reaction, mapping)

        self.assertEqual(result, {"initial": 0.0, "final": 2.0})

    def test_cli_writes_json_to_requested_output(self) -> None:
        reaction = {
            "states": [
                {
                    "label": "only",
                    "balanced_state": [
                        {"species": "H2", "phase": "GAS", "coefficient": 1.0}
                    ],
                    "slab_count": 0.0,
                }
            ]
        }
        mapping = {
            "entries": [
                {"species": "slab", "phase": "SLAB", "calc_mode": "static", "outcar": "slab.OUTCAR"},
                {"species": "H2", "phase": "GAS", "calc_mode": "static", "outcar": "h2.OUTCAR"},
            ]
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reaction_path = root / "reaction.json"
            mapping_path = root / "map.json"
            output_path = root / "result.json"
            reaction_path.write_text(json.dumps(reaction), encoding="utf-8")
            mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
            with patch.object(start, "read", side_effect=[_FakeAtoms(10.0), _FakeAtoms(2.0)]):
                exit_code = start.main([
                    "--reaction",
                    str(reaction_path),
                    "--mapping",
                    str(mapping_path),
                    "--output",
                    str(output_path),
                ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), {"only": 0.0})

    def test_missing_vibrational_outcar_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "custom.OUTCAR"
            with self.assertRaises(FileNotFoundError):
                calculate_vib.get_frequencies(missing)


if __name__ == "__main__":
    unittest.main()
