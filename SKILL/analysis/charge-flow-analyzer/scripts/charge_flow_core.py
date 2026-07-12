from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray
from pymatgen.core import Structure
from pymatgen.io.vasp.outputs import Chgcar

from charge_flow_metrics import build_dipole_summary, build_z_profile, write_legacy_plane_csv, write_z_profile_csv
from charge_flow_profile import write_side_profile_plot
from charge_flow_rendering import write_lobe_isosurface, write_slice_plots

PLANE_CSV: Final = "plane_average_z.csv"
Z_PROFILE_CSV: Final = "z_profile.csv"
DIPOLE_JSON: Final = "dipole_summary.json"
PLANE_PNG: Final = "plane_average_z.png"
SLICES_PNG: Final = "delta_density_slices.png"
ISOSURFACE_PNG: Final = "delta_density_isosurface.png"
REPORT_MD: Final = "charge_flow_report.md"
DELTA_CHGCAR: Final = "delta.CHGCAR"


@dataclass(frozen=True, slots=True)
class Term:
    label: str
    coefficient: float
    path: Path


@dataclass(frozen=True, slots=True)
class LoadedTerm:
    term: Term
    chgcar: Chgcar


@dataclass(frozen=True, slots=True)
class OutputPaths:
    plane_csv: Path
    z_profile_csv: Path
    dipole_json: Path
    plane_png: Path
    slices_png: Path | None
    isosurface_png: Path
    delta_chgcar: Path | None


@dataclass(frozen=True, slots=True)
class ChargeFlowError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


def run_difference(args: argparse.Namespace) -> None:
    terms = [parse_term(raw) for raw in args.term]
    loaded = [LoadedTerm(term=term, chgcar=load_chgcar(term.path)) for term in terms]
    validate_compatible_grids(loaded, lattice_atol=args.lattice_atol)
    outdir = Path(str(args.outdir)).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)

    base = loaded[0].chgcar
    delta = combine_terms(loaded)
    delta_chgcar = Chgcar(base.structure, {"total": delta})
    z_profile = build_z_profile(delta_chgcar)
    paths = OutputPaths(
        plane_csv=outdir / PLANE_CSV,
        z_profile_csv=outdir / Z_PROFILE_CSV,
        dipole_json=outdir / DIPOLE_JSON,
        plane_png=outdir / PLANE_PNG,
        slices_png=outdir / SLICES_PNG if args.slices else None,
        isosurface_png=outdir / ISOSURFACE_PNG,
        delta_chgcar=outdir / DELTA_CHGCAR if args.write_delta_chgcar else None,
    )

    write_legacy_plane_csv(paths.plane_csv, z_profile)
    write_z_profile_csv(paths.z_profile_csv, z_profile)
    paths.dipole_json.write_text(json.dumps(build_dipole_summary(z_profile), indent=2), encoding="utf-8")
    write_side_profile_plot(paths.plane_png, delta_chgcar, str(args.title))
    if paths.slices_png is not None:
        write_slice_plots(paths.slices_png, delta_chgcar, str(args.title))
    write_lobe_isosurface(paths.isosurface_png, delta_chgcar, str(args.title))
    if paths.delta_chgcar is not None:
        delta_chgcar.write_file(paths.delta_chgcar)

    summary = build_summary(
        loaded=loaded,
        comparison=str(args.comparison),
        delta=delta,
        paths=paths,
    )
    summary_path = outdir / "charge_flow_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    report_path = outdir / REPORT_MD
    report_path.write_text(build_report(summary), encoding="utf-8")
    print(json.dumps({"summary": str(summary_path), "report": str(report_path)}, indent=2))


def parse_term(raw: str) -> Term:
    label_text, sep, rest = raw.partition("=")
    if not sep:
        raise ChargeFlowError(f"Term must be label=coefficient:path, got {raw!r}")
    coefficient_text, sep, path_text = rest.partition(":")
    if not sep:
        raise ChargeFlowError(f"Term must include coefficient:path, got {raw!r}")
    try:
        coefficient = float(coefficient_text)
    except ValueError as exc:
        raise ChargeFlowError(f"Invalid coefficient in term {raw!r}") from exc
    label = label_text.strip()
    if not label:
        raise ChargeFlowError(f"Term label cannot be empty: {raw!r}")
    return Term(label=label, coefficient=coefficient, path=Path(path_text).expanduser())


