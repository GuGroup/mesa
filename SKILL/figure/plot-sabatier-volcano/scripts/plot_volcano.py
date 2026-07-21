#!/usr/bin/env python3
"""Plot publication-style Sabatier volcano plots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


EXAMPLE_SPEC: dict[str, Any] = {
    "points": [
        {"label": "Pt", "descriptor": -0.05, "activity": 1.00, "family": "noble", "highlight": True},
        {"label": "Pd", "descriptor": -0.18, "activity": 0.83, "family": "noble"},
        {"label": "Ir", "descriptor": -0.32, "activity": 0.64, "family": "noble"},
        {"label": "Ni", "descriptor": -0.58, "activity": 0.35, "family": "base"},
        {"label": "Co", "descriptor": -0.46, "activity": 0.48, "family": "base"},
        {"label": "Fe", "descriptor": -0.72, "activity": 0.20, "family": "base"},
        {"label": "Ag", "descriptor": 0.42, "activity": 0.25, "family": "weak"},
        {"label": "Au", "descriptor": 0.28, "activity": 0.46, "family": "weak"},
        {"label": "Cu", "descriptor": 0.12, "activity": 0.72, "family": "weak", "highlight": True},
    ],
    "curve": {
        "mode": "piecewise",
        "peak_x": 0.0,
        "peak_y": 1.05,
        "left_slope": 1.25,
        "right_slope": -1.55,
        "x_min": -0.85,
        "x_max": 0.55,
    },
    "xlabel": r"$\Delta G_{\mathrm{ads}}$ (eV)",
    "ylabel": "Relative activity",
    "optimum_label": "Sabatier optimum",
    "legend_loc": "auto",
}


STYLE_DEFAULTS: dict[str, Any] = {
    "figsize": [5.0, 3.6],
    "xlabel": r"$\Delta G_{\mathrm{ads}}$ (eV)",
    "ylabel": "Activity",
    "legend_loc": "auto",
    "higher_is_better": True,
    "base_fontsize": 10.5,
    "point_label_fontsize": 9.5,
    "axis_label_fontsize": 12.5,
    "legend_fontsize": 9.5,
}


DEFAULT_FAMILY_STYLES: dict[str, dict[str, str]] = {
    "noble": {"color": "#0F4D92", "marker": "o"},
    "base": {"color": "#B64342", "marker": "s"},
    "weak": {"color": "#2E7D6F", "marker": "^"},
    "other": {"color": "#767676", "marker": "o"},
}


def load_spec(path: str | None, use_example: bool = False) -> dict[str, Any]:
    if use_example:
        return EXAMPLE_SPEC
    if not path:
        raise SystemExit("Provide --input volcano.json, or use --example only for a generic style demo.")
    with Path(path).open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    spec = dict(STYLE_DEFAULTS)
    spec.update(loaded)
    return spec


def curve_xy(curve: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    mode = curve.get("mode", "piecewise")
    if mode == "points":
        return np.asarray(curve["x"], dtype=float), np.asarray(curve["y"], dtype=float)
    if mode != "piecewise":
        raise SystemExit(f"Unsupported curve mode: {mode}")

    peak_x = float(curve.get("peak_x", 0.0))
    peak_y = float(curve.get("peak_y", 1.0))
    left_slope = float(curve.get("left_slope", 1.0))
    right_slope = float(curve.get("right_slope", -1.0))
    x_min = float(curve.get("x_min", peak_x - 1.0))
    x_max = float(curve.get("x_max", peak_x + 1.0))
    x = np.linspace(x_min, x_max, 240)
    y = np.where(x <= peak_x, peak_y + left_slope * (x - peak_x), peak_y + right_slope * (x - peak_x))
    return x, y


def label_offsets(index: int) -> tuple[int, int]:
    offsets = [(5, 5), (5, -9), (-18, 6), (-20, -9), (7, 10), (-22, 11)]
    return offsets[index % len(offsets)]


def choose_legend_loc(ax: Any, handles: list[Any], point_xy: list[tuple[float, float]], curve_xy_data: tuple[np.ndarray, np.ndarray] | None) -> str:
    candidates = ["upper right", "upper left", "lower right", "lower left", "center right", "center left"]
    renderer = ax.figure.canvas.get_renderer()
    point_pixels = np.asarray([ax.transData.transform(xy) for xy in point_xy]) if point_xy else np.empty((0, 2))
    text_bboxes = [
        text.get_window_extent(renderer=renderer).expanded(1.04, 1.12)
        for text in ax.texts
        if text.get_visible()
    ]
    curve_pixels = np.empty((0, 2))
    if curve_xy_data is not None:
        x_curve, y_curve = curve_xy_data
        sample_step = max(len(x_curve) // 80, 1)
        curve_pixels = ax.transData.transform(np.column_stack([x_curve[::sample_step], y_curve[::sample_step]]))

    best_loc = candidates[0]
    best_score = float("inf")
    for loc in candidates:
        legend = ax.legend(handles=handles, loc=loc, prop={"weight": "bold", "size": 9.5})
        ax.figure.canvas.draw()
        bbox = legend.get_window_extent(renderer=renderer).expanded(1.06, 1.10)
        point_hits = sum(bbox.contains(x, y) for x, y in point_pixels)
        curve_hits = sum(bbox.contains(x, y) for x, y in curve_pixels)
        text_hits = sum(bbox.overlaps(text_bbox) for text_bbox in text_bboxes)
        score = point_hits * 100 + text_hits * 50 + curve_hits
        legend.remove()
        if score < best_score:
            best_score = score
            best_loc = loc
        if score == 0:
            break
    return best_loc


def plot(spec: dict[str, Any], output: str) -> Path:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": spec.get("base_fontsize", 10.5),
            "axes.linewidth": 1.0,
            "ytick.major.width": 1.0,
            "xtick.major.width": 1.0,
            "legend.frameon": False,
        }
    )

    points = spec["points"]
    family_styles = {**DEFAULT_FAMILY_STYLES, **spec.get("family_styles", {})}

    fig, ax = plt.subplots(figsize=tuple(spec.get("figsize", [5.0, 3.6])))
    ax.set_facecolor("white")

    curve_pixels_source: tuple[np.ndarray, np.ndarray] | None = None
    if spec.get("curve"):
        x_curve, y_curve = curve_xy(spec["curve"])
        curve_pixels_source = (x_curve, y_curve)
        ax.plot(x_curve, y_curve, color="#272727", lw=1.7, zorder=1, label="Volcano envelope")
        if spec["curve"].get("mode", "piecewise") == "piecewise":
            peak_x = float(spec["curve"].get("peak_x", 0.0))
            peak_y = float(spec["curve"].get("peak_y", 1.0))
            ax.scatter([peak_x], [peak_y], s=40, color="#272727", marker="*", zorder=4)
            ax.annotate(
                spec.get("optimum_label", "Optimum"),
                xy=(peak_x, peak_y),
                xytext=(6, 8),
                textcoords="offset points",
                fontsize=spec.get("point_label_fontsize", 9.5),
                fontweight="bold",
                color="#272727",
            )

    families_seen: list[str] = []
    point_xy: list[tuple[float, float]] = []
    for idx, point in enumerate(points):
        family = point.get("family", "other")
        style = family_styles.get(family, family_styles["other"])
        highlighted = bool(point.get("highlight", False))
        size = 58 if highlighted else 38
        edge_width = 1.2 if highlighted else 0.7
        point_xy.append((float(point["descriptor"]), float(point["activity"])))
        ax.scatter(
            [float(point["descriptor"])],
            [float(point["activity"])],
            s=size,
            marker=style.get("marker", "o"),
            facecolor=style.get("color", "#767676"),
            edgecolor="#272727",
            linewidth=edge_width,
            zorder=3 if highlighted else 2,
        )
        if family not in families_seen:
            families_seen.append(family)

        label_by_default = highlighted or len(points) <= 10
        if point.get("label_point", label_by_default):
            dx, dy = label_offsets(idx)
            ax.annotate(
                point["label"],
                xy=(float(point["descriptor"]), float(point["activity"])),
                xytext=(dx, dy),
                textcoords="offset points",
                fontsize=spec.get("point_label_fontsize", 9.5),
                fontweight="bold" if highlighted else "normal",
                color="#272727",
            )

    ax.set_xlabel(spec.get("xlabel", r"$\Delta G_{\mathrm{ads}}$ (eV)"), fontsize=spec.get("axis_label_fontsize", 12.5), fontweight="bold")
    ax.set_ylabel(spec.get("ylabel", "Activity"), fontsize=spec.get("axis_label_fontsize", 12.5), fontweight="bold")
    if spec.get("title"):
        ax.set_title(spec["title"], fontsize=11, fontweight="bold")

    if spec.get("xlim"):
        ax.set_xlim(*spec["xlim"])
    if spec.get("ylim"):
        ax.set_ylim(*spec["ylim"])
    else:
        y_values = [float(p["activity"]) for p in points]
        if spec.get("curve"):
            y_values.extend(curve_xy(spec["curve"])[1].tolist())
        y_min, y_max = min(y_values), max(y_values)
        pad = max((y_max - y_min) * 0.12, 0.08)
        ax.set_ylim(y_min - pad, y_max + pad)

    ax.tick_params(axis="both", labelsize=10.5, length=4, width=1.0, direction="out")
    for tick in ax.get_xticklabels() + ax.get_yticklabels():
        tick.set_fontweight("bold")
    for spine in ax.spines.values():
        spine.set_linewidth(1.0)
        spine.set_color("#272727")

    legend_handles = []
    if spec.get("curve"):
        legend_handles.append(Line2D([0], [0], color="#272727", lw=1.7, label="Envelope"))
    for family in families_seen:
        style = family_styles.get(family, family_styles["other"])
        legend_handles.append(
            Line2D(
                [0],
                [0],
                marker=style.get("marker", "o"),
                color="none",
                markerfacecolor=style.get("color", "#767676"),
                markeredgecolor="#272727",
                markersize=7,
                label=family,
            )
        )
    legend_loc = spec.get("legend_loc", "auto")
    if legend_loc == "auto":
        fig.canvas.draw()
        legend_loc = choose_legend_loc(ax, legend_handles, point_xy, curve_pixels_source)
    ax.legend(handles=legend_handles, loc=legend_loc, prop={"weight": "bold", "size": spec.get("legend_fontsize", 9.5)})

    fig.tight_layout()
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot a Sabatier volcano figure.")
    parser.add_argument("--input", help="JSON volcano plot spec containing user data.")
    parser.add_argument("--example", action="store_true", help="Render a generic style demo instead of user data.")
    parser.add_argument("--output", default="volcano.svg", help="Output path, usually .svg, .pdf, or .png.")
    args = parser.parse_args()

    print(plot(load_spec(args.input, args.example), args.output))


if __name__ == "__main__":
    main()
