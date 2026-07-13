from __future__ import annotations

import argparse
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray
from pymatgen.core import Lattice, Structure
from pymatgen.io.vasp.outputs import Chgcar

from charge_flow_core import run_difference

PT_SITES: Final = [
    (0.25, 0.25, 0.22),
    (0.75, 0.25, 0.22),
    (0.25, 0.75, 0.22),
    (0.75, 0.75, 0.22),
    (0.25, 0.25, 0.34),
    (0.75, 0.25, 0.34),
    (0.25, 0.75, 0.34),
    (0.75, 0.75, 0.34),
]
ADS_SITES: Final = [(0.25, 0.25, 0.49), (0.25, 0.25, 0.60)]
GRID_SHAPE: Final = (36, 36, 56)


def run_example(outdir_text: str) -> None:
    outdir = Path(outdir_text).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)
    lattice = Lattice.from_parameters(5.6, 5.6, 14.0, 90.0, 90.0, 90.0)
    structure = Structure(lattice, ["Pt"] * len(PT_SITES) + ["C", "O"], [*PT_SITES, *ADS_SITES])
    clean = sum((5.0 * gaussian(GRID_SHAPE, site, 0.035) for site in PT_SITES), start=np.zeros(GRID_SHAPE, dtype=np.float64))
    ads = 1.6 * gaussian(GRID_SHAPE, ADS_SITES[0], 0.030) + 2.0 * gaussian(GRID_SHAPE, ADS_SITES[1], 0.030)
    redistribution = 0.36 * gaussian(GRID_SHAPE, (0.25, 0.25, 0.425), 0.040)
    redistribution -= 0.20 * gaussian(GRID_SHAPE, (0.25, 0.25, 0.515), 0.040)
    redistribution -= 0.16 * gaussian(GRID_SHAPE, (0.25, 0.25, 0.355), 0.040)

    paths = {"combined": outdir / "CHGCAR_combined", "clean": outdir / "CHGCAR_clean", "adsorbate": outdir / "CHGCAR_adsorbate"}
    Chgcar(structure, {"total": clean + ads + redistribution}).write_file(paths["combined"])
    Chgcar(structure, {"total": clean}).write_file(paths["clean"])
    Chgcar(structure, {"total": ads}).write_file(paths["adsorbate"])
    args = argparse.Namespace(
        term=[f"combined=1:{paths['combined']}", f"clean=-1:{paths['clean']}", f"adsorbate=-1:{paths['adsorbate']}"],
        outdir=str(outdir / "analysis"),
        comparison="adsorption",
        title="Synthetic charge-flow example",
        slices=True,  # exercise the (opt-in) slice renderer in the smoke test
        write_delta_chgcar=True,
        lattice_atol=1e-5,
    )
    run_difference(args)


def gaussian(shape: tuple[int, int, int], center: tuple[float, float, float], sigma: float) -> NDArray[np.float64]:
    grids = np.meshgrid(*[np.linspace(0.0, 1.0, n, endpoint=False) for n in shape], indexing="ij")
    dist2 = sum((grid - coord) ** 2 for grid, coord in zip(grids, center))
    return np.exp(-dist2 / (2.0 * sigma**2)).astype(np.float64)
