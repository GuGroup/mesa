#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import re
from typing import Any

import numpy as np


ENERGY_KEYS = ("energy", "free_energy", "E", "Energy", "dft_energy", "potential_energy")

# aseview overlay render style for visual review (bonds on, Rowan style, compact
# atoms, perspective camera). Kept here so the look is consistent across runs.
VISUAL_STYLE = {
    "colorBy": "Atom",
    "showBond": True,
    "style": "rowan",
    "atomSize": 0.7,
    "viewMode": "Perspective",
    "showCell": True,
    "viewFit": 0.64,
    "backgroundColor": "#64748b",
    "cellColor": "#f1f5f9",
}
SEVERITY = {"pass": 0, "warn": 1, "fail": 2}


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return str(value)


def finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    if not math.isfinite(out):
        return None
    return out


def discover_inputs(path: Path) -> dict[str, Path | None]:
    if path.is_file():
        name = path.name.lower()
        if name == "oszicar":
            return {"trajectory": None, "oszicar": path}
        return {"trajectory": path, "oszicar": path.with_name("OSZICAR") if path.with_name("OSZICAR").exists() else None}

    priority = [
        "relax.traj",
        "trajectory.traj",
        "opt.traj",
        "vasprun.xml",
        "vasprun.xml.gz",
        "OUTCAR",
        "XDATCAR",
    ]
    for name in priority:
        candidate = path / name
        if candidate.exists():
            return {"trajectory": candidate, "oszicar": path / "OSZICAR" if (path / "OSZICAR").exists() else None}
    for pattern in ("*.traj", "*.extxyz", "*.xyz", "*.vasp"):
        matches = sorted(path.glob(pattern))
        if matches:
            return {"trajectory": matches[0], "oszicar": path / "OSZICAR" if (path / "OSZICAR").exists() else None}
    oszicar = path / "OSZICAR"
    return {"trajectory": None, "oszicar": oszicar if oszicar.exists() else None}


def read_trajectory(path: Path | None) -> list[Any]:
    if path is None:
        return []
    from ase.io import read

    try:
        frames = read(str(path), index=":")
    except Exception:
        frames = read(str(path), index="-1")
    if isinstance(frames, list):
        return frames
    return [frames]


