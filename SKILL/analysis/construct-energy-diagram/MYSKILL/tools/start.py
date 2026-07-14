#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ase.io import read

from .calculate_vib import get_frequencies, get_zpe_ts


def run(reaction: dict[str, Any], mapping: dict[str, Any]) -> dict[str, float]:
    entries = mapping.get("entries")
    states = reaction.get("states")
    if not isinstance(entries, list) or not entries:
        raise ValueError("mapping.entries must be a non-empty list")
    if not isinstance(states, list) or not states:
        raise ValueError("reaction.states must be a non-empty list")

    slab_entries = [
        entry
        for entry in entries
        if entry.get("species") == "slab" and entry.get("calc_mode") == "static"
    ]
    if len(slab_entries) != 1:
        raise ValueError("mapping must contain exactly one static slab entry")
    slab_energy = float(read(slab_entries[0]["outcar"], index="-1").get_potential_energy())

    absolute_energies: dict[str, float] = {}
    for state in states:
        label = str(state["label"])
        state_energy = 0.0
        for species_ref in state["balanced_state"]:
            state_energy += _species_free_energy(species_ref, entries)
        state_energy += float(state.get("slab_count", 0.0)) * slab_energy
        absolute_energies[label] = state_energy

    reference_label = str(states[0]["label"])
    reference_energy = absolute_energies[reference_label]
    return {
        label: energy - reference_energy
        for label, energy in absolute_energies.items()
    }


def _species_free_energy(
    species_ref: dict[str, Any],
    entries: list[dict[str, Any]],
) -> float:
    species = species_ref["species"]
    phase = species_ref["phase"]
    matches = [
        entry
        for entry in entries
        if entry.get("species") == species and entry.get("phase") == phase
    ]
    static_entries = [entry for entry in matches if entry.get("calc_mode") == "static"]
    vibration_entries = [entry for entry in matches if entry.get("calc_mode") == "vib"]
    if len(static_entries) != 1:
        raise ValueError(
            f"expected exactly one static calculation for {species!r} in phase {phase!r}"
        )
    if len(vibration_entries) > 1:
        raise ValueError(
            f"duplicate vibrational calculations for {species!r} in phase {phase!r}"
        )

    static_atoms = read(static_entries[0]["outcar"], index="-1")
    energy = float(static_atoms.get_potential_energy())
    zpe = 0.0
    entropy_term = 0.0
    if vibration_entries:
        vibration = vibration_entries[0]
        frequencies = get_frequencies(Path(vibration["outcar"]))
        if phase == "GAS":
            thermo = vibration.get("thermo")
            if not isinstance(thermo, dict):
                raise ValueError(
                    f"missing thermo metadata for gas vibration entry: {species!r}"
                )
            vibration_atoms = read(vibration["outcar"], index="-1")
            zpe, entropy_term = get_zpe_ts(
                frequencies,
                "GAS",
                T=298.0,
                outcar=vibration_atoms,
                geometry=thermo["geometry"],
                symmetrynumber=thermo["symmetrynumber"],
                spin=thermo["spin"],
            )
        elif phase == "ADS":
            zpe, entropy_term = get_zpe_ts(frequencies, "ADS", T=298.0)
        else:
            raise ValueError(f"unsupported vibrational phase: {phase!r}")

    coefficient = float(species_ref["coefficient"])
    return coefficient * (energy + zpe - entropy_term)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Construct a relative reaction free-energy profile from reaction and mapping JSON files."
    )
    parser.add_argument("--reaction", required=True, type=Path, help="Path to reaction.json")
    parser.add_argument("--mapping", required=True, type=Path, help="Path to map.json")
    parser.add_argument("--output", required=True, type=Path, help="Path for relative-energy JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    reaction = json.loads(args.reaction.read_text(encoding="utf-8"))
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    result = run(reaction, mapping)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
