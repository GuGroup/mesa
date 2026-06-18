# YTK
# YTK

from .species import SpeciesRef
from .formula import parse_formula_CHON
from .policy import ReservoirPolicy, ElectroChemPolicy
from .split import split_pathway_state
from .parser import parse_state_expr


def balance_state_to_reference(
    state: list[SpeciesRef],
    reference: list[SpeciesRef],
    policy: ReservoirPolicy | None = None
) -> list[SpeciesRef]:
    if policy is None:
        policy = ElectroChemPolicy()

    reference_count = count_CHON(reference)
    state_count = count_CHON(state)
    
    diff = {
        elem: reference_count[elem] - state_count[elem]
        for elem in reference_count
    }

    reservoir_terms = policy.solve(diff)
    return state + reservoir_terms

def count_CHON(state: list[SpeciesRef]) -> dict:
    count = {"C": 0.0, "H": 0.0, "O": 0.0, "N": 0.0}

    for species_ref in state:
        formula_count = parse_formula_CHON(species_ref.species)
        for elem, n in formula_count.items():
            count[elem] += n * species_ref.coefficient

    return count


