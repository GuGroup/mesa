# YTK
# YTK

from dataclasses import dataclass
from .species import SpeciesRef

class ReservoirPolicy:
    def solve(self, diff: dict[str, float]) -> list[SpeciesRef]:
        raise NotImplementedError

@dataclass(frozen=True)
class ElectroChemPolicy(ReservoirPolicy):
    def solve(self, diff: dict[str, float]) -> list[SpeciesRef]:
        # diff = a CO + b H2O + c NH3 + d H2
        a = diff["C"]
        c = diff["N"]
        b = diff["O"] - a
        d = (diff["H"] - 2*b - 3*c) / 2

        refs = [
            SpeciesRef("CO", "GAS", a),
            SpeciesRef("H2O", "GAS", b),
            SpeciesRef("NH3", "GAS", c),
            SpeciesRef("H2", "GAS", d),
        ]

        return [r for r in refs if abs(r.coefficient) > 1e-12]

