from __future__ import annotations

import unittest

from ase import Atoms

from slabuilder.structure_understanding import (
    analyze_surface_sites_packet,
    _adsorbate_bond_pairs,
    propose_local_transform_packet,
)


def slab_with_h() -> Atoms:
    atoms = Atoms(
        "Pt2H",
        positions=[
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [0.0, 0.0, 1.6],
        ],
        cell=[6.0, 6.0, 12.0],
        pbc=[True, True, False],
    )
    atoms.set_tags([1, 1, 2])
    return atoms


class StructureUnderstandingTests(unittest.TestCase):
    def test_current_site_prefers_source_site_metadata(self) -> None:
        atoms = slab_with_h()
        record = {
            "source_site": {
                "site_type": "bridge",
                "position": [1.0, 0.0, 0.0],
                "placed_position": [1.0, 0.0, 0.0],
                "surface_atom_indices": [0, 1],
                "sources": ["catkit"],
                "validation_score": 1.0,
            },
            "site_map": {
                "sites": [
                    {
                        "id": "site:0",
                        "site_type": "top",
                        "position": [1.05, 0.0, 0.0],
                        "surface_atom_indices": [0],
                    },
                    {
                        "id": "site:1",
                        "site_type": "bridge",
                        "position": [1.05, 0.0, 0.0],
                        "surface_atom_indices": [0, 1],
                    },
                ],
                "neighbors": [],
            },
        }

        packet = analyze_surface_sites_packet(atoms, record=record)

        current = packet["current_site"]
        self.assertEqual(current["site_type"], "bridge")
        self.assertEqual(current["surface_atom_indices"], [0, 1])
        self.assertEqual(current["id"], "site:1")
        self.assertEqual(current["source"], "metadata")
        self.assertEqual(current["site_map_match_method"], "surface_atom_indices")

    def test_diffusion_uses_spatial_fallback_when_source_site_has_no_graph_id(self) -> None:
        atoms = slab_with_h()
        record = {
            "kind": "adsorbate",
            "adsorbate_metadata": {
                "atom_indices": [2],
                "anchor_index": 2,
                "formula": "H",
            },
            "source_site": {
                "site_type": "bridge",
                "position": [0.0, 0.0, 0.0],
                "placed_position": [0.0, 0.0, 0.0],
                "surface_atom_indices": [0, 1],
                "sources": ["catkit"],
                "validation_score": 1.0,
            },
            "site_map": {
                "sites": [
                    {
                        "id": "site:0",
                        "site_type": "top",
                        "position": [0.8, 0.0, 0.0],
                        "surface_atom_indices": [0],
                    },
                    {
                        "id": "site:1",
                        "site_type": "bridge",
                        "position": [2.0, 0.0, 0.0],
                        "surface_atom_indices": [1, 2],
                    },
                ],
                "neighbors": [],
            },
        }

        packet = propose_local_transform_packet(
            atoms,
            record=record,
            transform_type="diffusion",
            target_adsorbate="H",
            max_site_distance=2.5,
            neighbor_shell=1,
            max_candidates=2,
        )

        self.assertEqual(packet["warnings"], [])
        self.assertGreaterEqual(len(packet["candidates"]), 1)
        self.assertEqual(packet["candidates"][0]["target_site"]["id"], "site:0")

    def test_adsorbate_bond_pairs_prune_terminal_terminal_edges(self) -> None:
        atoms = Atoms(
            "NHH",
            positions=[
                [0.0, 0.0, 0.0],
                [0.48, 0.0, 0.84],
                [-0.48, 0.0, 0.84],
            ],
        )

        bonds = _adsorbate_bond_pairs(atoms, [0, 1, 2])

        self.assertEqual(bonds, [(0, 1), (0, 2)])


if __name__ == "__main__":
    unittest.main()
