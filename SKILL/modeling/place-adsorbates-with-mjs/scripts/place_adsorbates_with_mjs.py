#!/usr/bin/env python3
"""Extract regular P0/P1/P2 adsorption sites as top/bridge/hollow records.

This wrapper is intentionally kept under audit/ so the original project files remain
unchanged while the workflow is tested.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WORKCOPY_ROOT = Path(__file__).resolve().parents[1]
FIG3_SCRIPT_DIR = Path(__file__).resolve().parent
if str(FIG3_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(FIG3_SCRIPT_DIR))

from fig3_common import (  # type: ignore  # noqa: E402
    ensure_dir,
    extract_framework_atoms,
    graph_box,
    graph_cell,
    inverse_3x3,
    normal_from_node,
    pbc_distance,
    prepare_poscar_input,
    read_json,
    row_vec_mat,
    v_add,
    v_mul,
    write_json,
)

SITE_KIND_BY_NODE_TYPE = {"P0": "top", "P1": "bridge", "P2": "hollow"}
NODE_TYPE_BY_SITE_KIND = {v: k for k, v in SITE_KIND_BY_NODE_TYPE.items()}
SITE_COLOR = {"top": "#1f77b4", "bridge": "#2ca02c", "hollow": "#d62728"}
SITE_SYMBOL = {"top": "He", "bridge": "Ne", "hollow": "Ar"}


@dataclass(frozen=True)
class PolicyDecision:
    accepted: bool
    site_kind: str
    regular: bool
    regular_policy: str
    reason: str


def finite_vec(value: Any, length: int = 3) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        return None
    out: list[float] = []
    try:
        for item in value:
            number = float(item)
            if not math.isfinite(number):
                return None
            out.append(number)
    except (TypeError, ValueError):
        return None
    return out


def parse_pbc_mask(raw: str) -> list[bool]:
    text = str(raw).strip().replace(" ", "")
    if "," in text:
        parts = text.split(",")
    else:
        parts = list(text)
    if len(parts) != 3 or any(part not in {"0", "1"} for part in parts):
        raise ValueError(f"PBC mask must be one of 111, 110, 000 or comma form; got {raw!r}")
    return [part == "1" for part in parts]


def pbc_mask_to_cli(mask: list[bool]) -> str:
    if len(mask) != 3:
        raise ValueError(f"PBC mask length must be 3, got {mask!r}")
    return ",".join("1" if bool(x) else "0" for x in mask)


def pbc_mask_to_label(mask: list[bool]) -> str:
    if len(mask) != 3:
        raise ValueError(f"PBC mask length must be 3, got {mask!r}")
    return "".join("1" if bool(x) else "0" for x in mask)


def site_kind_for_type(node_type: str | None) -> str:
    return SITE_KIND_BY_NODE_TYPE.get(str(node_type), "unknown")


def regular_site_policy(node: dict[str, Any]) -> PolicyDecision:
    node_type = str(node.get("type") or "")
    site_kind = site_kind_for_type(node_type)
    if site_kind == "unknown":
        return PolicyDecision(False, "unknown", False, "unsupported_node_type", "unsupported_node_type")

    if finite_vec(node.get("position")) is None:
        return PolicyDecision(False, site_kind, False, "missing_anchor_position", "missing_anchor_position")

    classification = str(node.get("classification") or "")
    if node_type == "P0":
        has_surface_normal = finite_vec(node.get("surface_normal")) is not None
        placement = node.get("placement") if isinstance(node.get("placement"), dict) else {}
        has_placement = finite_vec(placement.get("position")) is not None
        if not has_surface_normal and not has_placement:
            return PolicyDecision(False, site_kind, False, "P0_top_surface_node_exception", "missing_p0_normal_or_placement")
        return PolicyDecision(True, site_kind, True, "P0_top_surface_node_exception", "accepted")

    if classification != "regular":
        return PolicyDecision(False, site_kind, False, "classification_regular_required", f"classification_not_regular:{classification or 'missing'}")

    if node_type == "P2":
        if node.get("topology_valid_for_benchmark") is False:
            return PolicyDecision(False, site_kind, False, "regular_p2_topology_required", "p2_topology_invalid")
        if node.get("normal_display_allowed") is False:
            return PolicyDecision(False, site_kind, False, "regular_p2_topology_required", "p2_normal_display_blocked")
        if node.get("benchmark_blocking") is True:
            return PolicyDecision(False, site_kind, False, "regular_p2_topology_required", "p2_benchmark_blocking")
        status = str(node.get("topology_status") or "")
        if status and "invalid" in status.lower():
            return PolicyDecision(False, site_kind, False, "regular_p2_topology_required", f"p2_topology_status:{status}")
        return PolicyDecision(True, site_kind, True, "regular_p2_topology_required", "accepted")

    return PolicyDecision(True, site_kind, True, "classification_regular_required", "accepted")


def resolve_path_for_cli(value: str | os.PathLike[str]) -> Path:
    path = Path(os.path.expandvars(str(value))).expanduser()
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def sha256_12(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def _clean_float(value: float, eps: float = 1.0e-10) -> float:
    if abs(value) < eps:
        return 0.0
    nearest = round(value)
    if abs(value - nearest) < eps:
        return float(nearest)
    return value


def _wrap_fractional_components(frac: list[float], pbc: list[bool]) -> tuple[list[float], list[int], bool]:
    wrapped = list(frac)
    image_shift = [0, 0, 0]
    was_wrapped = False
    for i, periodic in enumerate(pbc):
        if not periodic:
            continue
        shift = math.floor(frac[i] + 1.0e-12)
        image_shift[i] = int(shift)
        if shift != 0:
            was_wrapped = True
        wrapped[i] = frac[i] - shift
        if wrapped[i] >= 1.0 - 1.0e-12:
            wrapped[i] = 0.0
            image_shift[i] += 1
            was_wrapped = True
        elif wrapped[i] < 0.0 and abs(wrapped[i]) < 1.0e-12:
            wrapped[i] = 0.0
    return wrapped, image_shift, was_wrapped


def wrap_position_to_pbc_cell(
    position: list[float],
    cell: list[list[float]] | None,
    box: list[float] | None,
    pbc: list[bool],
) -> tuple[list[float], list[int], bool]:
    """Wrap a Cartesian position into the displayed cell along periodic axes.

    Nonorthogonal cells must be wrapped in fractional coordinates using the full
    row-vector cell matrix. Open axes are left unchanged, so pbc110 slabs keep z.
    """
    pos = finite_vec(position)
    if pos is None:
        raise ValueError(f"position must be a finite 3-vector, got {position!r}")
    axes = list(pbc)
    if len(axes) != 3:
        raise ValueError(f"PBC mask length must be 3, got {pbc!r}")

    if cell is not None:
        try:
            frac = row_vec_mat(pos, inverse_3x3(cell))
            wrapped_frac, image_shift, was_wrapped = _wrap_fractional_components(frac, axes)
            wrapped = row_vec_mat(wrapped_frac, cell)
            return [_clean_float(x) for x in wrapped], image_shift, was_wrapped
        except ValueError:
            pass

    if box is None:
        return pos, [0, 0, 0], False

    wrapped = list(pos)
    image_shift = [0, 0, 0]
    was_wrapped = False
    for i, periodic in enumerate(axes):
        if not periodic:
            continue
        length = float(box[i]) if i < len(box) else 0.0
        if length <= 1.0e-12:
            continue
        shift = math.floor(pos[i] / length + 1.0e-12)
        image_shift[i] = int(shift)
        if shift != 0:
            was_wrapped = True
        wrapped[i] = pos[i] - shift * length
        if wrapped[i] >= length - 1.0e-12:
            wrapped[i] = 0.0
            image_shift[i] += 1
            was_wrapped = True
        elif wrapped[i] < 0.0 and abs(wrapped[i]) < 1.0e-12:
            wrapped[i] = 0.0
    return [_clean_float(x) for x in wrapped], image_shift, was_wrapped


def slab_z_side(
    position: list[float],
    atoms: list[dict[str, Any]],
) -> tuple[str | None, dict[str, float | int | None]]:
    """Classify a position as zmin/zmax relative to the framework atom slab."""
    z_values: list[float] = []
    for atom in atoms:
        atom_pos = finite_vec(atom.get("position"))
        if atom_pos is not None:
            z_values.append(atom_pos[2])
    pos = finite_vec(position)
    if pos is None or not z_values:
        return None, {"slab_z_min": None, "slab_z_max": None, "slab_z_mid": None, "slab_atom_count": len(z_values)}
    slab_z_min = min(z_values)
    slab_z_max = max(z_values)
    slab_z_mid = 0.5 * (slab_z_min + slab_z_max)
    side = "zmax" if pos[2] >= slab_z_mid else "zmin"
    return side, {
        "slab_z_min": _clean_float(slab_z_min),
        "slab_z_max": _clean_float(slab_z_max),
        "slab_z_mid": _clean_float(slab_z_mid),
        "slab_atom_count": len(z_values),
    }


def single_open_axis(pbc: list[bool]) -> int | None:
    open_axes = [index for index, periodic in enumerate(pbc) if not periodic]
    return open_axes[0] if len(open_axes) == 1 else None


def fractional_open_axis_side(
    position: list[float],
    atoms: list[dict[str, Any]],
    pbc: list[bool],
    cell: list[list[float]] | None,
) -> tuple[str | None, dict[str, Any]]:
    """Classify a site by fractional coordinate on the single open cell axis."""
    axis = single_open_axis(pbc)
    if axis is None or cell is None:
        return None, {"open_axis_index": axis, "open_axis_label": None, "open_axis_fractional": None, "open_axis_mid": None}
    try:
        inv_cell = inverse_3x3(cell)
        pos = finite_vec(position)
        if pos is None:
            raise ValueError("non-finite position")
        site_frac = row_vec_mat(pos, inv_cell)
        atom_axis_values: list[float] = []
        for atom in atoms:
            atom_pos = finite_vec(atom.get("position"))
            if atom_pos is not None:
                atom_axis_values.append(row_vec_mat(atom_pos, inv_cell)[axis])
        if not atom_axis_values:
            raise ValueError("missing atom positions")
    except ValueError:
        return None, {"open_axis_index": axis, "open_axis_label": "abc"[axis], "open_axis_fractional": None, "open_axis_mid": None}

    axis_min = min(atom_axis_values)
    axis_max = max(atom_axis_values)
    axis_mid = 0.5 * (axis_min + axis_max)
    site_axis = site_frac[axis]
    side = "open-max" if site_axis >= axis_mid else "open-min"
    return side, {
        "open_axis_index": axis,
        "open_axis_label": "abc"[axis],
        "open_axis_fractional": _clean_float(site_axis),
        "open_axis_min": _clean_float(axis_min),
        "open_axis_max": _clean_float(axis_max),
        "open_axis_mid": _clean_float(axis_mid),
    }


def classify_open_axis_side(
    position: list[float],
    atoms: list[dict[str, Any]],
    pbc: list[bool],
    cell: list[list[float]] | None,
    requested_side: str,
) -> tuple[str | None, dict[str, Any]]:
    if requested_side in ("open-max", "open-min"):
        return fractional_open_axis_side(position, atoms, pbc, cell)
    side, metadata = slab_z_side(position, atoms)
    return side, dict(metadata)


def choose_candidate_position(
    node: dict[str, Any],
    normal_source: str,
    candidate_distance: float,
) -> tuple[list[float] | None, list[float] | None, str, str | None, bool | None]:
    placement = node.get("placement") if isinstance(node.get("placement"), dict) else {}
    placement_pos = finite_vec(placement.get("position"))
    normal = normal_from_node(node, normal_source)
    if normal is not None:
        normal = finite_vec(normal)
    if placement_pos is not None:
        return (
            placement_pos,
            normal,
            "placement.position",
            str(placement.get("status")) if placement.get("status") is not None else None,
            bool(placement.get("target_clearance_reached")) if placement.get("target_clearance_reached") is not None else None,
        )
    anchor = finite_vec(node.get("position"))
    if anchor is None or normal is None:
        return None, normal, "missing_position_or_normal", None, None
    return v_add(anchor, v_mul(normal, candidate_distance)), normal, "fallback_anchor_plus_normal", None, None


def compute_min_clearance(
    position: list[float],
    atoms: list[dict[str, Any]],
    adsorbate_radius: float,
    box: list[float] | None,
    pbc: list[bool],
    cell: list[list[float]] | None,
) -> tuple[float | None, str | None]:
    best: float | None = None
    best_atom: str | None = None
    for atom in atoms:
        atom_pos = finite_vec(atom.get("position"))
        if atom_pos is None:
            continue
        dist = pbc_distance(position, atom_pos, box, pbc, cell=cell)
        clearance = dist - float(atom.get("atom_radius", 1.5)) - adsorbate_radius
        if best is None or clearance < best:
            best = clearance
            best_atom = str(atom.get("id"))
    return best, best_atom


def deduplicate_sites(
    sites: list[dict[str, Any]],
    threshold: float,
    box: list[float] | None,
    pbc: list[bool],
    cell: list[list[float]] | None,
) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    for site in sorted(sites, key=lambda item: float(item.get("min_clearance", -1.0e99)), reverse=True):
        duplicate = False
        for prev in accepted:
            if site.get("site_kind") != prev.get("site_kind"):
                continue
            if pbc_distance(site["adsorption_position"], prev["adsorption_position"], box, pbc, cell=cell) < threshold:
                duplicate = True
                break
        if not duplicate:
            accepted.append(site)
    accepted.sort(key=lambda item: (str(item.get("site_kind")), str(item.get("source_node_id"))))
    return accepted


def extract_regular_sites(
    data: dict[str, Any],
    adsorbate_radius: float,
    gap: float,
    pbc: list[bool],
    normal_source: str,
    dedup_distance: float,
    candidate_distance: float = 3.0,
    open_axis_side: str = "both",
) -> dict[str, Any]:
    atoms = extract_framework_atoms(data)
    box = graph_box(data)
    cell = graph_cell(data)
    raw_sites: list[dict[str, Any]] = []
    rejected: Counter[str] = Counter()
    nodes = [node for node in data.get("nodes", []) if isinstance(node, dict)]

    for node in nodes:
        decision = regular_site_policy(node)
        if not decision.accepted:
            rejected[decision.reason] += 1
            continue
        pos, normal, position_source, placement_status, placement_target_reached = choose_candidate_position(
            node, normal_source, candidate_distance
        )
        if pos is None or finite_vec(pos) is None:
            rejected["missing_candidate_position"] += 1
            continue
        raw_pos = finite_vec(pos)
        assert raw_pos is not None
        wrapped_pos, pbc_image_shift, pbc_wrapped = wrap_position_to_pbc_cell(raw_pos, cell=cell, box=box, pbc=pbc)
        min_clearance, nearest_atom = compute_min_clearance(wrapped_pos, atoms, adsorbate_radius, box, pbc, cell)
        if min_clearance is None:
            rejected["missing_clearance"] += 1
            continue
        if min_clearance < gap:
            rejected["clearance_lt_gap"] += 1
            continue
        side, side_metadata = classify_open_axis_side(wrapped_pos, atoms, pbc, cell, open_axis_side)
        if open_axis_side != "both" and side != open_axis_side:
            rejected["open_axis_side_filter"] += 1
            continue
        node_type = str(node.get("type"))
        site_kind = decision.site_kind
        source_id = str(node.get("id"))
        site = {
            "site_id": f"{site_kind}_{source_id}",
            "site_kind": site_kind,
            "node_type": node_type,
            "source_node_id": source_id,
            "classification": node.get("classification"),
            "regular": decision.regular,
            "regular_policy": decision.regular_policy,
            "anchor_position": finite_vec(node.get("position")),
            "raw_adsorption_position": raw_pos,
            "adsorption_position": wrapped_pos,
            "pbc_wrapped": pbc_wrapped,
            "pbc_image_shift": pbc_image_shift,
            "open_axis_side": side,
            "open_axis_side_filter": open_axis_side,
            "slab_z_min": side_metadata.get("slab_z_min"),
            "slab_z_max": side_metadata.get("slab_z_max"),
            "slab_z_mid": side_metadata.get("slab_z_mid"),
            "open_axis_index": side_metadata.get("open_axis_index"),
            "open_axis_label": side_metadata.get("open_axis_label"),
            "open_axis_fractional": side_metadata.get("open_axis_fractional"),
            "open_axis_min": side_metadata.get("open_axis_min"),
            "open_axis_max": side_metadata.get("open_axis_max"),
            "open_axis_mid": side_metadata.get("open_axis_mid"),
            "position_source": position_source,
            "normal_source": normal_source,
            "normal": normal,
            "min_clearance": min_clearance,
            "nearest_atom": nearest_atom,
            "atoms": node.get("atoms"),
            "placement_status": placement_status,
            "placement_target_reached": placement_target_reached,
            "topology_valid_for_benchmark": node.get("topology_valid_for_benchmark"),
            "incident_p3_count": node.get("incident_p3_count"),
            "value": node.get("value"),
            "value_type": node.get("value_type"),
        }
        raw_sites.append(site)

    sites = deduplicate_sites(raw_sites, dedup_distance, box, pbc, cell)
    counts = Counter(site["site_kind"] for site in sites)
    return {
        "framework_atom_count": len(atoms),
        "raw_site_count": len(raw_sites),
        "sites": sites,
        "counts": {"top": counts.get("top", 0), "bridge": counts.get("bridge", 0), "hollow": counts.get("hollow", 0), "total": len(sites)},
        "rejected": dict(rejected),
        "box": box,
        "cell": cell,
    }


def select_sites_for_html(sites: list[dict[str, Any]], per_kind: int = 5) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for kind in ("top", "bridge", "hollow"):
        subset = [site for site in sites if site.get("site_kind") == kind]
        subset.sort(key=lambda item: float(item.get("min_clearance", -1.0e99)), reverse=True)
        selected.extend(subset[: max(0, int(per_kind))])
    return selected


def write_sites_csv(path: Path, sites: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    fields = [
        "site_id",
        "site_kind",
        "node_type",
        "source_node_id",
        "classification",
        "min_clearance",
        "nearest_atom",
        "position_source",
        "placement_status",
        "open_axis_side",
        "x",
        "y",
        "z",
        "normal_x",
        "normal_y",
        "normal_z",
        "atoms",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for site in sites:
            pos = finite_vec(site.get("adsorption_position")) or [None, None, None]
            normal = finite_vec(site.get("normal")) or [None, None, None]
            writer.writerow(
                {
                    "site_id": site.get("site_id"),
                    "site_kind": site.get("site_kind"),
                    "node_type": site.get("node_type"),
                    "source_node_id": site.get("source_node_id"),
                    "classification": site.get("classification"),
                    "min_clearance": site.get("min_clearance"),
                    "nearest_atom": site.get("nearest_atom"),
                    "position_source": site.get("position_source"),
                    "placement_status": site.get("placement_status"),
                    "open_axis_side": site.get("open_axis_side"),
                    "x": pos[0],
                    "y": pos[1],
                    "z": pos[2],
                    "normal_x": normal[0],
                    "normal_y": normal[1],
                    "normal_z": normal[2],
                    "atoms": json.dumps(site.get("atoms"), ensure_ascii=False),
                }
            )


def write_sites_xyz(path: Path, sites: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    lines = [str(len(sites)), "regular adsorption sites: top=P0 bridge=P1 hollow=P2"]
    for site in sites:
        pos = finite_vec(site.get("adsorption_position"))
        if pos is None:
            continue
        symbol = SITE_SYMBOL.get(str(site.get("site_kind")), "X")
        lines.append(
            f"{symbol} {pos[0]:.8f} {pos[1]:.8f} {pos[2]:.8f} # {site.get('site_id')} clearance={float(site.get('min_clearance', 0.0)):.6g}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_html(path: Path, atoms: list[dict[str, Any]], sites: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    atom_points = []
    for atom in atoms:
        pos = finite_vec(atom.get("position"))
        if pos is None:
            continue
        atom_points.append({"id": atom.get("id"), "element": atom.get("element"), "position": pos})
    site_points = []
    for site in sites:
        pos = finite_vec(site.get("adsorption_position"))
        if pos is None:
            continue
        site_points.append({**site, "adsorption_position": pos})
    payload = {"atoms": atom_points, "sites": site_points, "metadata": metadata}
    rows = []
    for site in site_points:
        pos = site["adsorption_position"]
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(site.get('site_kind')))}</td>"
            f"<td>{html.escape(str(site.get('source_node_id')))}</td>"
            f"<td>{float(site.get('min_clearance', 0.0)):.6f}</td>"
            f"<td>{pos[0]:.6f}, {pos[1]:.6f}, {pos[2]:.6f}</td>"
            f"<td>{html.escape(str(site.get('classification')))}</td>"
            "</tr>"
        )
    site_counts = Counter(site.get("site_kind") for site in site_points)
    structure_label = Path(str(metadata.get("input") or "structure")).stem
    page_title = f"{structure_label} regular adsorption sites"
    html_text = f"""<!doctype html>
