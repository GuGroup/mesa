# YTK
# YTK
from pathlib import Path
import subprocess

from ase.thermochemistry import IdealGasThermo, HarmonicThermo
import numpy as np
from numpy.typing import NDArray

def get_frequencies(zpe_dir: Path):
    result = subprocess.run(
        "grep THz OUTCAR",
        shell=True,
        cwd=zpe_dir,
        capture_output=True,
        text=True,
    )   
    frequencies = []
    for line in result.stdout.splitlines():
        if "f/i" in line:
            continue
        tokens = line.split()
        thz_index = tokens.index("cm-1")
        freq = float(tokens[thz_index - 1]) 
        frequencies.append(freq)

    frequencies = np.array(frequencies)
    return frequencies

def get_zpe_ts(frequencies: NDArray, phase: str, T: float = 298.15, **kwargs):
    frequencies = np.asarray(frequencies, dtype=float)
    vib_energies = frequencies * 1.23981e-4  # cm-1 -> eV

    if phase == "GAS":
        P = kwargs.get("pressure", 101325)
        outcar = kwargs["outcar"]
        geometry = kwargs["geometry"]
        symmetrynumber = kwargs["symmetrynumber"]
        spin = kwargs["spin"]
        thermo = IdealGasThermo(
            vib_energies=vib_energies,
            potentialenergy=0.0,
            atoms=outcar,
            geometry=geometry,
            symmetrynumber=symmetrynumber,
            spin=spin,
        )
        zpe = thermo.get_ZPE_correction()
        S = thermo.get_entropy(T, P, verbose=False)

    elif phase == "ADS":
        thermo = HarmonicThermo(
            vib_energies=vib_energies,
            potentialenergy=0.0,
        )
        zpe = thermo.get_ZPE_correction()
        S = thermo.get_entropy(T, verbose=False)
    else:
        raise ValueError(f"unknown phase: {phase!r}")

    return float(zpe), float(T * S)
