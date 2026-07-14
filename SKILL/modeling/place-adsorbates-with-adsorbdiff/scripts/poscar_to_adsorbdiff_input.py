#!/usr/bin/env python3
"""Prepare a user POSCAR as an AdsorbDiff slab input with tag metadata."""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_ID = "place-adsorbates-with-adsorbdiff.poscar-prepare"


def parse_float_tokens(line: str, expected: int | None = None) -> list[float]:
    values = [float(token) for token in line.split()]
    if expected is not None and len(values) != expected:
        raise ValueError(f"expected {expected} float values, got {len(values)}: {line}")
    return values


def parse_int_tokens(line: str) -> list[int]:
    return [int(token) for token in line.split()]


def tokens_are_ints(tokens: list[str]) -> bool:
    try:
        [int(token) for token in tokens]
        return True
    except ValueError:
        return False


def vec_len(vector: list[float]) -> float:
    return math.sqrt(sum(item * item for item in vector))


def mat_det(matrix: list[list[float]]) -> float:
    a = matrix
    return (
        a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
        - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
        + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0])
    )


def mat_inv(matrix: list[list[float]]) -> list[list[float]]:
    det = mat_det(matrix)
    if abs(det) < 1e-12:
        raise ValueError("cell matrix is singular")
    a = matrix
    return [
        [
            (a[1][1] * a[2][2] - a[1][2] * a[2][1]) / det,
            (a[0][2] * a[2][1] - a[0][1] * a[2][2]) / det,
            (a[0][1] * a[1][2] - a[0][2] * a[1][1]) / det,
        ],
        [
            (a[1][2] * a[2][0] - a[1][0] * a[2][2]) / det,
            (a[0][0] * a[2][2] - a[0][2] * a[2][0]) / det,
            (a[0][2] * a[1][0] - a[0][0] * a[1][2]) / det,
        ],
        [
            (a[1][0] * a[2][1] - a[1][1] * a[2][0]) / det,
            (a[0][1] * a[2][0] - a[0][0] * a[2][1]) / det,
            (a[0][0] * a[1][1] - a[0][1] * a[1][0]) / det,
        ],
    ]


def row_vec_mat_mul(vector: list[float], matrix: list[list[float]]) -> list[float]:
    return [
        sum(vector[i] * matrix[i][j] for i in range(3))
        for j in range(3)
    ]


def frac_to_cart(frac: list[float], cell: list[list[float]]) -> list[float]:
    return row_vec_mat_mul(frac, cell)


def cart_to_frac(cart: list[float], cell: list[list[float]]) -> list[float]:
    return row_vec_mat_mul(cart, mat_inv(cell))


def ordered_counts(symbols: list[str]) -> OrderedDict[str, int]:
    counts: OrderedDict[str, int] = OrderedDict()
    for symbol in symbols:
        counts[symbol] = counts.get(symbol, 0) + 1
    return counts


def expanded_symbols(symbols: list[str], counts: list[int]) -> list[str]:
    expanded: list[str] = []
    for symbol, count in zip(symbols, counts):
        expanded.extend([symbol] * count)
    return expanded


def parse_poscar(path: Path) -> dict[str, Any]:
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    lines = [line.rstrip() for line in raw_lines if line.strip()]
    if len(lines) < 8:
        raise ValueError("POSCAR is too short")

    comment = lines[0]
    scale_tokens = parse_float_tokens(lines[1])
    if len(scale_tokens) not in (1, 3):
        raise ValueError("POSCAR scale line must contain one or three values")
    if any(value <= 0 for value in scale_tokens):
        raise ValueError("negative or zero POSCAR scale values are not supported")

    raw_cell = [parse_float_tokens(lines[index], 3) for index in range(2, 5)]
    if len(scale_tokens) == 1:
        scale = scale_tokens[0]
        cell = [[component * scale for component in vector] for vector in raw_cell]
        cartesian_scale = [scale, scale, scale]
    else:
        cell = [
            [component * scale_tokens[i] for i, component in enumerate(vector)]
            for vector in raw_cell
        ]
        cartesian_scale = scale_tokens

    cursor = 5
    maybe_symbols = lines[cursor].split()
    if tokens_are_ints(maybe_symbols):
        counts = parse_int_tokens(lines[cursor])
        symbols = [f"X{i + 1}" for i in range(len(counts))]
        vasp5 = False
        cursor += 1
    else:
        symbols = maybe_symbols
        counts = parse_int_tokens(lines[cursor + 1])
        vasp5 = True
        cursor += 2
    if len(symbols) != len(counts):
        raise ValueError("element symbol and count lines have different lengths")

    selective = False
    if lines[cursor].lower().startswith("s"):
        selective = True
        cursor += 1

    coord_mode = lines[cursor].strip().lower()
    cursor += 1
    direct = coord_mode.startswith("d")
    cartesian = coord_mode.startswith("c") or coord_mode.startswith("k")
    if not direct and not cartesian:
        raise ValueError(f"unknown coordinate mode: {lines[cursor - 1]}")

    atom_symbols = expanded_symbols(symbols, counts)
    natoms = sum(counts)
    if len(lines) < cursor + natoms:
        raise ValueError("POSCAR does not contain enough coordinate lines")

    atoms: list[dict[str, Any]] = []
    for index in range(natoms):
        parts = lines[cursor + index].split()
        if len(parts) < 3:
            raise ValueError(f"atom line {index + 1} has fewer than 3 coordinates")
        coords = [float(parts[0]), float(parts[1]), float(parts[2])]
        flags = parts[3:6] if selective and len(parts) >= 6 else []
        if direct:
            frac = coords
            cart = frac_to_cart(frac, cell)
        else:
            cart = [coords[i] * cartesian_scale[i] for i in range(3)]
            frac = cart_to_frac(cart, cell)
        atoms.append(
            {
                "index": index,
                "symbol": atom_symbols[index],
                "frac": frac,
                "cart": cart,
                "selective_flags": flags,
            }
        )

    return {
        "comment": comment,
        "cell": cell,
        "symbols": symbols,
        "counts": counts,
        "vasp5": vasp5,
        "selective_dynamics": selective,
        "coordinate_mode": "Direct" if direct else "Cartesian",
        "atoms": atoms,
    }