def parse_oszicar(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    pattern = re.compile(r"F=\s*([-+0-9.Ee]+)")
    e0_pattern = re.compile(r"E0=\s*([-+0-9.Ee]+)")
    for line in path.read_text(errors="ignore").splitlines():
        if "F=" not in line and "E0=" not in line:
            continue
        energy = None
        match = pattern.search(line)
        if match:
            energy = finite_float(match.group(1))
        if energy is None:
            match = e0_pattern.search(line)
            if match:
                energy = finite_float(match.group(1))
        if energy is not None:
            rows.append({"step": len(rows), "energy": energy, "source": "OSZICAR"})
    return rows


def get_energy(atoms: Any) -> float | None:
    for key in ENERGY_KEYS:
        if key in getattr(atoms, "info", {}):
            value = finite_float(atoms.info.get(key))
            if value is not None:
                return value
    try:
        return finite_float(atoms.get_potential_energy())
    except Exception:
        return None


def get_fmax(atoms: Any) -> float | None:
    try:
        forces = atoms.get_forces()
    except Exception:
        forces = atoms.arrays.get("forces") if hasattr(atoms, "arrays") else None
    if forces is None:
        return None
    forces = np.asarray(forces, dtype=float)
    if forces.ndim != 2 or forces.shape[1] != 3 or not np.isfinite(forces).all():
        return None
    if len(forces) == 0:
        return None
    return float(np.linalg.norm(forces, axis=1).max())


def apply_mic(delta: np.ndarray, cell: Any, pbc: Any) -> np.ndarray:
    """Wrap displacement vectors with the minimum-image convention.

    An atom that crosses a periodic boundary otherwise looks like a full-cell
    jump and produces false RMSD/displacement spikes. Only periodic directions
    are wrapped; non-periodic ones (e.g. the slab normal) are left untouched."""
    if cell is None or pbc is None:
        return delta
    cell = np.asarray(cell, dtype=float)
    flags = [bool(x) for x in pbc]
    if cell.shape != (3, 3) or not any(flags) or abs(np.linalg.det(cell)) < 1e-8:
        return delta
    frac = delta @ np.linalg.inv(cell)
    for axis in range(3):
        if flags[axis]:
            frac[:, axis] -= np.round(frac[:, axis])
    return frac @ cell


def fixed_indices(atoms: Any) -> list[int]:
    indices: list[int] = []
    for constraint in getattr(atoms, "constraints", []):
        value = getattr(constraint, "index", None)
        if value is None:
            continue
        try:
            indices.extend(int(i) for i in np.asarray(value).ravel())
        except Exception:
            continue
    return sorted(set(i for i in indices if 0 <= i < len(atoms)))


def bottom_indices(atoms: Any, fraction: float) -> list[int]:
    positions = np.asarray(atoms.positions, dtype=float)
    if len(positions) == 0:
        return []
    z = positions[:, 2]
    zmin = float(z.min())
    zmax = float(z.max())
    if zmax <= zmin:
        return list(range(len(atoms)))
    cutoff = zmin + max(0.01, min(1.0, fraction)) * (zmax - zmin)
    out = [int(i) for i, value in enumerate(z) if value <= cutoff]
    return out if len(out) >= min(3, len(atoms)) else list(range(len(atoms)))


def choose_anchor(atoms: Any, mode: str, bottom_fraction: float) -> tuple[str, list[int]]:
    if mode == "none":
        return "none", []
    if mode == "all":
        return "all", list(range(len(atoms)))
    if mode == "fixed":
        return "fixed", fixed_indices(atoms)
    if mode == "bottom":
        return "bottom", bottom_indices(atoms, bottom_fraction)
    fixed = fixed_indices(atoms)
    if fixed:
        return "fixed", fixed
    pbc = [bool(x) for x in getattr(atoms, "pbc", [False, False, False])]
    if len(pbc) >= 2 and pbc[0] and pbc[1]:
        return "bottom", bottom_indices(atoms, bottom_fraction)
    return "all", list(range(len(atoms)))


def kabsch_align(mobile: np.ndarray, target: np.ndarray, anchor: list[int]) -> np.ndarray:
    if not anchor:
        return mobile.copy()
    mob_anchor = mobile[anchor]
    tgt_anchor = target[anchor]
    mob_center = mob_anchor.mean(axis=0)
    tgt_center = tgt_anchor.mean(axis=0)
    mob = mobile - mob_center
    tgt = target - tgt_center
    cov = mob[anchor].T @ tgt[anchor]
    try:
        u, _, vt = np.linalg.svd(cov)
        d = np.sign(np.linalg.det(u @ vt))
        rot = u @ np.diag([1.0, 1.0, d]) @ vt
        return mob @ rot + tgt_center
    except Exception:
        return mobile - mob_center + tgt_center


def displacement_metrics(
    frame: Any,
    reference: Any,
    previous: Any | None,
    anchor: list[int],
) -> dict[str, float | None]:
    if len(frame) != len(reference):
        return {
            "rmsd_to_initial": None,
            "rmsd_step": None,
            "max_disp_to_initial": None,
            "max_disp_step": None,
        }
    pos = np.asarray(frame.positions, dtype=float)
    ref = np.asarray(reference.positions, dtype=float)
    cell = reference.cell.array if hasattr(reference, "cell") else None
    pbc = getattr(reference, "pbc", None)
    aligned = kabsch_align(pos, ref, anchor)
    delta = apply_mic(aligned - ref, cell, pbc)
    out: dict[str, float | None] = {
        "rmsd_to_initial": float(np.sqrt(np.mean(np.sum(delta * delta, axis=1)))),
        "max_disp_to_initial": float(np.linalg.norm(delta, axis=1).max()) if len(delta) else 0.0,
        "rmsd_step": None,
        "max_disp_step": None,
    }
    if previous is not None and len(previous) == len(frame):
        prev = np.asarray(previous.positions, dtype=float)
        prev_cell = previous.cell.array if hasattr(previous, "cell") else None
        prev_pbc = getattr(previous, "pbc", None)
        aligned_prev = kabsch_align(pos, prev, anchor)
        step_delta = apply_mic(aligned_prev - prev, prev_cell, prev_pbc)
        out["rmsd_step"] = float(np.sqrt(np.mean(np.sum(step_delta * step_delta, axis=1))))
        out["max_disp_step"] = float(np.linalg.norm(step_delta, axis=1).max()) if len(step_delta) else 0.0
    return out


def local_minima(energies: list[float | None]) -> list[int]:
    values = [e if e is not None and math.isfinite(e) else None for e in energies]
    out: list[int] = []
    for i in range(1, len(values) - 1):
        left, mid, right = values[i - 1], values[i], values[i + 1]
        if left is None or mid is None or right is None:
            continue
        if mid <= left and mid <= right:
            out.append(i)
    if values and values[-1] is not None:
        out.append(len(values) - 1)
    return sorted(set(out))


def significant_minima(metrics: list[dict[str, Any]], *, energy_prominence: float, rmsd_threshold: float) -> list[int]:
    minima = local_minima([row.get("energy") for row in metrics])
    significant: list[int] = []
    for index in minima:
        if not significant:
            significant.append(index)
            continue
        prev = significant[-1]
        e1 = metrics[prev].get("energy")
        e2 = metrics[index].get("energy")
        r1 = metrics[prev].get("rmsd_to_initial")
        r2 = metrics[index].get("rmsd_to_initial")
        if e1 is None or e2 is None:
            continue
        rmsd_sep = abs((r2 or 0.0) - (r1 or 0.0))
        between = [row.get("energy") for row in metrics[prev:index + 1] if row.get("energy") is not None]
        barrier = max(between) - min(e1, e2) if between else 0.0
        if barrier >= energy_prominence and rmsd_sep >= rmsd_threshold:
            significant.append(index)
    return significant


def build_metrics(frames: list[Any], oszicar_rows: list[dict[str, Any]], anchor_mode: str, bottom_fraction: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if frames:
        anchor_source, anchor = choose_anchor(frames[0], anchor_mode, bottom_fraction)
    else:
        anchor_source, anchor = "none", []

    metrics: list[dict[str, Any]] = []
    for index, atoms in enumerate(frames):
        disp = displacement_metrics(atoms, frames[0], frames[index - 1] if index else None, anchor)
        metrics.append({
            "step": index,
            "frame_index": index,
            "energy": get_energy(atoms),
            "fmax": get_fmax(atoms),
            **disp,
            "source": "trajectory",
        })

    if not metrics and oszicar_rows:
        metrics = [
            {
                "step": row["step"],
                "frame_index": None,
                "energy": row["energy"],
                "fmax": None,
                "rmsd_to_initial": None,
                "rmsd_step": None,
                "max_disp_to_initial": None,
                "max_disp_step": None,
                "source": row["source"],
            }
            for row in oszicar_rows
        ]
    elif metrics and oszicar_rows and all(row.get("energy") is None for row in metrics):
        for metric, osz in zip(metrics, oszicar_rows):
            metric["energy"] = osz["energy"]
            metric["energy_source"] = "OSZICAR"

    return metrics, {"anchor_source": anchor_source, "anchor_indices": anchor}


def finite_series(metrics: list[dict[str, Any]], key: str) -> list[float | None]:
    out: list[float | None] = []
    for row in metrics:
        value = row.get(key)
        if value is None:
            out.append(None)
            continue
        value = finite_float(value)
        out.append(value)
    return out


def bond_set(atoms: Any, scale: float) -> set[frozenset[int]]:
    """Covalent-radius bond graph (PBC-aware) as a set of {i, j} pairs."""
    from ase.neighborlist import natural_cutoffs, neighbor_list

    cutoffs = natural_cutoffs(atoms, mult=scale)
    first, second = neighbor_list("ij", atoms, cutoffs)
    return {frozenset((int(a), int(b))) for a, b in zip(first, second) if a != b}


def normal_projection(atoms: Any) -> np.ndarray:
    """Project positions onto the surface normal (a × b); fall back to z."""
    cell = atoms.cell.array if hasattr(atoms, "cell") else None
    pos = np.asarray(atoms.positions, dtype=float)
    if cell is None:
        return pos[:, 2]
    normal = np.cross(cell[0], cell[1])
    norm = float(np.linalg.norm(normal))
    if norm == 0.0:
        return pos[:, 2]
    return pos @ (normal / norm)


def detect_anomalies(frames: list[Any], args: argparse.Namespace) -> dict[str, Any]:
    """Flag 'moved to a weird place' signals: dissociation, new bonds, lift-off.

    These are intent-agnostic. The workflow decides whether a flagged change is
    acceptable (e.g. an intended dissociative adsorption) or a failure."""
    result: dict[str, Any] = {
        "comparable": False,
        "connectivity_changed": False,
        "dissociation_suspected": False,
        "new_bond_suspected": False,
        "n_bonds_removed": 0,
        "n_bonds_added": 0,
        "desorption_suspected": False,
        "max_upward_shift": None,
        "slab_like": False,
    }
    if len(frames) < 2:
        return result
    first, last = frames[0], frames[-1]
    if len(first) != len(last):
        return result
    result["comparable"] = True

    try:
        b0 = bond_set(first, args.bond_scale)
        b1 = bond_set(last, args.bond_scale)
        removed = b0 - b1
        added = b1 - b0
        result["n_bonds_removed"] = len(removed)
        result["n_bonds_added"] = len(added)
        result["dissociation_suspected"] = bool(removed)
        result["new_bond_suspected"] = bool(added)
        result["connectivity_changed"] = bool(removed or added)
    except Exception as exc:  # neighbor list needs a cell; skip gracefully
        result["bond_error"] = str(exc)

    pbc = [bool(x) for x in getattr(first, "pbc", [False, False, False])]
    slab_like = len(pbc) >= 2 and pbc[0] and pbc[1]
    result["slab_like"] = slab_like
    if slab_like:
        shift = normal_projection(last) - normal_projection(first)
        max_up = float(np.max(shift)) if len(shift) else 0.0
        result["max_upward_shift"] = max_up
        result["desorption_suspected"] = max_up > args.desorption_z

    return result


def parse_run_parameters(input_path: Path, trajectory: Path | None) -> dict[str, Any]:
    """Best-effort EDIFFG (force criterion) and NSW from VASP inputs/outputs."""
    search_dir = input_path if input_path.is_dir() else input_path.parent
    out: dict[str, Any] = {"ediffg": None, "nsw": None, "force_threshold": None, "source": None}

    def record(ediffg: float | None, nsw: int | None, source: str) -> bool:
        if ediffg is None and nsw is None:
            return False
        out["ediffg"] = ediffg
        out["nsw"] = nsw
        out["force_threshold"] = abs(ediffg) if (ediffg is not None and ediffg < 0) else None
        out["source"] = source
        return True

    # vasprun.xml: <i name="EDIFFG">-5.00e-02</i>, <i type="int" name="NSW">300</i>
    for name in ("vasprun.xml",):
        path = search_dir / name
        if path.exists():
            text = path.read_text(errors="ignore")
            ediffg = re.search(r'name="EDIFFG"[^>]*>\s*([-+0-9.Ee]+)', text)
            nsw = re.search(r'name="NSW"[^>]*>\s*([0-9]+)', text)
            if record(
                finite_float(ediffg.group(1)) if ediffg else None,
                int(nsw.group(1)) if nsw else None,
                name,
            ):
                return out

    for name in ("INCAR", "OUTCAR"):
        path = search_dir / name
        if path.exists():
            text = path.read_text(errors="ignore")
            ediffg = re.search(r"EDIFFG\s*=\s*([-+0-9.Ee]+)", text)
            nsw = re.search(r"NSW\s*=\s*([0-9]+)", text)
            if record(
                finite_float(ediffg.group(1)) if ediffg else None,
                int(nsw.group(1)) if nsw else None,
                name,
            ):
                return out
    return out


def build_verdict(
    diagnosis: dict[str, Any],
    anomalies: dict[str, Any],
    *,
    fmax_threshold: float | None,
    fmax_threshold_source: str,
    final_fmax: float | None,
    nsw: int | None,
    n_ionic_steps: int,
) -> dict[str, Any]:
    """Single automated pass/warn/fail verdict for unattended gating."""
    fail: list[str] = []
    warn: list[str] = []

    converged: bool | None = None
    if final_fmax is not None and fmax_threshold is not None:
        converged = final_fmax <= fmax_threshold
        if not converged:
            fail.append(
                f"final fmax {final_fmax:.3f} > {fmax_threshold:.3f} eV/Å "
                f"({fmax_threshold_source}) — not converged"
            )
    else:
        warn.append("convergence not confirmed (no forces and/or no force criterion available)")

    nsw_reached = bool(nsw is not None and n_ionic_steps >= nsw)
    if nsw_reached and converged is not True:
        fail.append(f"reached NSW step limit ({nsw}) without confirmed force convergence")

    if diagnosis.get("final_energy") is None:
        warn.append("no final energy available")
    if not diagnosis.get("energy_monotonic_decrease", True):
        warn.append("energy is not monotonically decreasing")
    if len(diagnosis.get("significant_minima", [])) >= 2:
        warn.append("multiple significant minima — endpoint may be path-dependent")

    if anomalies.get("dissociation_suspected"):
        warn.append(f"{anomalies['n_bonds_removed']} bond(s) broke vs initial (possible dissociation)")
    if anomalies.get("new_bond_suspected"):
        warn.append(f"{anomalies['n_bonds_added']} new bond(s) vs initial")
    if anomalies.get("desorption_suspected"):
        warn.append(
            f"max upward shift {anomalies['max_upward_shift']:.2f} Å — possible desorption/lift-off"
        )

    verdict = "fail" if fail else ("warn" if warn else "pass")
    return {
        "verdict": verdict,
        "converged": converged,
        "nsw_reached": nsw_reached,
        "fmax_threshold": fmax_threshold,
        "fmax_threshold_source": fmax_threshold_source,
        "fail_reasons": fail,
        "warn_reasons": warn,
    }


def diagnose(metrics: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    warnings: list[str] = []
    energies = finite_series(metrics, "energy")
    fmax = finite_series(metrics, "fmax")
    rmsd_step = finite_series(metrics, "rmsd_step")

    energy_increases: list[dict[str, Any]] = []
    for i in range(1, len(energies)):
        if energies[i] is None or energies[i - 1] is None:
            continue
        delta = float(energies[i] - energies[i - 1])
        if delta > args.energy_increase_threshold:
            energy_increases.append({"step": i, "delta_e": delta})
    if energy_increases:
        warnings.append(f"{len(energy_increases)} energy increases exceed {args.energy_increase_threshold:g} eV.")

    force_spikes: list[dict[str, Any]] = []
    for i in range(1, len(fmax)):
        if fmax[i] is None or fmax[i - 1] is None:
            continue
        delta = float(fmax[i] - fmax[i - 1])
        if delta > args.force_jump_threshold:
            force_spikes.append({"step": i, "delta_fmax": delta})
    if force_spikes:
        warnings.append(f"{len(force_spikes)} max-force jumps exceed {args.force_jump_threshold:g} eV/Å.")

    rmsd_jumps: list[dict[str, Any]] = []
    for i, value in enumerate(rmsd_step):
        if value is not None and value > args.rmsd_jump_threshold:
            rmsd_jumps.append({"step": i, "rmsd_step": float(value)})
    if rmsd_jumps:
        warnings.append(f"{len(rmsd_jumps)} RMSD jumps exceed {args.rmsd_jump_threshold:g} Å.")

    minima = local_minima(energies)
    multi_minima = significant_minima(
        metrics,
        energy_prominence=args.minima_energy_prominence,
        rmsd_threshold=args.minima_rmsd_threshold,
    )
    if len(multi_minima) >= 2:
        warnings.append(f"{len(multi_minima)} significant minima candidates detected.")

    final_fmax = next((value for value in reversed(fmax) if value is not None), None)
    if final_fmax is not None and final_fmax > args.high_final_fmax:
        warnings.append(f"Final Fmax {final_fmax:.3f} eV/Å exceeds {args.high_final_fmax:g} eV/Å.")

    return {
        "warnings": warnings,
        "energy_monotonic_decrease": not energy_increases,
        "energy_increases": energy_increases,
        "force_spikes": force_spikes,
        "rmsd_jumps": rmsd_jumps,
        "local_minima": minima,
        "significant_minima": multi_minima,
        "final_energy": next((value for value in reversed(energies) if value is not None), None),
        "final_fmax": final_fmax,
    }


def select_frames(metrics: list[dict[str, Any]], frame_count: int, diagnosis: dict[str, Any], sample_count: int, top_events: int) -> list[int]:
    if frame_count <= 0:
        return []
    selected = {0, frame_count - 1}
    for idx in np.linspace(0, frame_count - 1, num=min(sample_count, frame_count), dtype=int):
        selected.add(int(idx))
    for key, step_key in (("energy_increases", "step"), ("force_spikes", "step"), ("rmsd_jumps", "step")):
        for event in diagnosis.get(key, [])[:top_events]:
            step = event.get(step_key)
            if isinstance(step, int):
                selected.update(i for i in (step - 1, step, step + 1) if 0 <= i < frame_count)
    for idx in diagnosis.get("local_minima", [])[:top_events]:
        if isinstance(idx, int) and 0 <= idx < frame_count:
            selected.add(idx)
    for idx in diagnosis.get("significant_minima", []):
        if isinstance(idx, int) and 0 <= idx < frame_count:
            selected.add(idx)
    return sorted(selected)


def write_metrics_csv(path: Path, metrics: list[dict[str, Any]]) -> None:
    keys = [
        "step",
        "frame_index",
        "energy",
        "fmax",
        "rmsd_to_initial",
        "rmsd_step",
        "max_disp_to_initial",
        "max_disp_step",
        "source",
        "energy_source",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in metrics:
            writer.writerow({key: row.get(key) for key in keys})


def write_selected_frames(path: Path, frames: list[Any], selected: list[int], metrics: list[dict[str, Any]], anchor: list[int]) -> None:
    if not frames or not selected:
        return
    from ase.io import write

    out = []
    reference_positions = np.asarray(frames[0].positions, dtype=float)
    for sample_order, index in enumerate(selected):
        atoms = frames[index].copy()
        row = metrics[index]
        atoms.info["analysis_sample_order"] = sample_order
        atoms.info["analysis_frame_index"] = index
        for key in ("energy", "fmax", "rmsd_to_initial", "rmsd_step", "max_disp_to_initial", "max_disp_step"):
            value = row.get(key)
            if value is not None:
                atoms.info[f"analysis_{key}"] = float(value)
        if len(atoms) == len(frames[0]):
            aligned = kabsch_align(np.asarray(atoms.positions, dtype=float), reference_positions, anchor)
            atoms.arrays["analysis_disp_to_initial"] = np.linalg.norm(aligned - reference_positions, axis=1)
        if index > 0 and len(atoms) == len(frames[index - 1]):
            previous_positions = np.asarray(frames[index - 1].positions, dtype=float)
            aligned_step = kabsch_align(np.asarray(atoms.positions, dtype=float), previous_positions, anchor)
            atoms.arrays["analysis_disp_step"] = np.linalg.norm(aligned_step - previous_positions, axis=1)
        out.append(atoms)
    write(str(path), out, format="extxyz")


def write_aseview_htmls(
    trajectory_html: Path,
    overlay_html: Path,
    frames: list[Any],
    selected_frames: Path | None,
    colormap: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "trajectory_html_written": False,
        "overlay_html_written": False,
        "error": None,
    }
    try:
        from ase.io import read
        from aseview import MolecularViewer
        from aseview import OverlayViewer
    except Exception as exc:
        result["error"] = f"aseview import failed: {exc}"
        return result
    try:
        if frames:
            MolecularViewer(frames).save_html(str(trajectory_html))
            result["trajectory_html_written"] = True
        if selected_frames is not None:
            sampled = read(str(selected_frames), index=":")
            OverlayViewer(sampled, colorBy="Colormap", colormap=colormap).save_html(str(overlay_html))
            result["overlay_html_written"] = True
    except Exception as exc:
        result["error"] = f"aseview HTML export failed: {exc}"
    return result


def uniform_overlay_indices(n_frames: int, max_frames: int) -> list[int]:
    """Uniformly sample up to max_frames indices, always keeping first and last."""
    if n_frames <= 0:
        return []
    if n_frames <= max_frames:
        return list(range(n_frames))
    picks = sorted({int(round(x)) for x in np.linspace(0, n_frames - 1, max_frames)})
    picks = [i for i in picks if 0 <= i < n_frames]
    picks[0], picks[-1] = 0, n_frames - 1
    return sorted(set(picks))


def unwrap_selected(frames: list[Any], indices: list[int]) -> list[Any]:
    """Build MIC-unwrapped, non-rotated coordinates across the selected frames.

    Cumulative minimum-image unwrapping keeps an atom that crosses a periodic
    boundary visually continuous (so 'walked off the slab' reads correctly) while
    leaving the periodic cell unrotated."""
    from ase.geometry import find_mic

    selected = [frames[i] for i in indices]
    if not selected:
        return []
    out = [selected[0].copy()]
    continuous = np.asarray(selected[0].positions, dtype=float).copy()
    for previous, current in zip(selected, selected[1:]):
        delta = np.asarray(current.positions, dtype=float) - np.asarray(previous.positions, dtype=float)
        cell = current.cell.array if hasattr(current, "cell") else None
        pbc = [bool(x) for x in getattr(current, "pbc", [False, False, False])]
        if cell is not None and len(current) == len(previous) and any(pbc) and abs(np.linalg.det(cell)) > 1e-8:
            delta, _ = find_mic(delta, cell=cell, pbc=pbc)
        continuous = continuous + delta
        frame = current.copy()
        frame.positions[:] = continuous
        out.append(frame)
    return out


def camera_views(atoms: Any) -> dict[str, tuple[list[float], list[float]]]:
    """Top / Side-a / Side-b perspective directions from the cell basis.

    Falls back to fixed Cartesian axes for non-periodic / degenerate cells."""
    cell = atoms.cell.array if hasattr(atoms, "cell") else None
    if cell is not None and abs(np.linalg.det(cell)) > 1e-8:
        a = cell[0] / np.linalg.norm(cell[0])
        b = cell[1] / np.linalg.norm(cell[1])
        normal = np.cross(cell[0], cell[1])
        normal = normal / np.linalg.norm(normal)
    else:
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0])
        normal = np.array([0.0, 0.0, 1.0])
    return {
        "top": ((normal + 0.12 * a - 0.08 * b).tolist(), b.tolist()),
        "side_a": ((a + 0.12 * b + 0.08 * normal).tolist(), normal.tolist()),
        "side_b": ((b - 0.12 * a + 0.08 * normal).tolist(), normal.tolist()),
    }


def make_overlay_viewer(frames: list[Any], **kwargs: Any):
    """OverlayViewer with every sampled frame visible.

    aseview >= 0.0.12 exposes a native ``visibleIndices`` setting; make all
    sampled frames visible so the overlay shows the full trajectory, not just the
    first few. Falls back to a plain OverlayViewer on older aseview."""
    from aseview import OverlayViewer

    try:
        return OverlayViewer(frames, visibleIndices=list(range(len(frames))), **kwargs)
    except TypeError:
        return OverlayViewer(frames, **kwargs)


def render_overlay_pngs(
    frames: list[Any],
    indices: list[int],
    outdir: Path,
    prefix: str,
    *,
    width: int,
    height: int,
    chrome_path: str | None,
) -> dict[str, Any]:
    """Render Top/Side-a/Side-b overlay PNGs for the selected frame indices."""
    result: dict[str, Any] = {"indices": indices, "paths": {}, "error": None}
    selected = unwrap_selected(frames, indices)
    if not selected:
        result["error"] = "no frames to render"
        return result
    views = camera_views(selected[0])
    save_kwargs: dict[str, Any] = {"width": width, "height": height, "transparent": False}
    if chrome_path:
        save_kwargs["browser_executable_path"] = chrome_path
    try:
        for name, (direction, up) in views.items():
            viewer = make_overlay_viewer(selected, viewDirection=direction, viewUp=up, **VISUAL_STYLE)
            path = outdir / f"{prefix}_{name}.png"
            viewer.save_png(str(path), **save_kwargs)
            result["paths"][name] = str(path)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def write_review_markdown(path: Path, summary: dict[str, Any], selected_extxyz: Path | None, colormap: str) -> None:
    convergence = summary.get("convergence", {})
    anomalies = summary.get("anomalies", {})
    visual = summary.get("visual_validation", {})
    lines = [
        "# Calculation Result Visual Review",
        "",
        f"- **Overall verdict: {summary.get('verdict', 'unknown').upper()}** "
        f"(deterministic: {summary.get('deterministic_verdict', '?')}, "
        f"visual: {visual.get('status', '?')})",
        f"- Converged: {convergence.get('converged')} "
        f"(fmax {summary['diagnosis'].get('final_fmax')} vs "
        f"{convergence.get('fmax_threshold')} eV/Å, {convergence.get('fmax_threshold_source')})",
        f"- NSW reached: {convergence.get('nsw_reached')}",
        f"- Input: `{summary['input']}`",
        f"- Trajectory: `{summary.get('trajectory_input')}`",
        f"- OSZICAR: `{summary.get('oszicar_input')}`",
        f"- Frames: {summary['frame_count']}",
        f"- Energy monotonic decrease: {summary['diagnosis']['energy_monotonic_decrease']}",
        f"- Final energy: {summary['diagnosis'].get('final_energy')}",
        "",
        "## Verdict reasons",
        "",
    ]
    fail_reasons = convergence.get("fail_reasons", [])
    warn_reasons = convergence.get("warn_reasons", [])
    if fail_reasons:
        lines.extend(f"- FAIL: {reason}" for reason in fail_reasons)
    if warn_reasons:
        lines.extend(f"- WARN: {reason}" for reason in warn_reasons)
    if not fail_reasons and not warn_reasons:
        lines.append("- Converged with no anomalies under the selected thresholds.")
    if anomalies.get("comparable"):
        lines.extend([
            "",
            "## Anomaly checks (initial vs final)",
            "",
            f"- bonds removed: {anomalies.get('n_bonds_removed')} / added: {anomalies.get('n_bonds_added')}",
            f"- dissociation suspected: {anomalies.get('dissociation_suspected')}",
            f"- desorption suspected: {anomalies.get('desorption_suspected')} "
            f"(max upward shift {anomalies.get('max_upward_shift')})",
        ])
    lines.extend(["", "## Diagnostic warnings", ""])
    warnings = summary["diagnosis"].get("warnings", [])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- No high-level warnings under the selected thresholds.")
    lines.extend(["", "## Visual check", ""])
    trajectory_html = summary["paths"].get("aseview_trajectory_html")
    overlay_html = summary["paths"].get("aseview_overlay_html")
    if trajectory_html:
        lines.extend([
            f"- Full trajectory viewer: `{Path(trajectory_html).name}`",
        ])
    if overlay_html:
        lines.extend([
            f"- Event-sampled overlay viewer: `{Path(overlay_html).name}`",
        ])
    if trajectory_html or overlay_html:
        lines.append("")
    if selected_extxyz is not None:
        lines.extend([
            "Open the sampled overlay directly with:",
            "",
            "```bash",
            f"aseview {selected_extxyz.name} -v overlay --cmap {colormap} -o aseview_overlay.html",
            "```",
            "",
            "The selected extxyz stores `analysis_disp_to_initial` and `analysis_disp_step` per-atom arrays.",
            "Use aseview's built-in export controls in the viewer for PNG/GIF snapshots when needed.",
            "Inspect sampled frames around RMSD jumps, force spikes, energy increases, and local minima.",
        ])
    else:
        lines.append("No structural trajectory was available; OSZICAR-only analysis cannot support overlay review.")
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze UMA/MLIP or VASP optimization results and prepare visual-review artifacts.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", required=True, help="Result file or directory containing trajectory/log outputs.")
    parser.add_argument("--outdir", default="calculation_result_analysis", help="Output directory.")
    parser.add_argument("--anchor", choices=["auto", "fixed", "bottom", "all", "none"], default="auto", help="Alignment anchor policy for RMSD.")
    parser.add_argument("--bottom-fraction", type=float, default=0.35, help="Bottom z-fraction used for slab alignment when no FixAtoms are present.")
    parser.add_argument("--sample-count", type=int, default=12, help="Uniform samples to include in selected_frames.extxyz.")
    parser.add_argument("--top-events", type=int, default=6, help="Maximum events per signal to include in visual sampling.")
    parser.add_argument("--energy-increase-threshold", type=float, default=0.05, help="Energy increase threshold in eV.")
    parser.add_argument("--force-jump-threshold", type=float, default=2.0, help="Fmax jump threshold in eV/Å.")
    parser.add_argument("--rmsd-jump-threshold", type=float, default=0.35, help="Adjacent-frame RMSD jump threshold in Å.")
    parser.add_argument("--minima-energy-prominence", type=float, default=0.05, help="Energy barrier threshold for significant minima candidates in eV.")
    parser.add_argument("--minima-rmsd-threshold", type=float, default=0.4, help="RMSD separation threshold for significant minima candidates in Å.")
    parser.add_argument("--high-final-fmax", type=float, default=0.08, help="Warn when final Fmax exceeds this eV/Å threshold.")
    parser.add_argument("--fmax-threshold", type=float, default=None, help="Force convergence criterion (eV/Å) for the verdict. Default: |EDIFFG| from VASP outputs when present, else 0.05.")
    parser.add_argument("--nsw", type=int, default=None, help="Max ionic steps for the verdict. Default: NSW from VASP outputs when present.")
    parser.add_argument("--bond-scale", type=float, default=1.2, help="Covalent-radius multiplier for connectivity/dissociation detection.")
    parser.add_argument("--desorption-z", type=float, default=2.5, help="Upward shift along the surface normal (Å) that flags possible desorption/lift-off on slabs.")
    parser.add_argument("--colormap", default="viridis", help="aseview overlay colormap.")
    parser.add_argument("--no-html", action="store_true", help="Do not attempt aseview HTML export.")
    parser.add_argument("--overlay-max-frames", type=int, default=50, help="Max frames uniformly sampled for the overlay PNGs.")
    parser.add_argument("--zoom-frames", default=None, help="Comma-separated frame indices to also render as a zoomed overlay (e.g. '0,12,30').")
    parser.add_argument("--no-visual", action="store_true", help="Skip aseview PNG rendering entirely.")
    parser.add_argument("--chrome-path", default=None, help="Browser executable for aseview PNG export. Default: playwright's bundled chromium.")
    parser.add_argument("--png-width", type=int, default=1600, help="Overlay PNG width.")
    parser.add_argument("--png-height", type=int, default=1100, help="Overlay PNG height.")
    parser.add_argument("--visual-review", default=None, help="Path to a completed visual_review.json to ingest. Default: <outdir>/visual_review.json if present.")
    parser.add_argument("--skip-visual-validation", action="store_true", help="Skip the multimodal visual gate; overall verdict equals the deterministic verdict (PNGs are still rendered).")
    args = parser.parse_args()

    default_fmax_threshold = 0.05

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"Input does not exist: {input_path}")
    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    discovered = discover_inputs(input_path)
    frames = read_trajectory(discovered["trajectory"])
    oszicar_rows = parse_oszicar(discovered["oszicar"])
    metrics, anchor_info = build_metrics(frames, oszicar_rows, args.anchor, args.bottom_fraction)
    if not metrics:
        raise SystemExit("No trajectory frames or OSZICAR energy rows could be read.")

    diagnosis = diagnose(metrics, args)
    selected = select_frames(metrics, len(frames), diagnosis, args.sample_count, args.top_events)

    run_params = parse_run_parameters(input_path, discovered["trajectory"])
    if args.fmax_threshold is not None:
        fmax_threshold, fmax_threshold_source = args.fmax_threshold, "cli --fmax-threshold"
    elif run_params.get("force_threshold") is not None:
        fmax_threshold = run_params["force_threshold"]
        fmax_threshold_source = f"|EDIFFG| from {run_params['source']}"
    else:
        fmax_threshold, fmax_threshold_source = default_fmax_threshold, "default fallback"
    nsw = args.nsw if args.nsw is not None else run_params.get("nsw")
    anomalies = detect_anomalies(frames, args)
    verdict = build_verdict(
        diagnosis,
        anomalies,
        fmax_threshold=fmax_threshold,
        fmax_threshold_source=fmax_threshold_source,
        final_fmax=diagnosis.get("final_fmax"),
        nsw=nsw,
        n_ionic_steps=len(frames),
    )
    deterministic_verdict = verdict["verdict"]

    # --- Visual validation: aseview overlay PNGs + multimodal review gate ---
    visual: dict[str, Any] = {
        "status": "skipped" if args.skip_visual_validation else "pending",
        "overlay": None,
        "zoom": None,
        "request_path": None,
        "review_path": None,
        "review": None,
        "floor_applied": None,
        "error": None,
    }
    if not frames:
        # A relaxation result with no coordinates is a problem, not a bypass.
        visual["status"] = "unavailable"
        visual["error"] = "no structural frames to visualize"
    elif not args.no_visual:
        overlay_indices = uniform_overlay_indices(len(frames), args.overlay_max_frames)
        visual["overlay"] = render_overlay_pngs(
            frames, overlay_indices, outdir, "overlay",
            width=args.png_width, height=args.png_height, chrome_path=args.chrome_path,
        )
        if args.zoom_frames:
            zoom_idx = sorted({
                int(tok) for tok in args.zoom_frames.split(",")
                if tok.strip().lstrip("-").isdigit() and 0 <= int(tok) < len(frames)
            })
            if zoom_idx:
                visual["zoom"] = render_overlay_pngs(
                    frames, zoom_idx, outdir, "zoom",
                    width=args.png_width, height=args.png_height, chrome_path=args.chrome_path,
                )
        if visual["overlay"].get("error") and not visual["overlay"].get("paths"):
            visual["status"] = "unavailable"
            visual["error"] = visual["overlay"]["error"]

    request_path = outdir / "visual_review_request.json"
    if visual["status"] not in ("skipped", "unavailable"):
        request = {
            "instruction": (
                "Inspect the overlay PNGs (and zoom PNGs if present) and decide "
                "pass/warn/fail: did the relaxation stay physically sane (no "
                "unintended desorption, dissociation, atoms passing through each "
                "other, or migration to the wrong site)? Write the result to "
                "expected_review_file."
            ),
            "deterministic_verdict": deterministic_verdict,
            "overlay": (visual["overlay"] or {}).get("paths"),
            "zoom": (visual["zoom"] or {}).get("paths") if visual["zoom"] else None,
            "sampled_indices": (visual["overlay"] or {}).get("indices"),
            "n_frames_total": len(frames),
            "expected_review_file": str(outdir / "visual_review.json"),
            "result_schema": {"verdict": "pass|warn|fail", "reason": "str", "views_reviewed": ["top", "side_a", "side_b"]},
            "rule": "Visual review is downgrade-only: it may keep or worsen the deterministic verdict, never upgrade it.",
        }
        request_path.write_text(json.dumps(request, indent=2, default=json_default))
        visual["request_path"] = str(request_path)

    review_file = Path(args.visual_review).expanduser() if args.visual_review else (outdir / "visual_review.json")
    review_verdict: str | None = None
    if not args.skip_visual_validation and visual["status"] not in ("unavailable",) and review_file.exists():
        try:
            review = json.loads(review_file.read_text())
            candidate = str(review.get("verdict", "")).lower()
            if candidate in SEVERITY:
                review_verdict = candidate
                visual["review"] = review
                visual["review_path"] = str(review_file)
                visual["status"] = "completed"
            else:
                visual["status"] = "invalid"
                visual["error"] = f"review verdict not pass/warn/fail: {review.get('verdict')!r}"
        except Exception as exc:
            visual["status"] = "invalid"
            visual["error"] = f"could not parse {review_file}: {exc}"

    if args.skip_visual_validation:
        visual_floor = "pass"
    elif visual["status"] == "completed":
        visual_floor = review_verdict or "warn"
    else:  # pending / unavailable / invalid → problem floor
        visual_floor = "warn"
    visual["floor_applied"] = visual_floor
    overall_verdict = max(deterministic_verdict, visual_floor, key=lambda v: SEVERITY[v])

    metrics_path = outdir / "metrics.csv"
    summary_path = outdir / "analysis_summary.json"
    selected_path = outdir / "selected_frames.extxyz" if frames and selected else None
    trajectory_html_path = outdir / "aseview_trajectory.html"
    overlay_html_path = outdir / "aseview_overlay.html"
    review_path = outdir / "visual_review.md"

    write_metrics_csv(metrics_path, metrics)
    if selected_path is not None:
        write_selected_frames(selected_path, frames, selected, metrics, anchor_info["anchor_indices"])
    aseview_result = {"trajectory_html_written": False, "overlay_html_written": False, "error": None}
    if not args.no_html:
        aseview_result = write_aseview_htmls(
            trajectory_html_path,
            overlay_html_path,
            frames,
            selected_path,
            args.colormap,
        )

    summary = {
        "status": "ready",
        "verdict": overall_verdict,
        "deterministic_verdict": deterministic_verdict,
        "visual_validation": visual,
        "input": str(input_path),
        "trajectory_input": str(discovered["trajectory"]) if discovered["trajectory"] else None,
        "oszicar_input": str(discovered["oszicar"]) if discovered["oszicar"] else None,
        "frame_count": len(frames),
        "metric_count": len(metrics),
        "anchor": anchor_info,
        "convergence": verdict,
        "run_parameters": run_params,
        "anomalies": anomalies,
        "diagnosis": diagnosis,
        "selected_frames": selected,
        "paths": {
            "summary": str(summary_path),
            "metrics_csv": str(metrics_path),
            "selected_frames_extxyz": str(selected_path) if selected_path else None,
            "visual_review_md": str(review_path),
            "aseview_trajectory_html": str(trajectory_html_path) if aseview_result["trajectory_html_written"] else None,
            "aseview_overlay_html": str(overlay_html_path) if aseview_result["overlay_html_written"] else None,
        },
        "visualization": {
            "aseview_html_written": bool(aseview_result["trajectory_html_written"] or aseview_result["overlay_html_written"]),
            "aseview_error": aseview_result["error"],
            "suggested_commands": {
                "trajectory": f"aseview {discovered['trajectory']}" if discovered["trajectory"] else None,
                "overlay": f"aseview {selected_path.name} -v overlay --cmap {args.colormap} -o aseview_overlay.html" if selected_path else None,
            },
            "direct_png_note": "aseview exposes PNG/GIF export inside the browser viewer; the Python wrapper and CLI save viewer files as HTML.",
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, default=json_default))
    write_review_markdown(review_path, summary, selected_path, args.colormap)
    print(json.dumps(summary, indent=2, default=json_default))
    # Non-zero exit on a failing overall verdict so unattended workflows can gate.
    return 3 if overall_verdict == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
