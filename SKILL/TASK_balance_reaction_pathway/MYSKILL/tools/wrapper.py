# YTK
# YTK

from dataclasses import dataclass

from .species import SpeciesRef
from .split import split_pathway_state
from .parser import parse_state_expr
from .policy import ReservoirPolicy, ElectroChemPolicy
from .balancer import balance_state_to_reference



@dataclass(frozen=True)
class BalancedState:
    label: str
    raw_state: list[SpeciesRef]
    balanced_state: list[SpeciesRef]
    slab_count: float = 0.0

def count_ads_species(balanced_state: list[SpeciesRef]) -> float:
    count = 0.0
    for species in balanced_state:
        if species.phase=="ADS":
            count += species.coefficient
    return count

def build_balanced_pathway(
    reaction_pathway: str,
    reference_idx: int | None = None,
    policy: ReservoirPolicy | None = None,
    ) -> list[BalancedState]:

    # We call list[SpeciesRef] as state!

    if reference_idx is None:
        reference_idx = 0

    if policy is None:
        policy = ElectroChemPolicy()

    labels = split_pathway_state(reaction_pathway)
    raw_states = [parse_state_expr(label) for label in labels]

    reference_state = raw_states[reference_idx]
    
    balanced_states = [
        balance_state_to_reference(
            state=raw_state,
            reference=reference_state,
            policy=policy,
        )
        for raw_state in raw_states
    ]
    
    ads_counts = [count_ads_species(state) for state in balanced_states]
    max_ads_count = max(ads_counts)
    
    return [
        BalancedState(
            label=label,
            raw_state=raw_state,
            balanced_state=balanced_state,
            slab_count=max_ads_count - ads_count,
        )
        for (label, raw_state, balanced_state, ads_count) in zip(
            labels, raw_states, balanced_states, ads_counts)
    ]
