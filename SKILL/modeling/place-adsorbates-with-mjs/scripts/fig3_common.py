#!/usr/bin/env python3
"""Shared helpers for Application 1 / Fig.3 scripts."""

from __future__ import annotations

import csv
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import time
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any


AVOGADRO = 6.02214076e23

VDW_RADII = {
    "H": 1.20,
    "C": 1.70,
    "N": 1.55,
    "O": 1.52,
    "F": 1.47,
    "P": 1.80,
    "S": 1.80,
    "Cl": 1.75,
    "Br": 1.85,
    "I": 1.98,
    "Si": 2.10,
    "Al": 1.84,
    "Fe": 2.00,
    "Sr": 2.49,
    "Pt": 1.75,
    "Zn": 1.39,
    "Cu": 1.40,
    "Zr": 2.23,
    "Na": 2.27,
    "Li": 1.82,
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Config must be an object: {path}")
    return data


def resolve_path(value: str | os.PathLike[str] | None, base: Path | None = None) -> Path | None:
    if value in (None, ""):
        return None
    raw = os.path.expandvars(str(value))
    path = Path(raw)
    if path.is_absolute():
        return path
    return (base or repo_root()) / path


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def vec(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    try:
        return [float(value[0]), float(value[1]), float(value[2])]
    except (TypeError, ValueError):
        return None


def v_add(a: list[float], b: list[float]) -> list[float]:
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def v_sub(a: list[float], b: list[float]) -> list[float]:
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def v_mul(a: list[float], scale: float) -> list[float]:
    return [a[0] * scale, a[1] * scale, a[2] * scale]


def v_dot(a: list[float], b: list[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_mag(a: list[float]) -> float:
    return math.sqrt(v_dot(a, a))


def v_norm(a: list[float]) -> list[float] | None:
    mag = v_mag(a)
    if mag <= 1.0e-12:
        return None
    return [a[0] / mag, a[1] / mag, a[2] / mag]


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def stdev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    avg = sum(values) / len(values)
    return math.sqrt(sum((x - avg) ** 2 for x in values) / (len(values) - 1))


def stats_dict(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "min": min(values) if values else None,
        "mean": mean(values),
        "median": median(values),
        "max": max(values) if values else None,
        "stdev": stdev(values),
    }


def row_vec_mat(value: list[float], matrix: list[list[float]]) -> list[float]:
    return [
        value[0] * matrix[0][0] + value[1] * matrix[1][0] + value[2] * matrix[2][0],
        value[0] * matrix[0][1] + value[1] * matrix[1][1] + value[2] * matrix[2][1],
        value[0] * matrix[0][2] + value[1] * matrix[1][2] + value[2] * matrix[2][2],
    ]


def inverse_3x3(matrix: list[list[float]]) -> list[list[float]]:
    a, b, c = matrix[0]
    d, e, f = matrix[1]
    g, h, i = matrix[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) <= 1.0e-14:
        raise ValueError("singular cell matrix")
    inv_det = 1.0 / det
    return [
        [(e * i - f * h) * inv_det, (c * h - b * i) * inv_det, (b * f - c * e) * inv_det],
        [(f * g - d * i) * inv_det, (a * i - c * g) * inv_det, (c * d - a * f) * inv_det],
        [(d * h - e * g) * inv_det, (b * g - a * h) * inv_det, (a * e - b * d) * inv_det],
    ]


def full_cell_minimum_image_delta(
    a: list[float],
    b: list[float],
    cell: list[list[float]],
    pbc: list[bool] | None,
) -> list[float]:
    delta = v_sub(a, b)
    frac_delta = row_vec_mat(delta, inverse_3x3(cell))
    axes = pbc or [True, True, True]
    for i in range(3):
        if axes[i]:
            frac_delta[i] -= round(frac_delta[i])
    return row_vec_mat(frac_delta, cell)


def minimum_image_delta(
    a: list[float],
    b: list[float],
    box: list[float] | None,
    pbc: list[bool] | None,
    cell: list[list[float]] | None = None,
) -> list[float]:
    if cell is not None:
        try:
            return full_cell_minimum_image_delta(a, b, cell, pbc)
        except ValueError:
            pass
    delta = v_sub(a, b)
    if not box:
        return delta
    axes = pbc or [True, True, True]
    for i in range(3):
        length = float(box[i]) if i < len(box) else 0.0
        if not axes[i] or length <= 1.0e-12:
            continue
        if delta[i] > 0.5 * length:
            delta[i] -= length
        elif delta[i] < -0.5 * length:
            delta[i] += length
    return delta


def pbc_distance(
    a: list[float],
    b: list[float],
    box: list[float] | None,
    pbc: list[bool] | None,
    cell: list[list[float]] | None = None,
) -> float:
    return v_mag(minimum_image_delta(a, b, box, pbc, cell=cell))


def graph_nodes(data: dict[str, Any], node_type: str | None = None) -> list[dict[str, Any]]:
    nodes = [n for n in data.get("nodes", []) if isinstance(n, dict)]
    if node_type is None:
        return nodes
    return [n for n in nodes if n.get("type") == node_type]


def graph_box(data: dict[str, Any]) -> list[float] | None:
    metadata = data.get("metadata", {})
    box = vec(metadata.get("box_dimensions"))
    if box:
        return box
    cell = metadata.get("cell")
    if isinstance(cell, list) and len(cell) == 3:
        rows = [vec(row) for row in cell]
        if all(rows):
            return [v_mag(row) for row in rows if row is not None]
    return None


def graph_cell(data: dict[str, Any]) -> list[list[float]] | None:
    cell = data.get("metadata", {}).get("cell")
    if isinstance(cell, list) and len(cell) == 3:
        rows = [vec(row) for row in cell]
        if all(rows):
            return [row for row in rows if row is not None]
    return None


def graph_pbc(data: dict[str, Any], default: list[bool] | None = None) -> list[bool]:
    raw = data.get("metadata", {}).get("pbc")
    if isinstance(raw, list) and len(raw) == 3:
        return [bool(x) for x in raw]
    return list(default or [True, True, True])


def normal_from_node(node: dict[str, Any], normal_source: str) -> list[float] | None:
    if normal_source == "geompy":
        geompy = node.get("geompy_normal")
        if isinstance(geompy, dict) and geompy.get("valid", True) is not False:
            raw = vec(geompy.get("unit"))
            return v_norm(raw) if raw is not None else None
        return None
    if node.get("type") == "P2":
        raw = vec(node.get("normal"))
    else:
        raw = vec(node.get("surface_normal"))
    return v_norm(raw) if raw is not None else None


def extract_framework_atoms(data: dict[str, Any]) -> list[dict[str, Any]]:
    atoms = []
    for node in graph_nodes(data, "P0"):
        pos = vec(node.get("position"))
        if pos is None:
            continue
        element = str(node.get("element") or "X")
        try:
            radius = float(node.get("atom_radius", node.get("value", VDW_RADII.get(element, 1.5))))
        except (TypeError, ValueError):
            radius = VDW_RADII.get(element, 1.5)
        atoms.append(
            {
                "id": node.get("id"),
                "element": element,
                "position": pos,
                "atom_radius": radius,
            }
        )
    return atoms


def sanitize_id(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return value.strip("._") or "structure"


def command_to_string(command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)


def run_weighted_alpha(
    executable: Path,
    input_poscar: Path,
    run_dir: Path,
    alpha: float,
    pbc: list[int] | list[bool],
    emit_geompy: bool = True,
    precursor_radius: float | None = None,
    placement_gap: float | None = None,
    placement_step: float | None = None,
    placement_max_distance: float | None = None,
    timeout_seconds: int = 300,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    ensure_dir(run_dir)
    command = [
        str(executable.resolve()),
        "-f",
        str(input_poscar.resolve()),
        "-a",
        str(alpha),
        "--pbc",
        ",".join("1" if bool(x) else "0" for x in pbc),
    ]
    if extra_args:
        command += [str(x) for x in extra_args]
    if precursor_radius is not None:
        command += ["--precursor-radius", str(precursor_radius)]
    if placement_gap is not None:
        command += ["--placement-gap", str(placement_gap)]
    if placement_step is not None:
        command += ["--placement-step", str(placement_step)]
    if placement_max_distance is not None:
        command += ["--placement-max-distance", str(placement_max_distance)]
    if emit_geompy:
        command.append("--emit-geompy-normals")

    start = time.perf_counter()
    result = subprocess.run(
        command,
        cwd=run_dir,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    runtime = time.perf_counter() - start
    (run_dir / "weighted_alpha_stdout.log").write_text(result.stdout, encoding="utf-8")
    (run_dir / "weighted_alpha_stderr.log").write_text(result.stderr, encoding="utf-8")
    graph = run_dir / ("weighted_alpha_graph_geompy_normals.json" if emit_geompy else "weighted_alpha_graph.json")
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


def clean_cif_token(value: str) -> str:
    value = value.strip().strip("'\"")
    value = re.sub(r"\([0-9]+\)$", "", value)
    return value


def parse_float_token(value: str) -> float:
    value = clean_cif_token(value)
    if value in {".", "?"}:
        raise ValueError("missing numeric CIF token")
    return float(value)


def lattice_from_lengths_angles(a: float, b: float, c: float, alpha: float, beta: float, gamma: float) -> list[list[float]]:
    ar = math.radians(alpha)
    br = math.radians(beta)
    gr = math.radians(gamma)
    ax = a
    bx = b * math.cos(gr)
    by = b * math.sin(gr)
    cx = c * math.cos(br)
    cy = c * (math.cos(ar) - math.cos(br) * math.cos(gr)) / max(math.sin(gr), 1.0e-12)
    cz2 = max(c * c - cx * cx - cy * cy, 0.0)
    cz = math.sqrt(cz2)
    return [[ax, 0.0, 0.0], [bx, by, 0.0], [cx, cy, cz]]


def frac_to_cart(frac: list[float], cell: list[list[float]]) -> list[float]:
    return [
        frac[0] * cell[0][0] + frac[1] * cell[1][0] + frac[2] * cell[2][0],
        frac[0] * cell[0][1] + frac[1] * cell[1][1] + frac[2] * cell[2][1],
        frac[0] * cell[0][2] + frac[1] * cell[1][2] + frac[2] * cell[2][2],
    ]


def parse_cif(path: Path) -> tuple[list[list[float]], list[dict[str, Any]], list[str]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    scalars: dict[str, str] = {}
    warnings: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or not stripped.startswith("_"):
            continue
        parts = stripped.split(None, 1)
        if len(parts) == 2:
            scalars[parts[0].lower()] = parts[1].strip()

    a = parse_float_token(scalars["_cell_length_a"])
    b = parse_float_token(scalars["_cell_length_b"])
    c = parse_float_token(scalars["_cell_length_c"])
    alpha = parse_float_token(scalars.get("_cell_angle_alpha", "90"))
    beta = parse_float_token(scalars.get("_cell_angle_beta", "90"))
    gamma = parse_float_token(scalars.get("_cell_angle_gamma", "90"))
    if max(abs(alpha - 90.0), abs(beta - 90.0), abs(gamma - 90.0)) > 1.0e-6:
        warnings.append("nonorthogonal CIF cell converted to POSCAR, but current C++ PBC uses orthorhombic box lengths")
    cell = lattice_from_lengths_angles(a, b, c, alpha, beta, gamma)

    atoms: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        if lines[i].strip().lower() != "loop_":
            i += 1
            continue
        i += 1
        headers = []
        while i < len(lines) and lines[i].strip().startswith("_"):
            headers.append(lines[i].strip().lower())
            i += 1
        if not headers or not any(h.startswith("_atom_site_") for h in headers):
            continue
        header_index = {name: idx for idx, name in enumerate(headers)}
        fx = header_index.get("_atom_site_fract_x")
        fy = header_index.get("_atom_site_fract_y")
        fz = header_index.get("_atom_site_fract_z")
        type_idx = header_index.get("_atom_site_type_symbol")
        label_idx = header_index.get("_atom_site_label")
        if fx is None or fy is None or fz is None:
            continue
        while i < len(lines):
            stripped = lines[i].strip()
            if not stripped or stripped.startswith("#"):
                i += 1
                continue
            if stripped.lower() == "loop_" or stripped.startswith("_"):
                break
            try:
                tokens = shlex.split(stripped, posix=True)
            except ValueError:
                tokens = stripped.split()
            if len(tokens) >= len(headers):
                raw_element = tokens[type_idx] if type_idx is not None else tokens[label_idx or 0]
                element_match = re.match(r"([A-Z][a-z]?)", clean_cif_token(raw_element))
                element = element_match.group(1) if element_match else "X"
                frac = [parse_float_token(tokens[fx]), parse_float_token(tokens[fy]), parse_float_token(tokens[fz])]
                atoms.append({"element": element, "frac": frac, "position": frac_to_cart(frac, cell)})
            i += 1
    if not atoms:
        raise ValueError(f"No atom_site fractional coordinates parsed from CIF: {path}")
    return cell, atoms, warnings


def write_poscar(path: Path, comment: str, cell: list[list[float]], atoms: list[dict[str, Any]], direct: bool = False) -> None:
    ensure_dir(path.parent)
    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for atom in atoms:
        grouped.setdefault(str(atom["element"]), []).append(atom)
    lines = [comment, " 1.0000000000000000"]
    for row in cell:
        lines.append(" " + " ".join(f"{float(x):20.16f}" for x in row))
    lines.append(" " + " ".join(grouped.keys()))
    lines.append(" " + " ".join(str(len(items)) for items in grouped.values()))
    lines.append("Direct" if direct else "Cartesian")
    for items in grouped.values():
        for atom in items:
            coords = atom.get("frac") if direct else atom.get("position")
            if coords is None:
                raise ValueError("Atom is missing coordinates")
            lines.append(" " + " ".join(f"{float(x):20.16f}" for x in coords[:3]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_poscar_atoms(path: Path) -> tuple[list[list[float]], list[dict[str, Any]]]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    scale_tokens = lines[1].split()
    scale = float(scale_tokens[0])
    cell = [[float(x) * scale for x in lines[i].split()[:3]] for i in range(2, 5)]
    elements = lines[5].split()
    counts = [int(x) for x in lines[6].split()]
    idx = 7
    if lines[idx].lower().startswith("s"):
        idx += 1
    coord = lines[idx].lower()
    idx += 1
    atoms = []
    for element, count in zip(elements, counts):
        for _ in range(count):
            values = [float(x) for x in lines[idx].split()[:3]]
            idx += 1
            pos = frac_to_cart(values, cell) if coord.startswith("d") else values
            atoms.append({"element": element, "position": pos})
    return cell, atoms


def cif_to_poscar(cif_path: Path, poscar_path: Path, comment: str | None = None) -> dict[str, Any]:
    cell, atoms, warnings = parse_cif(cif_path)
    write_poscar(poscar_path, comment or cif_path.stem, cell, atoms, direct=False)
    return {"input": str(cif_path), "output": str(poscar_path), "atom_count": len(atoms), "warnings": warnings}


def prepare_poscar_input(input_path: Path, run_dir: Path, structure_id: str) -> dict[str, Any]:
    ensure_dir(run_dir)
    target = run_dir / f"{sanitize_id(structure_id)}.POSCAR"
    suffix = input_path.suffix.lower()
    if suffix == ".cif":
        info = cif_to_poscar(input_path, target, comment=structure_id)
        info["format"] = "cif"
        return info
    if suffix in {".vasp", ".poscar", ""} or input_path.name.upper().startswith("POSCAR"):
        shutil.copyfile(input_path, target)
        return {"input": str(input_path), "output": str(target), "format": "poscar", "warnings": []}
    shutil.copyfile(input_path, target)
    return {"input": str(input_path), "output": str(target), "format": "unknown-copied", "warnings": []}


def generate_c60_poscar(path: Path, radius: float = 3.55, box_size: float = 20.0) -> dict[str, Any]:
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    even_perms = [(0, 1, 2), (1, 2, 0), (2, 0, 1)]
    bases = [
        (0.0, 1.0, 3.0 * phi),
        (1.0, 2.0 + phi, 2.0 * phi),
        (phi, 2.0, 1.0 + 2.0 * phi),
    ]
    points = []
    seen = set()
    for base in bases:
        sign_ranges = [[1] if abs(x) < 1.0e-12 else [-1, 1] for x in base]
        for sx in sign_ranges[0]:
            for sy in sign_ranges[1]:
                for sz in sign_ranges[2]:
                    signed = (sx * base[0], sy * base[1], sz * base[2])
                    for perm in even_perms:
                        p = (signed[perm[0]], signed[perm[1]], signed[perm[2]])
                        key = tuple(round(x, 10) for x in p)
                        if key not in seen:
                            seen.add(key)
                            points.append(list(p))
    if len(points) != 60:
        raise RuntimeError(f"Generated {len(points)} C60 points, expected 60")
    avg_radius = mean([v_mag(p) for p in points]) or 1.0
    scale = radius / avg_radius
    center = [box_size / 2.0] * 3
    atoms = [{"element": "C", "position": v_add(center, v_mul(p, scale))} for p in points]
    cell = [[box_size, 0.0, 0.0], [0.0, box_size, 0.0], [0.0, 0.0, box_size]]
    write_poscar(path, "C60 generated truncated-icosahedron demo", cell, atoms, direct=False)
    return {"output": str(path), "atom_count": len(atoms), "radius": radius, "box_size": box_size}


def write_placeholder_png(path: Path) -> None:
    import base64

    ensure_dir(path.parent)
    data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    path.write_bytes(data)


def write_png_html_fallback(html_path: Path, png_path: Path, title: str) -> None:
    rel = os.path.relpath(png_path, html_path.parent)
    html_path.write_text(
        f"<!doctype html><meta charset='utf-8'><title>{title}</title>"
        f"<h1>{title}</h1><img src='{rel}' style='max-width:100%;height:auto'>\n",
        encoding="utf-8",
    )


def detect_topology_blockers(root: Path) -> list[str]:
    blocker_files = [
        root / "reports" / "pbc_geometry_audit_after_fix.md",
        root / "reports" / "p3_outward_normal_validation.md",
    ]
    patterns = [
        "topology/canonicalization issue remains",
        "shared p2/p3 topology",
        "still failing / suspicious",
        "pair entries not opposite",
        "opposite-normal invariant still fails",
        "stronger invariant",
    ]
    blockers = []
    for path in blocker_files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        matched = [pattern for pattern in patterns if pattern in text]
        if matched:
            blockers.append(f"{path}: matched {', '.join(matched)}")
    return blockers


def classification_allowed(node: dict[str, Any], allowed: list[str]) -> bool:
    cls = str(node.get("classification", "")).lower()
    return cls in {item.lower() for item in allowed}


def cell_volume_from_graph(data: dict[str, Any]) -> float | None:
    metadata = data.get("metadata", {})
    cell = metadata.get("cell")
    if isinstance(cell, list) and len(cell) == 3:
        rows = [vec(row) for row in cell]
        if all(rows):
            a, b, c = rows  # type: ignore[misc]
            return abs(
                a[0] * (b[1] * c[2] - b[2] * c[1])
                - a[1] * (b[0] * c[2] - b[2] * c[0])
                + a[2] * (b[0] * c[1] - b[1] * c[0])
            )
    box = graph_box(data)
    if box:
        return box[0] * box[1] * box[2]
    return None


def normalized_csv_fieldnames(fieldnames: list[str] | None) -> dict[str, str]:
    result = {}
    for name in fieldnames or []:
        result[name.strip().lower()] = name
    return result


def get_csv_value(row: dict[str, str], mapping: dict[str, str], aliases: list[str]) -> str | None:
    for alias in aliases:
        key = mapping.get(alias.lower())
        if key is not None and row.get(key, "").strip() != "":
            return row[key].strip()
    return None


def safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value))
    except ValueError:
        return None
