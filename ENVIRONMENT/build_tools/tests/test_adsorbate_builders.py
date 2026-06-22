from __future__ import annotations

import json
import unittest

from ase.build import fcc111

from slabuilder.adsorption import (
    AdsorbatePlacementSpec,
    _build_adsorbate_atoms,
    add_multiple_adsorbates_to_slab,
)
from slabuilder.structure_understanding import validate_structure_packet


class AdsorbateBuilderTests(unittest.TestCase):
    def test_h2_adsorbate_is_supported_for_hor(self) -> None:
        atoms = _build_adsorbate_atoms("H2")
        self.assertEqual(atoms.get_chemical_formula(), "H2")
        self.assertEqual(atoms.info.get("adsorbate_builder"), "ase")

    def test_multiple_adsorbates_can_be_placed_on_one_slab(self) -> None:
        slab = fcc111("Cu", size=(3, 3, 3), vacuum=8.0)
        slab.set_pbc([True, True, False])

        atoms = add_multiple_adsorbates_to_slab(
            slab,
            [
                AdsorbatePlacementSpec("CO", "top", 0),
                AdsorbatePlacementSpec("O", "hollow", 0),
            ],
            backend="catkit",
            min_site_separation=0.0,
        )

        self.assertEqual(len(atoms), len(slab) + 3)
        self.assertEqual(atoms.info.get("multi_adsorbate_count"), 2)
        placements = json.loads(atoms.info["multi_adsorbate_metadata_json"])
        self.assertEqual([item["adsorbate"] for item in placements], ["CO", "O"])
        self.assertTrue(all(item["binding_contact"]["ok"] for item in placements))
        self.assertTrue(validate_structure_packet(atoms)["passed"])


if __name__ == "__main__":
    unittest.main()
