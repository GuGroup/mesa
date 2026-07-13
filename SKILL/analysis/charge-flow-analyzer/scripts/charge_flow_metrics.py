from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from pymatgen.io.vasp.outputs import Chgcar


@dataclass(frozen=True, slots=True)
class ZProfile:
    z_ang: NDArray[np.float64]
    raw_plane_average: NDArray[np.float64]
    delta_n_avg_e_per_ang3: NDArray[np.float64]
    delta_lambda_e_per_ang: NDArray[np.float64]
    q_e_from_bottom_e: NDArray[np.float64]
    q_e_from_top_e: NDArray[np.float64]
    dz_ang: float
    area_ang2: float
    c_length_ang: float
    volume_ang3: float


def build_z_profile(delta_chgcar: Chgcar) -> ZProfile:
    raw_plane = np.asarray(delta_chgcar.get_average_along_axis(2), dtype=np.float64)
    z_grid = np.asarray(delta_chgcar.get_axis_grid(2), dtype=np.float64)
    matrix = np.asarray(delta_chgcar.structure.lattice.matrix, dtype=np.float64)
    c_length = max(float(np.linalg.norm(matrix[2])), 1e-12)
    volume = max(float(delta_chgcar.structure.lattice.volume), 1e-12)
    dz = c_length / max(float(len(z_grid)), 1.0)
    delta_n_avg = raw_plane / volume
    delta_lambda = raw_plane / c_length
    q_bottom = np.cumsum(delta_lambda) * dz
    q_top = np.cumsum(delta_lambda[::-1]) * dz
    return ZProfile(
        z_ang=z_grid,
        raw_plane_average=raw_plane,
        delta_n_avg_e_per_ang3=delta_n_avg,
        delta_lambda_e_per_ang=delta_lambda,
        q_e_from_bottom_e=q_bottom,
        q_e_from_top_e=q_top[::-1],
        dz_ang=dz,
        area_ang2=volume / c_length,
        c_length_ang=c_length,
        volume_ang3=volume,
    )


def write_legacy_plane_csv(path: Path, profile: ZProfile) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["z_ang", "delta_plane_average", "cumulative_integral_assuming_density_units"])
        for z_value, avg_value, cumulative_value in zip(profile.z_ang, profile.raw_plane_average, profile.q_e_from_bottom_e):
            writer.writerow([f"{z_value:.10g}", f"{avg_value:.10g}", f"{cumulative_value:.10g}"])


def write_z_profile_csv(path: Path, profile: ZProfile) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "z_A",
            "delta_plane_average_raw_chgcar",
            "delta_n_avg_e_per_A3",
            "delta_lambda_e_per_A",
            "q_e_from_bottom_e",
            "q_e_from_top_e",
        ])
        rows = zip(
            profile.z_ang,
            profile.raw_plane_average,
            profile.delta_n_avg_e_per_ang3,
            profile.delta_lambda_e_per_ang,
            profile.q_e_from_bottom_e,
            profile.q_e_from_top_e,
        )
        for row in rows:
            writer.writerow([f"{float(value):.10g}" for value in row])


def build_dipole_summary(profile: ZProfile) -> dict[str, str | int | float | bool]:
    electron_moment = float(np.sum(profile.z_ang * profile.delta_lambda_e_per_ang) * profile.dz_ang)
    positive = float(np.clip(profile.delta_lambda_e_per_ang, 0.0, None).sum() * profile.dz_ang)
    negative = float(np.clip(profile.delta_lambda_e_per_ang, None, 0.0).sum() * profile.dz_ang)
    half_abs = float(0.5 * np.abs(profile.delta_lambda_e_per_ang).sum() * profile.dz_ang)
    net = float(profile.q_e_from_bottom_e[-1]) if len(profile.q_e_from_bottom_e) else 0.0
    electrostatic_dipole = -electron_moment
    return {
        "schema_version": 1,
        "density_convention": "delta_n_avg = raw_plane_average / cell_volume; delta_lambda = raw_plane_average / c_length",
        "z_origin": "bottom of CHGCAR cell axis 3",
        "cell_volume_A3": profile.volume_ang3,
        "surface_area_A2": profile.area_ang2,
        "c_length_A": profile.c_length_ang,
        "dz_A": profile.dz_ang,
        "net_electron_count_residual_e": net,
        "positive_delta_lambda_integral_e": positive,
        "negative_delta_lambda_integral_e": negative,
        "half_abs_redistribution_e": half_abs,
        "electron_density_moment_e_A": electron_moment,
        "electrostatic_dipole_e_A": electrostatic_dipole,
        "electrostatic_dipole_per_area_e_A_per_A2": electrostatic_dipole / profile.area_ang2,
        "work_function_available": False,
        "work_function_note": "CHGCAR-derived dipole descriptor only; use LOCPOT/electrostatic potential for work-function claims.",
    }
