# YTK
# YTK
from pathlib import Path

from ase.thermochemistry import IdealGasThermo, HarmonicThermo
import numpy as np
from numpy.typing import NDArray

def get_frequencies(path: Path) -> NDArray:
    outcar = path / "OUTCAR" if path.is_dir() else path
    frequencies = []
    with outcar.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if "THz" not in line or "f/i" in line:
                continue
            tokens = line.split()
            if "cm-1" in tokens:
                frequencies.append(float(tokens[tokens.index("cm-1") - 1]))
    return np.array(frequencies)

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
