#!/usr/bin/env python3
"""Plot publication-quality DOS/PDOS diagrams from VASP vasprun.xml.

Renders density of states using the sumo visual style (fill_between + line,
automatic legend cutoff, spin-polarised mirroring) without requiring sumo
as a dependency.  Only pymatgen + matplotlib + numpy are needed.

Style sheets in ../styles/ are applied via ``plt.style.use`` to reproduce
the sumo look (color cycle, font sizes, figure dimensions).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import AutoMinorLocator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STYLE_DIR = Path(__file__).resolve().parent.parent / "styles"
SUMO_BASE_STYLE = STYLE_DIR / "sumo_base.mplstyle"
SUMO_DOS_STYLE = STYLE_DIR / "sumo_dos.mplstyle"

EMPTY_SPACE = 1.05  # y-axis headroom multiplier (matches sumo)

DEFAULT_COLORS = [
    "#0075dc", "#d6604d", "#2E7D6F", "#9A4D8E",
    "#426600", "#ff0010", "#003380", "#ffa405",
]

EXAMPLE_SPEC: dict[str, Any] = {
    "title": None,
    "mode": "element_pdos",
    "elements": ["Pt"],
    "orbitals": ["s", "p", "d"],
    "emin": -10,
    "emax": 5,
    "figsize": [4.4, 3.2],
}

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _generate_synthetic_dos() -> dict[str, Any]:
    """Create synthetic DOS data for ``--example`` demos (no vasprun needed)."""
    energies = np.linspace(-12, 6, 500)
    fermi = 0.0

    def _gauss(x: np.ndarray, mu: float, sigma: float, amp: float) -> np.ndarray:
        return amp * np.exp(-0.5 * ((x - mu) / sigma) ** 2)

    s_dos = _gauss(energies, -8.0, 1.5, 2.0) + _gauss(energies, 2.0, 1.8, 1.5)
    p_dos = _gauss(energies, -5.0, 2.0, 4.0) + _gauss(energies, 1.5, 1.5, 3.0)
    d_dos = (
        _gauss(energies, -3.0, 1.2, 12.0)
        + _gauss(energies, -1.0, 0.8, 18.0)
        + _gauss(energies, 0.5, 1.0, 8.0)
    )
    total = s_dos + p_dos + d_dos

    return {
        "energies": energies,
        "fermi": fermi,
        "total": total,
        "pdos": {"Pt": {"s": s_dos, "p": p_dos, "d": d_dos}},
        "is_spin_polarized": False,
    }


def _load_vasprun(path: str) -> dict[str, Any]:
    """Load DOS data from a real vasprun.xml via pymatgen."""
    from pymatgen.electronic_structure.core import OrbitalType, Spin
    from pymatgen.io.vasp.outputs import Vasprun

    vr = Vasprun(path, parse_dos=True, parse_potcar_file=False)
    cdos = vr.complete_dos
    fermi = cdos.efermi
    energies = cdos.energies - fermi  # shift to Fermi = 0

    is_spin = Spin.down in cdos.densities
    total_up = cdos.densities[Spin.up]
    total_down = cdos.densities.get(Spin.down)

    # Collect element-orbital PDOS
    pdos: dict[str, dict[str, Any]] = {}
    for el in cdos.structure.composition.elements:
        el_str = str(el)
        try:
            spd = cdos.get_element_spd_dos(el_str)
        except Exception:
            continue
        pdos[el_str] = {}
        for orb_type, dos_obj in spd.items():
            orb_name = orb_type.name  # s, p, d, f
            up = dos_obj.densities[Spin.up]
            down = dos_obj.densities.get(Spin.down)
            if is_spin and down is not None:
                pdos[el_str][orb_name] = {"up": up, "down": down}
            else:
                pdos[el_str][orb_name] = up

    result: dict[str, Any] = {
        "energies": energies,
        "fermi": 0.0,  # already shifted
        "is_spin_polarized": is_spin,
    }
    if is_spin:
        result["total"] = {"up": total_up, "down": total_down}
    else:
        result["total"] = total_up
    result["pdos"] = pdos
    return result


def _load_spec(path: str | None, vasprun: str | None, use_example: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (spec, dos_data).

    ``spec`` is the plotting configuration; ``dos_data`` holds the actual
    numeric arrays.
    """
    if use_example:
        return dict(EXAMPLE_SPEC), _generate_synthetic_dos()

    if vasprun:
        dos_data = _load_vasprun(vasprun)
        spec: dict[str, Any] = {}
        if path:
            with Path(path).open("r", encoding="utf-8") as f:
                spec = json.load(f)
        return spec, dos_data

    if path:
        with Path(path).open("r", encoding="utf-8") as f:
            spec = json.load(f)
        vr_path = spec.get("vasprun")
        if not vr_path:
            raise SystemExit("JSON spec must contain 'vasprun' key, or use --vasprun.")
        return spec, _load_vasprun(vr_path)

    raise SystemExit("Provide --vasprun, --input, or --example.")