def load_chgcar(path: Path) -> Chgcar:
    if not path.exists():
        raise ChargeFlowError(f"CHGCAR path does not exist: {path}")
    return Chgcar.from_file(str(path))


def validate_compatible_grids(loaded: list[LoadedTerm], lattice_atol: float) -> None:
    if not loaded:
        raise ChargeFlowError("At least one term is required.")
    ref = loaded[0].chgcar
    ref_shape = total_grid(ref).shape
    ref_lattice = np.asarray(ref.structure.lattice.matrix, dtype=float)
    for item in loaded[1:]:
        if total_grid(item.chgcar).shape != ref_shape:
            raise ChargeFlowError(f"Grid shape mismatch for {item.term.label}: {total_grid(item.chgcar).shape} != {ref_shape}")
        lattice = np.asarray(item.chgcar.structure.lattice.matrix, dtype=float)
        if not np.allclose(lattice, ref_lattice, atol=lattice_atol, rtol=0.0):
            raise ChargeFlowError(f"Lattice mismatch for {item.term.label}; CHGCAR subtraction is not meaningful.")


def total_grid(chgcar: Chgcar) -> NDArray[np.float64]:
    if "total" not in chgcar.data:
        raise ChargeFlowError("CHGCAR lacks a 'total' density dataset.")
    return np.asarray(chgcar.data["total"], dtype=np.float64)


def combine_terms(loaded: list[LoadedTerm]) -> NDArray[np.float64]:
    shape = total_grid(loaded[0].chgcar).shape
    delta = np.zeros(shape, dtype=np.float64)
    for item in loaded:
        delta = delta + item.term.coefficient * total_grid(item.chgcar)
    return delta


def build_summary(
    loaded: list[LoadedTerm],
    comparison: str,
    delta: NDArray[np.float64],
    paths: OutputPaths,
) -> dict[str, object]:
    base = loaded[0].chgcar
    volume = float(base.structure.lattice.volume)
    grid_points = int(delta.size)
    positive = np.clip(delta, 0.0, None)
    negative = np.clip(delta, None, 0.0)
    voxel_factor = volume / float(grid_points)
    raw_chgcar_factor = 1.0 / float(grid_points)
    return {
        "schema_version": 2,
        "comparison": comparison,
        "backend": "pymatgen.io.vasp.outputs.Chgcar",
        "density_convention": {
            "raw_chgcar_residual_e": "sum(raw_delta) / N_grid",
            "normalized_delta_n_e_per_A3": "raw_delta / cell_volume",
            "lateral_integral_delta_lambda_e_per_A": "raw_plane_average / c_length",
        },
        "terms": [{"label": item.term.label, "coefficient": item.term.coefficient, "path": str(item.term.path)} for item in loaded],
        "grid_shape": list(delta.shape),
        "cell_volume_ang3": volume,
        "raw_grid_sum": float(delta.sum()),
        "integral_assuming_vasp_chgcar_raw_e": float(delta.sum() * raw_chgcar_factor),
        "positive_integral_assuming_vasp_chgcar_raw_e": float(positive.sum() * raw_chgcar_factor),
        "negative_integral_assuming_vasp_chgcar_raw_e": float(negative.sum() * raw_chgcar_factor),
        "half_abs_integral_assuming_vasp_chgcar_raw_e": float(0.5 * np.abs(delta).sum() * raw_chgcar_factor),
        "integral_assuming_density_grid_e": float(delta.sum() * voxel_factor),
        "positive_integral_assuming_density_grid_e": float(positive.sum() * voxel_factor),
        "negative_integral_assuming_density_grid_e": float(negative.sum() * voxel_factor),
        "half_abs_integral_assuming_density_grid_e": float(0.5 * np.abs(delta).sum() * voxel_factor),
        "min_delta": float(delta.min()),
        "max_delta": float(delta.max()),
        "extrema": extrema_summary(delta, base.structure),
        "warnings": warnings_for_summary(loaded, delta),
        "outputs": {
            "plane_average_csv": str(paths.plane_csv),
            "z_profile_csv": str(paths.z_profile_csv),
            "dipole_summary_json": str(paths.dipole_json),
            "plane_average_png": str(paths.plane_png),
            "delta_density_slices_png": str(paths.slices_png) if paths.slices_png else None,
            "delta_density_isosurface_png": str(paths.isosurface_png),
            "delta_chgcar": str(paths.delta_chgcar) if paths.delta_chgcar else None,
        },
    }