<meta charset="utf-8">
<title>{html.escape(page_title)}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<h1>Regular adsorption sites sample</h1>
<p>top=P0, bridge=P1, hollow=P2. Showing sampled sites selected by highest clearance per kind. Periodic axes are wrapped into the display cell; open axes are left unchanged.</p>
<ul>
  <li>input: <code>{html.escape(str(metadata.get('input')))}</code></li>
  <li>pbc: <code>{html.escape(str(metadata.get('pbc_label')))}</code></li>
  <li>-a / adsorbate radius / engine alpha used: <code>{html.escape(str(metadata.get('adsorbate_radius')))}</code></li>
  <li>engine sha256_12: <code>{html.escape(str(metadata.get('engine_sha256_12')))}</code></li>
  <li>shown counts: {dict(site_counts)}</li>
</ul>
<div id="plot" style="width:100%;height:760px;"></div>
<table border="1" cellspacing="0" cellpadding="4">
<thead><tr><th>kind</th><th>source node</th><th>min clearance</th><th>position</th><th>classification</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
<script>
const payload = {json.dumps(payload, ensure_ascii=False)};
const atoms = payload.atoms;
const sites = payload.sites;
const traces = [];
traces.push({{
  type: 'scatter3d', mode: 'markers', name: 'framework atoms',
  x: atoms.map(p => p.position[0]), y: atoms.map(p => p.position[1]), z: atoms.map(p => p.position[2]),
  text: atoms.map(p => `${{p.element || 'X'}} ${{p.id}}`),
  marker: {{size: 3, color: '#888', opacity: 0.55}}
}});
const colors = {{top: '#1f77b4', bridge: '#2ca02c', hollow: '#d62728'}};
for (const kind of ['top', 'bridge', 'hollow']) {{
  const subset = sites.filter(s => s.site_kind === kind);
  traces.push({{
    type: 'scatter3d', mode: 'markers+text', name: `${{kind}} (${{kind === 'top' ? 'P0' : kind === 'bridge' ? 'P1' : 'P2'}})`,
    x: subset.map(s => s.adsorption_position[0]),
    y: subset.map(s => s.adsorption_position[1]),
    z: subset.map(s => s.adsorption_position[2]),
    text: subset.map(s => s.source_node_id),
    textposition: 'top center',
    hovertext: subset.map(s => `${{s.site_id}}<br>clearance=${{Number(s.min_clearance).toFixed(6)}}<br>classification=${{s.classification}}`),
    hoverinfo: 'text',
    marker: {{size: 7, color: colors[kind], opacity: 0.95, line: {{width: 1, color: '#111'}}}}
  }});
}}
Plotly.newPlot('plot', traces, {{
  title: {json.dumps(page_title + ': 5 each P0/P1/P2 when available')},
  scene: {{aspectmode: 'data', xaxis: {{title: 'x (A)'}}, yaxis: {{title: 'y (A)'}}, zaxis: {{title: 'z (A)'}}}},
  legend: {{orientation: 'h'}}
}});
</script>
"""
    path.write_text(html_text, encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-f", "--input", required=True, type=str, help="CIF or POSCAR input")
    parser.add_argument("-a", "--adsorbate-radius", required=True, type=float, help="Adsorbate radius; also used as engine -a unless --engine-alpha is set")
    parser.add_argument("--pbc", required=True, type=str, help="PBC mask: 111, 110, 000, or comma form")
    parser.add_argument("--engine-alpha", type=float, default=None, help="Optional C++ weighted-alpha value; defaults to -a")
    parser.add_argument("--gap", type=float, default=0.1, help="Required clearance after subtracting framework and adsorbate radii")
    parser.add_argument("--dedup-distance", type=float, default=0.6, help="Per-kind site deduplication distance")
    parser.add_argument("--candidate-distance", type=float, default=3.0, help="Fallback anchor + normal distance when placement is unavailable")
    parser.add_argument("--normal-source", choices=("current", "geompy"), default="current")
    parser.add_argument(
        "--open-axis-side",
        choices=("both", "zmax", "zmin", "open-max", "open-min"),
        default="both",
        help="For slabs, keep both sides, Cartesian-z side, or fractional side along the single open cell axis",
    )
    parser.add_argument("--placement-step", type=float, default=0.0125)
    parser.add_argument("--placement-max-distance", type=float, default=8.0)
    parser.add_argument("--alpha-factor", type=float, default=1.0, help="weighted-alpha construction factor for --engine-cli new (reference~1.0, production 3.5)")
    parser.add_argument("--engine-cli", choices=("new", "legacy"), default="new", help="new: -a=contact radius + --alpha-factor + --input-sha256 (PR#21 engine); legacy: -a=alpha + --precursor-radius (reference engine)")
    parser.add_argument("--sample-per-kind", type=int, default=5, help="Number of top/bridge/hollow sites to show in sample HTML")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--out-dir", type=str, default=None)
    parser.add_argument("--exe", type=str, required=True)
    parser.add_argument("--radius-file", type=str, required=True)
    parser.add_argument("--dry-run", action="store_true", help="Prepare input and command metadata, but do not execute the engine")
    parser.add_argument("--debug", action="store_true", help="Preserve full engine graph/logs under engine_run/ for private audit (public output stays IP-minimal by default)")
    return parser


def default_out_dir(input_path: Path, adsorbate_radius: float, pbc_label: str) -> Path:
    safe_radius = str(adsorbate_radius).replace(".", "p").replace("-", "m")
    return Path.cwd() / "audit" / "reproduced" / "adsorption_sites" / f"{input_path.stem}_a{safe_radius}_pbc{pbc_label}"


def command_to_string(command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in str(part) else str(part) for part in command)


def sha256_hex(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_engine_command(command: list[str], run_dir: Path, timeout_seconds: int) -> dict[str, Any]:
    """Run a prebuilt (new-CLI) engine command; graph is emitted into run_dir."""
    run_dir.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    result = subprocess.run(command, cwd=str(run_dir), text=True, capture_output=True, timeout=timeout_seconds, check=False)
    runtime = time.perf_counter() - start
    (run_dir / "weighted_alpha_stdout.log").write_text(result.stdout, encoding="utf-8")
    (run_dir / "weighted_alpha_stderr.log").write_text(result.stderr, encoding="utf-8")
    graph = run_dir / "weighted_alpha_graph_geompy_normals.json"
    if not graph.exists():
        graph = run_dir / "weighted_alpha_graph.json"
    return {
        "command": command,
        "command_string": command_to_string(command),
        "returncode": result.returncode,
        "runtime_seconds": runtime,
        "stdout_log": str(run_dir / "weighted_alpha_stdout.log"),
        "stderr_log": str(run_dir / "weighted_alpha_stderr.log"),
        "graph_json": str(graph),
        "graph_exists": graph.exists(),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    pbc = parse_pbc_mask(args.pbc)
    if args.open_axis_side in ("zmax", "zmin") and pbc[2]:
        raise ValueError("--open-axis-side zmax/zmin requires a nonperiodic z axis, e.g. --pbc 110 or 000")
    if args.open_axis_side in ("open-max", "open-min") and single_open_axis(pbc) is None:
        raise ValueError("--open-axis-side open-max/open-min requires exactly one nonperiodic axis")
    pbc_label = pbc_mask_to_label(pbc)
    input_path = resolve_path_for_cli(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"input not found: {input_path}")
    exe = resolve_path_for_cli(args.exe)
    if not exe.exists():
        raise FileNotFoundError(f"weighted-alpha executable not found: {exe}")
    radius_file = resolve_path_for_cli(args.radius_file)
    if not radius_file.exists():
        raise FileNotFoundError(f"radius file not found: {radius_file}")

    engine_alpha = float(args.engine_alpha) if args.engine_alpha is not None else float(args.adsorbate_radius)
    engine_alpha_source = "--engine-alpha" if args.engine_alpha is not None else "-a/--adsorbate-radius"
    out_dir = ensure_dir(resolve_path_for_cli(args.out_dir) if args.out_dir else default_out_dir(input_path, args.adsorbate_radius, pbc_label))
    prepared_dir = ensure_dir(out_dir / "prepared_input")
    structure_id = input_path.stem
    conversion = prepare_poscar_input(input_path, prepared_dir, structure_id)
    prepared_poscar = Path(conversion["output"])

    extra_args = ["--voro-construction-mode", "pbc_masked_image_aware", "--radius-file", str(radius_file.resolve())]
    staged_input_sha256 = sha256_hex(prepared_poscar)
    if args.engine_cli == "new":
        # PR#21 engine contract: -a = contact-anchor radius, --alpha-factor = weighted-alpha factor,
        # staged POSCAR bound via --input-sha256 (no --precursor-radius).
        command = [
            str(exe.resolve()),
            "-f",
            str(prepared_poscar.resolve()),
            "-a",
            str(float(args.adsorbate_radius)),
            "--alpha-factor",
            str(float(args.alpha_factor)),
            "--pbc",
            pbc_mask_to_cli(pbc),
            *extra_args,
            "--placement-gap",
            str(float(args.gap)),
            "--placement-step",
            str(float(args.placement_step)),
            "--placement-max-distance",
            str(float(args.placement_max_distance)),
            "--input-sha256",
            staged_input_sha256,
            "--emit-geompy-normals",
        ]
    else:
        # Legacy reference engine: -a = weighted-alpha factor, --precursor-radius = probe radius.
        command = [
            str(exe.resolve()),
            "-f",
            str(prepared_poscar.resolve()),
            "-a",
            str(engine_alpha),
            "--pbc",
            pbc_mask_to_cli(pbc),
            *extra_args,
            "--precursor-radius",
            str(float(args.adsorbate_radius)),
            "--placement-gap",
            str(float(args.gap)),
            "--placement-step",
            str(float(args.placement_step)),
            "--placement-max-distance",
            str(float(args.placement_max_distance)),
            "--emit-geompy-normals",
        ]
    # Public, IP-minimal metadata: parameters + provenance hashes only. Engine path/command,
    # backend/mode names, and full graph metadata are NEVER written to the public output;
    # they are preserved under engine_run/ only when --debug is set.
    metadata: dict[str, Any] = {
        "input": input_path.name,
        "adsorbate_radius": float(args.adsorbate_radius),
        "engine_cli": args.engine_cli,
        "alpha_factor": float(args.alpha_factor),
        "engine_alpha": engine_alpha,
        "pbc": pbc,
        "pbc_label": pbc_label,
        "gap": float(args.gap),
        "dedup_distance": float(args.dedup_distance),
        "placement_step": float(args.placement_step),
        "placement_max_distance": float(args.placement_max_distance),
        "candidate_distance": float(args.candidate_distance),
        "normal_source": args.normal_source,
        "open_axis_side": args.open_axis_side,
        "engine_sha256_12": sha256_12(exe),
        "staged_input_sha256": staged_input_sha256,
        "site_filter_policy": "regular_p1_p2_with_p0_top_exception_v1",
    }

    # engine_command.txt exposes the exact invocation (flags, construction mode);
    # keep it only for debug or dry-run preview.
    if args.debug or args.dry_run:
        (out_dir / "engine_command.txt").write_text(command_to_string(command) + "\n", encoding="utf-8")

    if args.dry_run:
        payload = {"metadata": metadata, "counts": {"top": 0, "bridge": 0, "hollow": 0, "total": 0}, "sites": []}
        write_json(out_dir / "regular_adsorption_sites.json", payload)
        print(out_dir / "regular_adsorption_sites.json")
        return 0

    # Run the engine in a PRIVATE temp dir; the full geometric graph (nodes/edges/metadata)
    # is a transient internal artifact and is NOT persisted to the public output.
    run_dir = Path(tempfile.mkdtemp(prefix="wa_run_"))
    keep_dir = ensure_dir(out_dir / "engine_run") if args.debug else None
    try:
        if args.engine_cli == "new":
            cpp_run = run_engine_command(command, run_dir, int(args.timeout_seconds))
        else:
            from fig3_common import run_weighted_alpha  # type: ignore  # noqa: WPS433

            cpp_run = run_weighted_alpha(
                executable=exe,
                input_poscar=prepared_poscar,
                run_dir=run_dir,
                alpha=engine_alpha,
                pbc=pbc,
                emit_geompy=True,
                precursor_radius=float(args.adsorbate_radius),
                placement_gap=float(args.gap),
                placement_step=float(args.placement_step),
                placement_max_distance=float(args.placement_max_distance),
                timeout_seconds=int(args.timeout_seconds),
                extra_args=extra_args,
            )

        if cpp_run["returncode"] != 0 or not cpp_run["graph_exists"]:
            # On failure surface only the logs (not the graph) so the run is debuggable.
            fail_dir = ensure_dir(out_dir / "engine_run")
            for name in ("weighted_alpha_stdout.log", "weighted_alpha_stderr.log"):
                src = run_dir / name
                if src.exists():
                    shutil.copy2(src, fail_dir / name)
            payload = {"metadata": metadata, "counts": {"top": 0, "bridge": 0, "hollow": 0, "total": 0}, "sites": [], "error": "engine run failed"}
            write_json(out_dir / "regular_adsorption_sites.json", payload)
            raise RuntimeError(f"engine run failed; see logs in {fail_dir}")

        graph_data = read_json(Path(cpp_run["graph_json"]))
        extraction = extract_regular_sites(
            graph_data,
            adsorbate_radius=float(args.adsorbate_radius),
            gap=float(args.gap),
            pbc=pbc,
            normal_source=args.normal_source,
            dedup_distance=float(args.dedup_distance),
            candidate_distance=float(args.candidate_distance),
            open_axis_side=args.open_axis_side,
        )
        framework_atoms = extract_framework_atoms(graph_data)

        # --debug only: preserve full engine artifacts + internal metadata for private audit.
        if keep_dir is not None:
            for item in run_dir.iterdir():
                if item.is_file():
                    shutil.copy2(item, keep_dir / item.name)
            write_json(
                keep_dir / "debug_metadata.json",
                {
                    "engine_executable": str(exe.resolve()),
                    "radius_file": str(radius_file.resolve()),
                    "engine_command": command_to_string(command),
                    "conversion": conversion,
                    "cpp_run": cpp_run,
                    "graph_metadata_subset": {
                        key: graph_data.get("metadata", {}).get(key)
                        for key in (
                            "requested_construction_mode", "resolved_backend", "legacy_equivalent_mode",
                            "p2_topology_invalid_count", "p0_count", "p1_count", "p2_count", "p3_count",
                            "pbc110_p2_geometry_split_mode", "p2_geometry_split",
                        )
                        if key in graph_data.get("metadata", {})
                    },
                },
            )
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)

    payload = {
        "metadata": metadata,
        "counts": extraction["counts"],
        "rejected": extraction["rejected"],
        "framework_atom_count": extraction["framework_atom_count"],
        "raw_site_count": extraction["raw_site_count"],
        "sites": extraction["sites"],
    }
    json_path = out_dir / "regular_adsorption_sites.json"
    csv_path = out_dir / "regular_adsorption_sites.csv"
    xyz_path = out_dir / "regular_adsorption_sites.xyz"
    html_sample_path = out_dir / f"regular_adsorption_sites_{args.sample_per_kind}each.html"
    write_json(json_path, payload)
    write_sites_csv(csv_path, extraction["sites"])
    write_sites_xyz(xyz_path, extraction["sites"])
    selected = select_sites_for_html(extraction["sites"], per_kind=int(args.sample_per_kind))
    write_html(html_sample_path, framework_atoms, selected, metadata)
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {xyz_path}")
    print(f"Wrote {html_sample_path}")
    print(f"Counts {payload['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
