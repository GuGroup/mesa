#!/usr/bin/env python3
"""Plot comparative reaction energy diagrams with chemdiagrams."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EXAMPLE_SPEC: dict[str, Any] = {
    "data": {
        "Catalyst A": [0.0, -0.13, 0.38, -0.76, -0.20, 0.0],
        "Catalyst B": [0.0, -0.96, -1.02, -1.03, 0.09, 0.0],
        "Interface": [0.0, -0.62, -0.33, -0.73, -0.65, 0.0],
    },
    "x_labels": [
        r"H$_2$O+*+e$^-$",
        r"  H$_2$O*",
        "    TS",
        "  H*+OH*",
        r"  OH*+$\frac{1}{2}$H$_2$",
        r"     *+OH$^-$+$\frac{1}{2}$H$_2$",
    ],
    "colors": {
        "Catalyst A": "#2166ac",
        "Catalyst B": "#d6604d",
        "Interface": "#7b3294",
    },
    "skip_points": {
        "Catalyst B": [2],
    },
    "ylabel": r"$\Delta G_{\mathrm{rel}}$ (eV)",
    "xlabel": "Reaction Coordinate",
    "figsize": [6, 4],
    "fontsize": 10,
    "x_number_min_max": [0.5, 4.5],
    "zero_label_positions": [0, 5],
}


STYLE_DEFAULTS: dict[str, Any] = {
    "ylabel": r"$\Delta G_{\mathrm{rel}}$ (eV)",
    "xlabel": "Reaction Coordinate",
    "figsize": [5.4, 3.6],
    "fontsize": 8,
    "x_number_min_max": [0.5, 4.5],
    "zero_label_positions": [0, 5],
    "show_zero_line": True,
    "show_state_ticks": True,
    "legend_loc": "upper right",
}


DEFAULT_COLOR_ORDER = [
    "#0F4D92",
    "#B64342",
    "#2E7D6F",
    "#9A4D8E",
    "#767676",
    "#D99A2B",
]


def load_spec(path: str | None, use_example: bool = False) -> dict[str, Any]:
    if use_example:
        return EXAMPLE_SPEC
    if not path:
        raise SystemExit("Provide --input energies.json, or use --example only for a generic style demo.")
    with Path(path).open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    spec = dict(STYLE_DEFAULTS)
    spec.update(loaded)
    return spec


def filtered_path(values: list[float], skip_indices: set[int]) -> tuple[list[int], list[float]]:
    x_values = []
    y_values = []
    for idx, value in enumerate(values):
        if idx in skip_indices:
            continue
        x_values.append(idx)
        y_values.append(value)
    return x_values, y_values


def plot(spec: dict[str, Any], output: str) -> Path:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    import matplotlib.transforms as mtransforms

    try:
        from chemdiagrams import EnergyDiagram
    except ImportError as exc:
        raise SystemExit("Missing dependency: install chemdiagrams in the active Python environment.") from exc

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 8,
            "axes.linewidth": 0.9,
            "ytick.major.width": 0.8,
            "xtick.major.width": 0.8,
            "legend.frameon": False,
        }
    )

    dia = EnergyDiagram(figsize=tuple(spec.get("figsize", [6, 4])), fontsize=spec.get("fontsize", 10))
    labels = list(spec["data"])
    colors = dict(spec.get("colors", {}))
    for idx, label in enumerate(labels):
        colors.setdefault(label, DEFAULT_COLOR_ORDER[idx % len(DEFAULT_COLOR_ORDER)])
    skip_points = {label: set(indices) for label, indices in spec.get("skip_points", {}).items()}
    all_drawn_values: list[float] = []

    for label, raw_values in spec["data"].items():
        values = [float(value) for value in raw_values]
        x_plot, y_plot = filtered_path(values, skip_points.get(label, set()))
        all_drawn_values.extend(y_plot)
        dia.draw_path(
            x_plot,
            y_plot,
            color=colors.get(label),
            path_name=label,
            linetypes=1,
            lw_connector=1.35,
            lw_plateau=1.9,
            width_plateau=0.58,
        )

    if spec.get("show_zero_line", True):
        dia.ax.axhline(0, color="#CFCECE", lw=0.8, zorder=0)

    if all_drawn_values:
        y_min = min(all_drawn_values)
        y_max = max(all_drawn_values)
        pad = max((y_max - y_min) * 0.18, 0.18)
        dia.ax.set_ylim(y_min - pad, y_max + pad)

    number_range = spec.get("x_number_min_max")
    if number_range:
        dia.add_numbers_auto(n_decimals=2, x_min_max=tuple(number_range), fontsize=7.5)
    else:
        dia.add_numbers_auto(n_decimals=2, fontsize=7.5)

    for x_ref in spec.get("zero_label_positions", []):
        dia.ax.text(float(x_ref), 0.06, "0.00", ha="center", va="bottom", fontsize=7.5, color="#767676")

    dia.set_diagram_style("boxed")
    if spec.get("x_labels"):
        dia.set_xlabels(spec["x_labels"], fontsize=10, weight="bold")
    dia.ax.set_ylabel(spec.get("ylabel", r"$\Delta G_{\mathrm{rel}}$ (eV)"), fontsize=11, weight="bold")
    dia.ax.set_xlabel(spec.get("xlabel", "Reaction Coordinate"), fontsize=11, weight="bold", labelpad=10)
    if spec.get("title"):
        dia.ax.set_title(spec["title"], fontsize=9, weight="bold")
    dia.ax.tick_params(axis="y", labelsize=8, length=3)
    if spec.get("show_state_ticks", True):
        dia.ax.tick_params(axis="x", which="major", length=6, width=1.1, direction="out", pad=9)
        x_count = max((len(values) for values in spec["data"].values()), default=0)
        ymin, ymax = dia.ax.get_ylim()
        tick_half_len = (ymax - ymin) * 0.023
        for x_state in range(x_count):
            dia.ax.vlines(
                x_state,
                ymin - tick_half_len,
                ymin + tick_half_len,
                color="#272727",
                lw=1.1,
                zorder=4,
                clip_on=False,
            )
    else:
        dia.ax.tick_params(axis="x", length=0)
    for spine in dia.ax.spines.values():
        spine.set_linewidth(0.9)
        spine.set_color("#272727")

    legend_handles = [
        Line2D([0], [0], color=colors.get(label), lw=2.5, label=label)
        for label in spec["data"]
        if colors.get(label)
    ]
    if legend_handles:
        dia.ax.legend(
            handles=legend_handles,
            frameon=False,
            fontsize=8,
            loc=spec.get("legend_loc", "upper right"),
            ncol=1,
            handlelength=1.8,
            handletextpad=0.5,
            prop={"weight": "bold", "size": 8},
        )

    offset = mtransforms.ScaledTranslation(-4 / 72, 0, dia.fig.dpi_scale_trans)
    for tick in dia.ax.get_xticklabels():
        tick.set_fontweight("bold")
        tick.set_fontsize(10)
        tick.set_transform(tick.get_transform() + offset)

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dia.fig.tight_layout()
    dia.fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(dia.fig)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot a reaction energy diagram.")
    parser.add_argument("--input", help="JSON plot spec containing the user's actual paths, energies, and labels.")
    parser.add_argument("--example", action="store_true", help="Render a generic style demo instead of user data.")
    parser.add_argument("--output", default="energy_diagram.svg", help="Output path, usually .svg, .pdf, or .png.")
    args = parser.parse_args()

    output_path = plot(load_spec(args.input, args.example), args.output)
    print(output_path)


if __name__ == "__main__":
    main()
