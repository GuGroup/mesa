from __future__ import annotations

import render_core as rc


def colormap_rgb(name: str, position: float) -> tuple[float, float, float]:
    import matplotlib

    cmap = matplotlib.colormaps[name]
    red, green, blue, _alpha = cmap(position)
    return float(red), float(green), float(blue)


def recolor_atoms(items: list[rc.Item], color: tuple[float, float, float]) -> list[rc.Item]:
    colored: list[rc.Item] = []
    for depth, kind, payload in items:
        if kind == "atom":
            xy, radius, _existing_color, alpha, is_fixed, show_fixed_halo = payload
            colored.append((depth, kind, (xy, radius, color, alpha, is_fixed, show_fixed_halo)))
        else:
            colored.append((depth, kind, payload))
    return colored
