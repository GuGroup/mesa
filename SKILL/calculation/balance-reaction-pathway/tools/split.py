# YTK
# YTK

def split_pathway_state(reaction_pathway: str) -> list:
    states = [s.strip() for s in reaction_pathway.split(">")]
    states = [s for s in states if s]
    
    if any(not s for s in states):
        raise ValueError(f"empty state in reaction_pathway: {reaction_pathway!r}")

    if len(states) < 2:
        raise ValueError("reaction_pathway must contain at least two states")

    return states