# ---------------------------------------------------------------------------
# Filtering helpers
# ---------------------------------------------------------------------------


def _parse_element_orbitals(tokens: list[str] | None) -> dict[str, list[str]] | None:
    """Parse ``--elements Pt.d Ni.p`` into ``{'Pt': ['d'], 'Ni': ['p']}``."""
    if not tokens:
        return None
    result: dict[str, list[str]] = {}
    for tok in tokens:
        if "." in tok:
            el, orb = tok.split(".", 1)
            result.setdefault(el, []).append(orb)
        else:
            result[tok] = []  # empty = all orbitals
    return result


def _filter_pdos(
    pdos: dict[str, dict[str, Any]],
    element_filter: dict[str, list[str]] | None,
) -> dict[str, dict[str, Any]]:
    """Keep only the elements/orbitals requested."""
    if element_filter is None:
        return pdos
    filtered: dict[str, dict[str, Any]] = {}
    for el, orbitals in element_filter.items():
        if el not in pdos:
            continue
        if not orbitals:
            filtered[el] = pdos[el]
        else:
            filtered[el] = {o: pdos[el][o] for o in orbitals if o in pdos[el]}
    return filtered


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

_ORBITAL_ORDER = {"s": 0, "p": 1, "d": 2, "f": 3}


def _sort_orbitals(orbitals: dict) -> list[str]:
    return sorted(orbitals.keys(), key=lambda o: _ORBITAL_ORDER.get(o, 99))


