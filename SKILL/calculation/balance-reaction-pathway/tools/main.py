# YTK
# YTK

from .wrapper import build_balanced_pathway
from .policy import ReservoirPolicy, ElectroChemPolicy
from .serializer import to_metadata

def policy_from_system(system: str):
    normalized = system.strip().lower()
    if normalized in ["electrochem", "electrochemical", "electrochemistry"]:
        return "ElectroChemPolicy", ElectroChemPolicy()
    
    raise ValueError(
        f"unsupported system: {system!r}"
        "Currently supported: 'ElectroChem'."
    )


def run(reaction_pathway: str, system: str, reference_idx: int = 0) -> dict:
    policy_name, policy = policy_from_system(system)

    states = build_balanced_pathway(
        reaction_pathway=reaction_pathway, 
        reference_idx=reference_idx, 
        policy=policy
    )

    metadata = to_metadata(
        reaction_pathway=reaction_pathway, 
        policy_name=policy_name, 
        states=states)

    return metadata


a = run("HNO3(g)>*NO3>*NO2>*NO>*NOH>*N>*NH>*NH2>NH3(g)", "ElectroChem")

print(a)
