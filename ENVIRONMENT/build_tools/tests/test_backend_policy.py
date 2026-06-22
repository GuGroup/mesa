from __future__ import annotations

import unittest

from pymatgen.core import Lattice, Structure

from slabuilder.backend_policy import DEFAULT_BACKEND_POLICY


def structure_for(symbols: list[str]) -> Structure:
    lattice = Lattice.cubic(4.2)
    coords = [(i / max(len(symbols), 1), 0.0, 0.0) for i, _ in enumerate(symbols)]
    return Structure(lattice, symbols, coords)


class BackendPolicyTests(unittest.TestCase):
    def test_oxide_prefers_surfaxe(self) -> None:
        backend = DEFAULT_BACKEND_POLICY.choose(structure_for(["Ti", "O", "O"]))
        self.assertEqual(backend, "surfaxe")

    def test_binary_nitride_defaults_to_catkit(self) -> None:
        backend = DEFAULT_BACKEND_POLICY.choose(structure_for(["Ti", "N"]))
        self.assertEqual(backend, "catkit")

    def test_prefer_symmetry_still_overrides_chemistry(self) -> None:
        backend = DEFAULT_BACKEND_POLICY.choose(structure_for(["Ti", "N"]), prefer_symmetry=True)
        self.assertEqual(backend, "pymatgen")


if __name__ == "__main__":
    unittest.main()