def plot_dos(
    dos_data: dict[str, Any],
    spec: dict[str, Any],
    output: str,
    subplot: bool = False,
    export_data: bool = False,
) -> Path:
    """Render DOS/PDOS and save to *output*."""
    # Apply sumo styles
    styles: list = []
    if SUMO_BASE_STYLE.exists():
        styles.append(str(SUMO_BASE_STYLE))
    if SUMO_DOS_STYLE.exists():
        styles.append(str(SUMO_DOS_STYLE))
    if styles:
        plt.style.use(styles)

    # Override with spec values
    plt.rcParams.update({
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
    })

    energies = np.asarray(dos_data["energies"])
    is_spin = dos_data.get("is_spin_polarized", False)
    total = dos_data.get("total")
    pdos = dos_data.get("pdos", {})

    # Apply element/orbital filter
    el_filter = _parse_element_orbitals(spec.get("elements"))
    pdos = _filter_pdos(pdos, el_filter)

    emin = spec.get("emin", -6.0)
    emax = spec.get("emax", 6.0)
    mask = (energies >= emin - 0.05) & (energies <= emax + 0.05)
    e_masked = energies[mask]

    plot_total = spec.get("plot_total", True)
    legend_cutoff_pct = spec.get("legend_cutoff", 3.0)
    figsize = tuple(spec.get("figsize", [4.4, 3.2]))

    # Determine number of subplots
    elements = list(pdos.keys())
    if subplot and elements:
        nplots = len(elements) + (1 if plot_total else 0)
    else:
        nplots = 1

    fig, axes = plt.subplots(
        nplots, 1,
        figsize=(figsize[0], figsize[1] * nplots) if nplots > 1 else figsize,
        sharex=True,
        squeeze=False,
    )
    axes_flat: list = [ax for row in axes for ax in row]

    # Track global ymax for consistent scaling
    global_ymax = 0.0
    color_idx = 0

    def _get_density_1d(data: Any, spin_up: bool = True) -> np.ndarray:
        """Extract density array, handling spin dict or plain array."""
        if isinstance(data, dict):
            return np.asarray(data["up"] if spin_up else data["down"])
        return np.asarray(data)

    def _draw_line(
        ax: matplotlib.axes.Axes,
        e: np.ndarray,
        dens_data: Any,
        color: str,
        label: str | None,
        alpha_fill: float,
        is_spin_pol: bool,
    ) -> float:
        """Draw fill_between + line for one DOS component. Returns ymax."""
        ymax = 0.0
        up = _get_density_1d(dens_data, True)[mask]
        ax.fill_between(e, up, lw=0, facecolor=color, alpha=alpha_fill)
        ax.plot(e, up, color=color, label=label, lw=1.2)
        ymax = max(ymax, float(np.max(up)))

        if is_spin_pol and isinstance(dens_data, dict):
            down = -_get_density_1d(dens_data, False)[mask]
            ax.fill_between(e, down, lw=0, facecolor=color, alpha=alpha_fill)
            ax.plot(e, down, color=color, lw=1.2)
            ymax = max(ymax, float(np.max(np.abs(down))))
        return ymax

    # --- Compute reference ymax for legend cutoff ---
    if total is not None:
        ref_up = _get_density_1d(total, True)[mask]
        ref_ymax = float(np.max(ref_up)) if len(ref_up) > 0 else 0
    else:
        ref_ymax = 0
    cutoff = (legend_cutoff_pct / 100.0) * ref_ymax

    if subplot and elements:
        ax_idx = 0
        if plot_total and total is not None:
            ax = axes_flat[ax_idx]
            ym = _draw_line(ax, e_masked, total, "k", "Total DOS", 0.15, is_spin)
            global_ymax = max(global_ymax, ym)
            ax_idx += 1

        for el in elements:
            ax = axes_flat[ax_idx]
            for orb in _sort_orbitals(pdos[el]):
                c = DEFAULT_COLORS[color_idx % len(DEFAULT_COLORS)]
                color_idx += 1
                orb_data = pdos[el][orb]
                orb_max = float(np.max(_get_density_1d(orb_data, True)[mask]))
                label = f"{el} ({orb})" if orb_max >= cutoff else None
                ym = _draw_line(ax, e_masked, orb_data, c, label, 0.25, is_spin)
                global_ymax = max(global_ymax, ym)
            ax.legend(loc="upper right", frameon=False, ncol=1)
            ax_idx += 1
    else:
        ax = axes_flat[0]
        if plot_total and total is not None:
            ym = _draw_line(ax, e_masked, total, "k", "Total DOS", 0.15, is_spin)
            global_ymax = max(global_ymax, ym)

        for el in elements:
            for orb in _sort_orbitals(pdos[el]):
                c = DEFAULT_COLORS[color_idx % len(DEFAULT_COLORS)]
                color_idx += 1
                orb_data = pdos[el][orb]
                orb_max = float(np.max(_get_density_1d(orb_data, True)[mask]))
                label = f"{el} ({orb})" if orb_max >= cutoff else None
                ym = _draw_line(ax, e_masked, orb_data, c, label, 0.25, is_spin)
                global_ymax = max(global_ymax, ym)

    # --- Axis formatting (sumo style) ---
    ymax_plot = global_ymax * EMPTY_SPACE
    for ax in axes_flat:
        ax.set_xlim(emin, emax)
        if is_spin:
            ax.set_ylim(-ymax_plot, ymax_plot)
        else:
            ax.set_ylim(0, ymax_plot)
        # Fermi level line
        ax.axvline(0, color="#888888", ls="--", lw=0.8, zorder=0)
        # Minor ticks
        ax.xaxis.set_minor_locator(AutoMinorLocator(2))
        ax.yaxis.set_minor_locator(AutoMinorLocator(2))
        # y-tick labels off (DOS units are arbitrary)
        ax.tick_params(axis="y", labelleft=False)

    # Labels
    axes_flat[-1].set_xlabel(spec.get("xlabel", "Energy (eV)"))
    if nplots == 1:
        axes_flat[0].set_ylabel(spec.get("ylabel", "DOS"))
        # Place legend above the axes to avoid overlap with curves
        axes_flat[0].legend(
            loc="lower center",
            bbox_to_anchor=(0.5, 1.02),
            frameon=False,
            ncol=spec.get("legend_columns", 4),
            fontsize=9,
            columnspacing=1.0,
            handletextpad=0.4,
        )
    else:
        fig.text(
            0.02, 0.5, spec.get("ylabel", "DOS"),
            ha="left", va="center", rotation="vertical",
            fontsize=matplotlib.rcParams.get("axes.labelsize", 11),
        )
        fig.subplots_adjust(hspace=0)

    if spec.get("title"):
        axes_flat[0].set_title(
            spec["title"], fontsize=9, weight="bold",
            pad=20,  # extra pad to clear legend above
        )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=400, bbox_inches="tight")
    plt.close(fig)

    # Optional data export
    if export_data:
        csv_path = output_path.with_suffix(".csv")
        _export_csv(csv_path, dos_data, mask, elements, pdos)
        print(f"Data exported: {csv_path}")

    return output_path


