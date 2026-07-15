# YTK
# YTK

from pathlib import Path

import json
from ase.io import read

from .calculate_vib import get_frequencies, get_zpe_ts


def run(reaction: dict, mapping: dict) -> dict[str, float]:
    for m in mapping['entries']:
        if m['species'] == "slab":
            outcar = read(m['outcar'], index='-1')
            slab_G = outcar.get_potential_energy()

    all_G = {}
    
    reference_label = reaction['states'][0]['label']

    for state in reaction['states']:
        label = state['label']
        balanced_state = state['balanced_state']
        slab_count = state['slab_count']
        
        state_G = 0

        for species_ref in balanced_state:
            E = None
            ZPE, TS = 0.0, 0.0
            for m in mapping['entries']:

                if m['species'] != species_ref['species']:
                    continue
                if m['phase'] != species_ref['phase']:
                    continue

                if m['calc_mode'] == 'static':
                    outcar = read(m['outcar'], index="-1")
                    E = outcar.get_potential_energy()

                elif m['calc_mode'] == 'vib':
                    frequencies = get_frequencies(Path(m['outcar']).parent)
                    if species_ref['phase'] == "GAS":
                        if "thermo" not in m:
                            raise ValueError(f"missing thermo metadat for GAS vib: {species_ref}")

                        outcar = read(m['outcar'], index="-1")
                        thermo={
                            "outcar": outcar,
                            "geometry": m['thermo']['geometry'],
                            "symmetrynumber": m['thermo']['symmetrynumber'],
                            "spin": m['thermo']['spin'],
                        }
                        ZPE, TS = get_zpe_ts(frequencies, "GAS", T=298, **thermo)

                    elif species_ref['phase'] == "ADS":
                        ZPE, TS = get_zpe_ts(frequencies, "ADS", T=298)

            if E is None:
                raise ValueError(f"missing static energy for {species_ref}")

            species_G = E + ZPE - TS
            species_G = species_ref['coefficient'] * species_G
            state_G += species_G
        
        state_G += slab_count * slab_G
        all_G[label] = state_G
    
    reference_G = all_G[reference_label]
    for label, G in all_G.items():
        all_G[label] = G - reference_G

    return all_G


import matplotlib.pyplot as plt

# reaction is general for one task
reaction = json.load(open("/Users/ytkim/MLwork/agent/mesa_ytk/results/TASK2/CoNiCuRu_NO3RR/reaction.json", "r"))
# mapping is specific for each metal
mapping = json.load(open("/Users/ytkim/MLwork/agent/mesa_ytk/results/TASK2/CoNiCuRu_NO3RR/map.json", "r"))
# both are crucial information.

all_G = run(reaction, mapping)
ll = []
gg = []
for l, g in all_G.items():
    ll.append(l)
    gg.append(g)

plt.scatter(ll,gg)
plt.show()
            
                    
