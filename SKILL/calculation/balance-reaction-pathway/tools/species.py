# YTK
# YTK

from dataclasses import dataclass

@dataclass(frozen=True)
class SpeciesRef:
    species: str
    phase: str
    coefficient: float = 1.0
