# YTK
# YTK
from pathlib import Path

from ase.thermochemistry import IdealGasThermo, HarmonicThermo
import numpy as np
from numpy.typing import NDArray

def get_frequencies(outcar: Path) -> NDArray:
    if not outcar.is_file():
        raise FileNotFoundError(f"vibrational OUTCAR does not exist: {outcar}")

    frequencies: list[float] = []
    for line in outcar.read_text(encoding="utf-8", errors="replace").splitlines():
        if "THz" not in line or "cm-1" not in line or "f/i" in line:
            continue
        tokens = line.split()
        cm_index = tokens.index("cm-1")
        frequencies.append(float(tokens[cm_index - 1]))

    if not frequencies:
        raise ValueError(f"no real vibrational frequencies found in {outcar}")
    return np.asarray(frequencies, dtype=float)

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
