# YTK
# YTK

from dataclasses import asdict

from .wrapper import BalancedState, build_balanced_pathway

def to_metadata(reaction_pathway: str, policy_name: str, states: list[BalancedState]) -> dict:
    metadata = {}
    metadata['task_type'] = 'balance_string_reaction_pathway'
    metadata['status'] = 'finished'
    metadata['reaction_pathway'] = reaction_pathway
    metadata['policy'] = policy_name
    metadata['states'] = []
    for balanced_state in states:
        data = asdict(balanced_state)
        metadata['states'].append(data)

    return metadata


