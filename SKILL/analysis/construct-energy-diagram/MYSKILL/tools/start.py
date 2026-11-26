# YTK
# YTK

import argparse
import json
from pathlib import Path

from ase.io import read

from .calculate_vib import get_frequencies, get_zpe_ts


def run(reaction: dict, mapping: dict) -> dict[str, float]:
    slab_G = None
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
                    frequencies = get_frequencies(Path(m['outcar']))
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
        
        if slab_count:
            if slab_G is None:
                raise ValueError(f"missing slab energy for {label}")
            state_G += slab_count * slab_G
        all_G[label] = state_G
    
    reference_G = all_G[reference_label]
    for label, G in all_G.items():
        all_G[label] = G - reference_G

    return all_G


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute relative reaction energies.")
    parser.add_argument("--reaction", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    reaction = json.loads(args.reaction.read_text(encoding="utf-8"))
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    for entry in mapping["entries"]:
        entry["outcar"] = str(args.mapping.parent / entry["outcar"])

    energies = run(reaction, mapping)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(energies, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