def tag_surface_atoms(
    atoms: list[dict[str, Any]],
    cell: list[list[float]],
    surface_thickness_a: float,
    surface_side: str,
) -> tuple[list[int], dict[str, Any]]:
    frac_z = [atom["frac"][2] for atom in atoms]
    min_z = min(frac_z)
    max_z = max(frac_z)
    c_length = vec_len(cell[2])
    threshold_frac = surface_thickness_a / c_length if c_length > 0 else 0.0

    tags: list[int] = []
    surface_indices: list[int] = []
    for atom, z_value in zip(atoms, frac_z):
        top = z_value >= max_z - threshold_frac - 1e-9
        bottom = z_value <= min_z + threshold_frac + 1e-9
        is_surface = top if surface_side == "top" else bottom if surface_side == "bottom" else top or bottom
        tag = 1 if is_surface else 0
        tags.append(tag)
        if tag == 1:
            surface_indices.append(atom["index"])

    return tags, {
        "surface_side": surface_side,
        "surface_thickness_a": surface_thickness_a,
        "threshold_frac": threshold_frac,
        "min_frac_z": min_z,
        "max_frac_z": max_z,
        "surface_atom_indices": surface_indices,
        "surface_atom_count": len(surface_indices),
    }


def estimate_vacuum_a(atoms: list[dict[str, Any]], cell: list[list[float]]) -> float:
    frac_z = [atom["frac"][2] for atom in atoms]
    span = max(frac_z) - min(frac_z)
    return max(0.0, (1.0 - span) * vec_len(cell[2]))


def write_prepared_poscar(
    parsed: dict[str, Any],
    tags: list[int],
    output_path: Path,
    write_selective_dynamics: bool,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"AdsorbDiff prepared from {parsed['comment']}")
    lines.append("1.0")
    for vector in parsed["cell"]:
        lines.append("  " + "  ".join(f"{value: .16f}" for value in vector))
    lines.append("  " + "  ".join(parsed["symbols"]))
    lines.append("  " + "  ".join(str(value) for value in parsed["counts"]))
    if write_selective_dynamics:
        lines.append("Selective dynamics")
    lines.append("Direct")
    for atom, tag in zip(parsed["atoms"], tags):
        frac = atom["frac"]
        line = "  " + "  ".join(f"{value: .16f}" for value in frac)
        if write_selective_dynamics:
            line += "   T T T" if tag == 1 else "   F F F"
        lines.append(line)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_tags(tags: list[int], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(str(tag) for tag in tags) + "\n", encoding="utf-8")