def _export_csv(
    path: Path,
    dos_data: dict[str, Any],
    mask: np.ndarray,
    elements: list[str],
    pdos: dict[str, dict[str, Any]],
) -> None:
    """Write masked DOS data to a CSV file."""

    def _get_up(d: Any) -> np.ndarray:
        if isinstance(d, dict):
            return np.asarray(d["up"])
        return np.asarray(d)

    energies = np.asarray(dos_data["energies"])[mask]
    columns = ["Energy_eV"]
    data_cols = [energies]

    total = dos_data.get("total")
    if total is not None:
        columns.append("Total_DOS")
        data_cols.append(_get_up(total)[mask])

    for el in elements:
        for orb in _sort_orbitals(pdos[el]):
            columns.append(f"{el}_{orb}")
            data_cols.append(_get_up(pdos[el][orb])[mask])

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row_vals in zip(*data_cols):
            writer.writerow([f"{v:.6f}" for v in row_vals])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot DOS/PDOS from VASP vasprun.xml (sumo style, no sumo dependency)."
    )
    parser.add_argument("--vasprun", help="Path to vasprun.xml or vasprun.xml.gz.")
    parser.add_argument("--input", help="JSON plot spec (see references/input-schema.md).")
    parser.add_argument("--example", action="store_true", help="Render demo with synthetic data.")
    parser.add_argument("--output", default="dos.svg", help="Output path (.svg/.pdf/.png).")
    parser.add_argument(
        "--elements", nargs="+",
        help="Element.orbital filter, e.g. Pt.d Ni.p  (element alone = all orbitals).",
    )
    parser.add_argument("--subplot", action="store_true", help="Separate subplot per element.")
    parser.add_argument("--emin", type=float, help="Minimum energy (eV).")
    parser.add_argument("--emax", type=float, help="Maximum energy (eV).")
    parser.add_argument("--export-data", action="store_true", help="Also save raw data as CSV.")
    parser.add_argument("--no-total", action="store_true", help="Hide total DOS line.")
    args = parser.parse_args()

    spec, dos_data = _load_spec(args.input, args.vasprun, args.example)

    # CLI overrides
    if args.elements:
        spec["elements"] = args.elements
    if args.emin is not None:
        spec["emin"] = args.emin
    if args.emax is not None:
        spec["emax"] = args.emax
    if args.no_total:
        spec["plot_total"] = False

    out = plot_dos(dos_data, spec, args.output, subplot=args.subplot, export_data=args.export_data)
    print(out)


if __name__ == "__main__":
    main()