def extrema_summary(delta: NDArray[np.float64], structure: Structure) -> dict[str, object]:
    min_index = np.unravel_index(int(np.argmin(delta)), delta.shape)
    max_index = np.unravel_index(int(np.argmax(delta)), delta.shape)
    return {
        "min_grid_index": [int(value) for value in min_index],
        "min_cartesian_ang": cartesian_for_index(min_index, delta.shape, structure),
        "max_grid_index": [int(value) for value in max_index],
        "max_cartesian_ang": cartesian_for_index(max_index, delta.shape, structure),
    }


def cartesian_for_index(index: tuple[int, int, int], shape: tuple[int, int, int], structure: Structure) -> list[float]:
    frac = [(float(i) + 0.5) / float(n) for i, n in zip(index, shape)]
    return [float(value) for value in structure.lattice.get_cartesian_coords(frac)]


def warnings_for_summary(loaded: list[LoadedTerm], delta: NDArray[np.float64]) -> list[str]:
    warnings: list[str] = []
    if any("diff" in item.chgcar.data for item in loaded):
        warnings.append("Spin-polarized CHGCAR detected; this script analyzes total density only.")
    if abs(float(delta.sum())) > 1e-3 * max(float(np.abs(delta).sum()), 1.0):
        warnings.append("Delta grid has a non-negligible raw residual; check formula, charge state, and references.")
    if len(loaded) < 2:
        warnings.append("Only one term was supplied; this is not a charge-density difference.")
    return warnings


def build_report(summary: dict[str, object]) -> str:
    return "\n".join([
        "# Charge-Flow Analysis Report",
        "",
        f"Comparison: `{summary['comparison']}`",
        f"Backend: `{summary['backend']}`",
        "",
        "## Formula",
        "",
        json.dumps(summary["terms"], indent=2),
        "",
        "Positive delta density means electron accumulation relative to the stated references.",
        "Negative delta density means electron depletion relative to the stated references.",
        "Normalized profile outputs use Delta n = raw_delta / cell_volume and Delta lambda = raw_plane_average / c_length.",
        "",
        "## Integral Checks",
        "",
        f"- raw grid sum: `{summary['raw_grid_sum']}`",
        f"- integral assuming raw VASP CHGCAR grid values: `{summary['integral_assuming_vasp_chgcar_raw_e']}` e",
        f"- positive raw-CHGCAR lobe integral: `{summary['positive_integral_assuming_vasp_chgcar_raw_e']}` e",
        f"- negative raw-CHGCAR lobe integral: `{summary['negative_integral_assuming_vasp_chgcar_raw_e']}` e",
        f"- half-absolute raw-CHGCAR redistribution: `{summary['half_abs_integral_assuming_vasp_chgcar_raw_e']}` e",
        f"- diagnostic if input grid were already e/A^3 density: `{summary['integral_assuming_density_grid_e']}` e",
        "",
        "## Profile Outputs",
        "",
        f"- z profile CSV: `{summary['outputs']['z_profile_csv']}`",
        f"- dipole summary JSON: `{summary['outputs']['dipole_summary_json']}`",
        "",
        "## Allowed Claim",
        "",
        "Use this result to support bounded statements about electron accumulation, depletion, and polarization at controlled catalyst sites.",
        "",
        "## Do Not Claim",
        "",
        "Do not claim formal oxidation states, exact atom-to-atom electron transfer, activity, selectivity, or donation/back-donation decomposition from this result alone.",
    ]) + "\n"