def build_metadata(
    parsed: dict[str, Any],
    tags: list[int],
    tag_info: dict[str, Any],
    input_path: Path,
    output_poscar: Path,
    vacuum_min_a: float,
) -> dict[str, Any]:
    warnings: list[str] = []
    vacuum_a = estimate_vacuum_a(parsed["atoms"], parsed["cell"])
    if vacuum_a < vacuum_min_a:
        warnings.append(
            f"Estimated vacuum along c is {vacuum_a:.3f} A, below requested minimum {vacuum_min_a:.3f} A."
        )
    if tag_info["surface_atom_count"] == 0:
        warnings.append("No surface atoms were tagged.")
    if all(tag == 1 for tag in tags):
        warnings.append("All atoms were tagged as surface; reduce surface_thickness_a or check cell orientation.")

    formula_counts = ordered_counts([atom["symbol"] for atom in parsed["atoms"]])
    return {
        "input_poscar": str(input_path),
        "prepared_poscar": str(output_poscar),
        "natoms": len(parsed["atoms"]),
        "formula_counts": dict(formula_counts),
        "cell": parsed["cell"],
        "tags": tags,
        "tag_meaning": {"0": "subsurface_or_fixed_slab", "1": "surface_slab"},
        "surface": tag_info,
        "estimated_vacuum_a": vacuum_a,
        "warnings": warnings,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def prepare_poscar(
    input_poscar: Path,
    output_poscar: Path,
    metadata_output: Path,
    tags_output: Path,
    surface_thickness_a: float = 2.0,
    surface_side: str = "top",
    vacuum_min_a: float = 8.0,
    write_selective_dynamics: bool = True,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    artifacts: list[dict[str, str]] = []
    try:
        parsed = parse_poscar(input_poscar)
        tags, tag_info = tag_surface_atoms(
            parsed["atoms"],
            parsed["cell"],
            surface_thickness_a=surface_thickness_a,
            surface_side=surface_side,
        )
        write_prepared_poscar(parsed, tags, output_poscar, write_selective_dynamics)
        write_tags(tags, tags_output)
        metadata = build_metadata(parsed, tags, tag_info, input_poscar, output_poscar, vacuum_min_a)
        metadata_output.parent.mkdir(parents=True, exist_ok=True)
        metadata_output.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        artifacts.extend(
            [
                {"path": str(output_poscar), "kind": "prepared_poscar"},
                {"path": str(metadata_output), "kind": "poscar_metadata"},
                {"path": str(tags_output), "kind": "adsorbdiff_tags"},
            ]
        )
    except Exception as exc:  # noqa: BLE001 - command-line tool returns structured failure.
        metadata = {}
        errors.append({"type": type(exc).__name__, "message": str(exc)})

    return {
        "status": "failure" if errors else "success",
        "task_id": TASK_ID,
        "skill": "poscar_to_adsorbdiff_input",
        "data": metadata,
        "artifacts": artifacts,
        "messages": metadata.get("warnings", []) if isinstance(metadata, dict) else [],
        "errors": errors,
        "provenance": {
            "inputs": [str(input_poscar)],
            "generated_files": [item["path"] for item in artifacts],
        },
        "next_action": {
            "recommendation": "fix_poscar" if errors else "check_adsorbate",
            "reason": "POSCAR preparation failed." if errors else "Prepared slab POSCAR and tag metadata are available.",
        },
    }


def self_test() -> int:
    text = """Pt slab
1.0
2.8 0.0 0.0
0.0 2.8 0.0
0.0 0.0 18.0
Pt
4
Direct
0.0 0.0 0.25
0.5 0.0 0.25
0.0 0.5 0.42
0.5 0.5 0.42
"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        poscar = root / "POSCAR"
        poscar.write_text(text, encoding="utf-8")
        result = prepare_poscar(
            input_poscar=poscar,
            output_poscar=root / "prepared" / "POSCAR",
            metadata_output=root / "results" / "metadata.json",
            tags_output=root / "results" / "tags.txt",
        )
        if result["status"] != "success":
            print(json.dumps(result, indent=2))
            return 1
        tags = result["data"]["tags"]
        if tags != [0, 0, 1, 1]:
            print(f"unexpected tags: {tags}")
            return 1
    print("self-test passed")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Input POSCAR path.")
    parser.add_argument("--workdir", type=Path, default=Path("."), help="Workflow directory.")
    parser.add_argument("--output-poscar", type=Path, help="Prepared POSCAR output path.")
    parser.add_argument("--metadata-output", type=Path, help="Metadata JSON output path.")
    parser.add_argument("--tags-output", type=Path, help="Tag text output path.")
    parser.add_argument("--surface-thickness-a", type=float, default=2.0)
    parser.add_argument("--surface-side", choices=["top", "bottom", "both"], default="top")
    parser.add_argument("--vacuum-min-a", type=float, default=8.0)
    parser.add_argument("--no-selective-dynamics", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        return self_test()
    if args.input is None:
        raise SystemExit("--input is required unless --self-test is used")
    workdir = args.workdir.resolve()
    output_poscar = (args.output_poscar or workdir / "adsorbdiff_slab" / "POSCAR").resolve()
    metadata_output = (args.metadata_output or workdir / "results" / "adsorbdiff_poscar_metadata.json").resolve()
    tags_output = (args.tags_output or workdir / "results" / "adsorbdiff_tags.txt").resolve()
    result = prepare_poscar(
        input_poscar=args.input.resolve(),
        output_poscar=output_poscar,
        metadata_output=metadata_output,
        tags_output=tags_output,
        surface_thickness_a=args.surface_thickness_a,
        surface_side=args.surface_side,
        vacuum_min_a=args.vacuum_min_a,
        write_selective_dynamics=not args.no_selective_dynamics,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
