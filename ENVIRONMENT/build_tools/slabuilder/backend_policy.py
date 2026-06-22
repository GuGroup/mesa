"""Backend selection policy for slab generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pymatgen.core import Structure

from slabuilder.config import BACKEND_DEFAULT, BACKEND_OXIDE_NITRIDE, BACKEND_SYMMETRY

Backend = Literal["catkit", "pymatgen", "surfaxe"]


def composition_symbols(structure: Structure) -> set[str]:
    """Return element symbols present in a structure composition."""
    return {getattr(el, "symbol", str(el)) for el in structure.composition.elements}


@dataclass(frozen=True)
class BackendPolicy:
    """Resolve slab generation backend from explicit user intent and chemistry."""

    oxide_backend: Backend = "surfaxe"
    default_backend: Backend = "catkit"
    symmetry_backend: Backend = "pymatgen"

    def is_oxide_like(self, structure: Structure) -> bool:
        symbols = composition_symbols(structure)
        return "O" in symbols and bool(symbols - {"O"})

    def is_nitride_like(self, structure: Structure) -> bool:
        symbols = composition_symbols(structure)
        return "N" in symbols and "O" not in symbols and bool(symbols - {"N"})

    def choose(
        self,
        structure: Structure,
        explicit_backend: Backend | None = None,
        prefer_symmetry: bool = False,
    ) -> Backend:
        """Choose backend. Explicit backend always wins."""
        if explicit_backend is not None:
            return explicit_backend
        if prefer_symmetry:
            return self.symmetry_backend
        if self.is_oxide_like(structure):
            return self.oxide_backend
        if self.is_nitride_like(structure):
            return self.default_backend
        return self.default_backend


DEFAULT_BACKEND_POLICY = BackendPolicy(
    oxide_backend=BACKEND_OXIDE_NITRIDE,
    default_backend=BACKEND_DEFAULT,
    symmetry_backend=BACKEND_SYMMETRY,
)


def choose_backend_for_structure(
    structure: Structure,
    explicit_backend: Backend | None = None,
    prefer_symmetry: bool = False,
) -> Backend:
    """Convenience wrapper around the default backend policy."""
    return DEFAULT_BACKEND_POLICY.choose(
        structure=structure,
        explicit_backend=explicit_backend,
        prefer_symmetry=prefer_symmetry,
    )
