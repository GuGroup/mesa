#!/usr/bin/env python3
"""Create a demo trajectory for relaxation-result analysis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a small slab trajectory with intentional convergence-analysis events.")
    parser.add_argument("--output", default="demo_surface_jump.extxyz", help="Output extxyz path.")
    args = parser.parse_args()

    from ase import Atoms
    from ase.build import fcc111
    from ase.calculators.singlepoint import SinglePointCalculator
    from ase.constraints import FixAtoms
    from ase.io import write

    rng = np.random.default_rng(7)
    slab = fcc111("Cu", size=(4, 4, 3), vacuum=10.0, orthogonal=True)
    z = slab.positions[:, 2]
    bottom_cutoff = np.sort(np.unique(np.round(z, 6)))[0] + 0.2
    fixed = [int(i) for i, value in enumerate(z) if value <= bottom_cutoff]
    slab.set_constraint(FixAtoms(indices=fixed))

    top_z = float(z.max())
    cell = slab.cell.array
    site_a = np.array([0.42 * cell[0, 0], 0.42 * cell[1, 1], top_z + 1.85])
    site_b = np.array([0.58 * cell[0, 0], 0.40 * cell[1, 1], top_z + 1.85])
    site_c = np.array([0.33 * cell[0, 0], 0.68 * cell[1, 1], top_z + 1.95])

    atoms0 = slab + Atoms("CO", positions=[site_a, site_a + [0.0, 0.0, 1.15]])
    atoms0.info.pop("adsorbate_info", None)
    ads = [len(atoms0) - 2, len(atoms0) - 1]
    # Mark the adsorbate (slabuilder's convention) so the renderer suppresses
    # slab-slab bonds and only draws ads-ads / ads-slab ones.
    atoms0.info["adsorbate_atom_indices_json"] = json.dumps(ads)
    top = [int(i) for i, value in enumerate(atoms0.positions[:, 2]) if top_z - 0.2 <= value <= top_z + 0.2]

    energies = [-0.10, -0.45, -0.78, -0.98, -0.83, -1.08, -0.52, -0.90, -1.14, -1.24, -1.29, -1.31]
    fmax_values = [4.2, 3.4, 2.6, 1.7, 2.4, 1.2, 5.4, 3.1, 1.5, 0.7, 0.22, 0.06]

    frames = []
    for step, (energy, fmax) in enumerate(zip(energies, fmax_values)):
        atoms = atoms0.copy()
        atoms.set_constraint(FixAtoms(indices=fixed))
        frac = step / (len(energies) - 1)

        if step < 6:
            progress = step / 5
            c_pos = (1 - progress) * site_a + progress * site_b
            o_offset = np.array([0.10 * progress, 0.0, 1.15 - 0.08 * progress])
        else:
            progress = (step - 6) / 5
            c_pos = (1 - progress) * site_c + progress * (site_c + [0.22, -0.18, -0.10])
            o_offset = np.array([0.38 - 0.16 * progress, 0.15, 1.02 + 0.05 * progress])

        atoms.positions[ads[0]] = c_pos
        atoms.positions[ads[1]] = c_pos + o_offset

        for index in top:
            if index in fixed:
                continue
            atoms.positions[index] += rng.normal(0.0, 0.015 + 0.01 * frac, size=3)
        if step >= 6:
            atoms.positions[top[5]] += [0.05 * (step - 5), -0.02 * (step - 5), 0.06 * (step - 5)]

        forces = np.zeros((len(atoms), 3))
        forces[ads[0]] = [fmax, 0.0, 0.0]
        forces[top[5]] = [0.0, 0.25 * fmax, 0.0]
        atoms.calc = SinglePointCalculator(atoms, energy=energy, forces=forces)
        atoms.info["demo_note"] = "synthetic slab/CO trajectory with energy, force, and RMSD events"
        frames.append(atoms)

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    write(str(output), frames, format="extxyz")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
