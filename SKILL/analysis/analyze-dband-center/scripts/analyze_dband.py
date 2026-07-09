#!/usr/bin/env python3
"""Compute d-band center, width, and filling from VASP vasprun.xml.

Provides single-system analysis and multi-system comparison.  Uses
pymatgen's ``CompleteDos`` methods for the heavy lifting and renders
d-DOS visualisations in the sumo publication style.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import AutoMinorLocator

# ---------------------------------------------------------------------------
# Style paths
# ---------------------------------------------------------------------------

STYLE_DIR = Path(__file__).resolve().parent.parent / "styles"
SUMO_BASE_STYLE = STYLE_DIR / "sumo_base.mplstyle"
SUMO_DOS_STYLE = STYLE_DIR / "sumo_dos.mplstyle"

DEFAULT_COLORS = [
    "#0075dc", "#d6604d", "#2E7D6F", "#9A4D8E",
    "#426600", "#ff0010", "#003380", "#ffa405",
]

# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------


def _analyze_vasprun(
    path: str,
    elements: list[str] | None = None,
    erange: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """Return d-band metrics and d-DOS arrays for one vasprun.xml."""
    from pymatgen.electronic_structure.core import OrbitalType, Spin
    from pymatgen.io.vasp.outputs import Vasprun

    vr = Vasprun(path, parse_dos=True, parse_potcar_file=False)
    cdos = vr.complete_dos
    fermi = cdos.efermi
    energies = cdos.energies - fermi

    if elements is None:
        elements = [
            str(el)
            for el in cdos.structure.composition.elements
            if _has_d_electrons(str(el))
        ]

    results: dict[str, Any] = {
        "fermi": fermi,
        "energies": energies.tolist(),
        "elements": {},
    }

    for el in elements:
        try:
            center = cdos.get_band_center(band=OrbitalType.d, elements=[el], erange=erange)
            width = cdos.get_band_width(band=OrbitalType.d, elements=[el], erange=erange)
            try:
                filling = cdos.get_band_filling(band=OrbitalType.d, elements=[el], erange=erange)
            except TypeError:
                filling = cdos.get_band_filling(band=OrbitalType.d, elements=[el])
        except Exception as exc:
            results["elements"][el] = {"error": str(exc)}
            continue

        # d-DOS for plotting
        spd = cdos.get_element_spd_dos(el)
        d_dos_obj = spd[OrbitalType.d]
        d_dens_up = d_dos_obj.densities[Spin.up]
        d_dens_down = d_dos_obj.densities.get(Spin.down)

        el_result: dict[str, Any] = {
            "d_band_center": round(float(center), 4),
            "d_band_width": round(float(width), 4),
            "d_band_filling": round(float(filling), 4),
            "d_dos_up": d_dens_up.tolist(),
        }
        if d_dens_down is not None:
            el_result["d_dos_down"] = d_dens_down.tolist()

        results["elements"][el] = el_result

    return results


def _has_d_electrons(symbol: str) -> bool:
    """Check if an element typically has d-electrons (transition metals)."""
    from pymatgen.core.periodic_table import Element

    try:
        el = Element(symbol)
        return el.Z >= 21  # Sc onwards
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Synthetic demo data
# ---------------------------------------------------------------------------


def _generate_synthetic_dband() -> dict[str, Any]:
    """Create synthetic d-band data for ``--example`` demos."""
    energies = np.linspace(-12, 6, 500)

    def _gauss(x: np.ndarray, mu: float, sigma: float, amp: float) -> np.ndarray:
        return amp * np.exp(-0.5 * ((x - mu) / sigma) ** 2)

    # Pt-like d-band
    pt_d = (
        _gauss(energies, -3.5, 1.0, 10.0)
        + _gauss(energies, -1.8, 0.7, 15.0)
        + _gauss(energies, 0.3, 0.9, 6.0)
    )
    # PtNi-like d-band (shifted down)
    ptni_d = (
        _gauss(energies, -4.2, 1.0, 9.0)
        + _gauss(energies, -2.5, 0.7, 14.0)
        + _gauss(energies, -0.3, 0.9, 7.0)
    )

    def _calc_center(e: np.ndarray, d: np.ndarray) -> float:
        return float(np.trapezoid(d * e, e) / np.trapezoid(d, e))

    def _calc_width(e: np.ndarray, d: np.ndarray) -> float:
        center = _calc_center(e, d)
        return float(np.sqrt(np.trapezoid(d * (e - center) ** 2, e) / np.trapezoid(d, e)))

    def _calc_filling(e: np.ndarray, d: np.ndarray) -> float:
        below_mask = e <= 0
        return float(np.trapezoid(d[below_mask], e[below_mask]) / np.trapezoid(d, e))

    return {
        "systems": [
            {
                "label": "Pt(111)",
                "energies": energies,
                "d_dos": pt_d,
                "d_band_center": _calc_center(energies, pt_d),
                "d_band_width": _calc_width(energies, pt_d),
                "d_band_filling": _calc_filling(energies, pt_d),
            },
            {
                "label": "PtNi(111)",
                "energies": energies,
                "d_dos": ptni_d,
                "d_band_center": _calc_center(energies, ptni_d),
                "d_band_width": _calc_width(energies, ptni_d),
                "d_band_filling": _calc_filling(energies, ptni_d),
            },
        ]
    }


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------


def _apply_styles() -> None:
    styles: list = []
    if SUMO_BASE_STYLE.exists():
        styles.append(str(SUMO_BASE_STYLE))
    if SUMO_DOS_STYLE.exists():
        styles.append(str(SUMO_DOS_STYLE))
    if styles:
        plt.style.use(styles)
    plt.rcParams.update({"svg.fonttype": "none", "pdf.fonttype": 42})


def plot_single_dband(
    energies: np.ndarray,
    d_dos: np.ndarray,
    center: float,
    label: str,
    output: str,
    emin: float = -10.0,
    emax: float = 5.0,
) -> Path:
    """Plot d-DOS with d-band center marker for a single system."""
    _apply_styles()

    mask = (energies >= emin - 0.05) & (energies <= emax + 0.05)
    e = energies[mask]
    d = d_dos[mask]
    dmax = float(np.max(d))
    ymax = dmax * 1.12

    fig, ax = plt.subplots(figsize=(5.0, 3.4))

    # Filled region below Fermi (subtle background shading)
    fill_mask = e <= 0
    ax.fill_between(e[fill_mask], d[fill_mask], lw=0,
                    facecolor="#0075dc", alpha=0.10)

    # Main d-DOS curve
    ax.fill_between(e, d, lw=0, facecolor="#0075dc", alpha=0.22)
    ax.plot(e, d, color="#0075dc", lw=1.5,
            label=f"{label} d-DOS  ($\\varepsilon_d$={center:.2f} eV)")

    # d-band center: subtle vertical line + triangle marker
    ax.axvline(center, color="#d6604d", ls="-", lw=1.0, alpha=0.5, zorder=1)
    ax.plot(center, ymax * 0.97, marker="v", color="#d6604d",
            markersize=7, clip_on=False, zorder=5)

    # Fermi level
    ax.axvline(0, color="#aaaaaa", ls="--", lw=0.8, zorder=0)
    ax.text(0.15, ymax * 0.92, "$E_F$",
            fontsize=9, color="#999999", ha="left", va="top")

    ax.set_xlim(emin, emax)
    ax.set_ylim(0, ymax)
    ax.set_xlabel("Energy (eV)")
    ax.set_ylabel("d-DOS (states/eV)")
    ax.tick_params(axis="y", labelleft=False)
    ax.xaxis.set_minor_locator(AutoMinorLocator(2))
    ax.yaxis.set_minor_locator(AutoMinorLocator(2))

    # Legend above axes
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 1.02),
        frameon=False,
        ncol=1,
        fontsize=8.5,
        handletextpad=0.4,
        handlelength=1.8,
    )

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=400, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_comparison(
    systems: list[dict[str, Any]],
    output: str,
    emin: float = -10.0,
    emax: float = 5.0,
) -> Path:
    """Overlay d-DOS from multiple systems for comparison."""
    _apply_styles()

    fig, ax = plt.subplots(figsize=(5.0, 3.4))

    global_dmax = 0.0
    center_info: list[tuple[float, str, str]] = []  # (center, label, color)

    for i, sys in enumerate(systems):
        energies = np.asarray(sys["energies"])
        d_dos = np.asarray(sys["d_dos"])
        center = sys["d_band_center"]
        label = sys.get("label", f"System {i + 1}")
        color = DEFAULT_COLORS[i % len(DEFAULT_COLORS)]

        mask = (energies >= emin - 0.05) & (energies <= emax + 0.05)
        e = energies[mask]
        d = d_dos[mask]

        ax.fill_between(e, d, lw=0, facecolor=color, alpha=0.18)
        ax.plot(e, d, color=color, lw=1.5,
                label=f"{label}  ($\\varepsilon_d$={center:.2f} eV)")
        global_dmax = max(global_dmax, float(np.max(d)))
        center_info.append((center, label, color))

    # Set y-axis before drawing center markers
    ymax = global_dmax * 1.12
    ax.set_ylim(0, ymax)
    ax.set_xlim(emin, emax)

    # d-band center markers: subtle vertical lines from bottom
    for center, label, color in center_info:
        ax.axvline(center, color=color, ls="-", lw=1.0, alpha=0.45, zorder=1)
        # Small triangle marker at the top of the line
        ax.plot(center, ymax * 0.97, marker="v", color=color,
                markersize=6, clip_on=False, zorder=5)

    # Fermi level
    ax.axvline(0, color="#aaaaaa", ls="--", lw=0.8, zorder=0)
    ax.text(0.15, ymax * 0.92, "$E_F$",
            fontsize=9, color="#999999", ha="left", va="top")

    ax.set_xlabel("Energy (eV)")
    ax.set_ylabel("d-DOS (states/eV)")
    ax.tick_params(axis="y", labelleft=False)
    ax.xaxis.set_minor_locator(AutoMinorLocator(2))
    ax.yaxis.set_minor_locator(AutoMinorLocator(2))

    # Legend above the axes — includes ε_d values in labels
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 1.02),
        frameon=False,
        ncol=min(len(systems), 3),
        fontsize=8.5,
        columnspacing=1.2,
        handletextpad=0.4,
        handlelength=1.8,
    )

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=400, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="D-band center analysis from VASP vasprun.xml."
    )
    sub = parser.add_subparsers(dest="command")

    # --- single ---
    p_single = sub.add_parser("single", help="Analyse one vasprun.xml.")
    p_single.add_argument("--vasprun", required=True, help="Path to vasprun.xml.")
    p_single.add_argument("--elements", nargs="+", help="Elements to analyse (default: all TMs).")
    p_single.add_argument("--emin", type=float, default=-10.0)
    p_single.add_argument("--emax", type=float, default=5.0)
    p_single.add_argument("--output", default="dband.svg", help="Plot output path.")
    p_single.add_argument("--json", help="Save metrics to JSON file.")

    # --- compare ---
    p_cmp = sub.add_parser("compare", help="Compare d-band across systems.")
    p_cmp.add_argument("--vaspruns", nargs="+", required=True, help="vasprun.xml paths.")
    p_cmp.add_argument("--labels", nargs="+", help="Labels for each system.")
    p_cmp.add_argument("--element", required=True, help="Element to compare (e.g. Pt).")
    p_cmp.add_argument("--emin", type=float, default=-10.0)
    p_cmp.add_argument("--emax", type=float, default=5.0)
    p_cmp.add_argument("--output", default="dband_compare.svg")
    p_cmp.add_argument("--json", help="Save comparison metrics to JSON file.")

    # --- example ---
    p_ex = sub.add_parser("example", help="Render demo with synthetic data.")
    p_ex.add_argument("--output", default="dband_example.svg")
    p_ex.add_argument("--emin", type=float, default=-10.0)
    p_ex.add_argument("--emax", type=float, default=5.0)

    args = parser.parse_args()

    if args.command == "single":
        result = _analyze_vasprun(args.vasprun, args.elements)
        # Print summary
        print(f"{'Element':<10} {'ε_d (eV)':<12} {'Width (eV)':<12} {'Filling':<10}")
        print("-" * 44)
        for el, data in result["elements"].items():
            if "error" in data:
                print(f"{el:<10} ERROR: {data['error']}")
                continue
            print(
                f"{el:<10} {data['d_band_center']:<12.4f} "
                f"{data['d_band_width']:<12.4f} {data['d_band_filling']:<10.4f}"
            )
            # Plot
            energies = np.asarray(result["energies"])
            d_dos = np.asarray(data["d_dos_up"])
            out = plot_single_dband(
                energies, d_dos, data["d_band_center"],
                el, args.output, args.emin, args.emax,
            )
            print(f"Plot saved: {out}")

        if args.json:
            # Convert non-serializable items
            json_result = {
                "fermi": result["fermi"],
                "elements": {
                    el: {k: v for k, v in d.items() if k not in ("d_dos_up", "d_dos_down")}
                    for el, d in result["elements"].items()
                },
            }
            Path(args.json).write_text(json.dumps(json_result, indent=2), encoding="utf-8")
            print(f"Metrics saved: {args.json}")

    elif args.command == "compare":
        labels = args.labels or [Path(v).parent.name for v in args.vaspruns]
        systems = []
        print(f"{'Label':<20} {'ε_d (eV)':<12} {'Width (eV)':<12} {'Filling':<10}")
        print("-" * 54)
        for vr_path, label in zip(args.vaspruns, labels):
            result = _analyze_vasprun(vr_path, [args.element])
            el_data = result["elements"].get(args.element, {})
            if "error" in el_data:
                print(f"{label:<20} ERROR: {el_data['error']}")
                continue
            print(
                f"{label:<20} {el_data['d_band_center']:<12.4f} "
                f"{el_data['d_band_width']:<12.4f} {el_data['d_band_filling']:<10.4f}"
            )
            systems.append({
                "label": label,
                "energies": np.asarray(result["energies"]),
                "d_dos": np.asarray(el_data["d_dos_up"]),
                "d_band_center": el_data["d_band_center"],
                "d_band_width": el_data["d_band_width"],
                "d_band_filling": el_data["d_band_filling"],
            })

        if systems:
            out = plot_comparison(systems, args.output, args.emin, args.emax)
            print(f"Comparison plot saved: {out}")

        if args.json:
            json_out = [
                {k: v for k, v in s.items() if k not in ("energies", "d_dos")}
                for s in systems
            ]
            Path(args.json).write_text(json.dumps(json_out, indent=2), encoding="utf-8")
            print(f"Comparison metrics saved: {args.json}")

    elif args.command == "example":
        demo = _generate_synthetic_dband()
        out = plot_comparison(demo["systems"], args.output, args.emin, args.emax)
        print(f"Example plot saved: {out}")
        print()
        print(f"{'Label':<20} {'ε_d (eV)':<12} {'Width (eV)':<12} {'Filling':<10}")
        print("-" * 54)
        for s in demo["systems"]:
            print(
                f"{s['label']:<20} {s['d_band_center']:<12.4f} "
                f"{s['d_band_width']:<12.4f} {s['d_band_filling']:<10.4f}"
            )

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
