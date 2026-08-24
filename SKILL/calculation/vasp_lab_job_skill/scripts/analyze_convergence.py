#!/usr/bin/env python3
"""Analyze VASP k-point or ENCUT convergence directories.

Examples:
  python scripts/analyze_convergence.py --type kpoint --root slab/kconv --write slab_convergence.yml
  python scripts/analyze_convergence.py --type encut --root slab/encut_conv --selected-settings slab_convergence.yml --write slab_convergence.yml
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from vasp_lab_common import SkillError, load_defaults, load_yaml, write_yaml

TOTEN_RE = re.compile(r"free\s+energy\s+TOTEN\s*=\s*([-+0-9.Ee]+)\s+eV")
OSZICAR_F_RE = re.compile(r"\bF=\s*([-+0-9.Ee]+)")


def read_text(path: Path) -> str:
    return path.read_text(errors="ignore") if path.is_file() else ""


def final_energy(calc_dir: Path) -> float | None:
    outcar = read_text(calc_dir / "OUTCAR")
    values = [float(x) for x in TOTEN_RE.findall(outcar)]
    if values:
        return values[-1]
    oszicar = read_text(calc_dir / "OSZICAR")
    vals = [float(x) for x in OSZICAR_F_RE.findall(oszicar)]
    return vals[-1] if vals else None


def parse_kdir(path: Path) -> tuple[list[int], int] | None:
    m = re.fullmatch(r"k(\d)(\d)(\d)", path.name)
    if not m:
        return None
    return [int(m.group(1)), int(m.group(2)), int(m.group(3))], int(m.group(1))


def parse_encut_dir(path: Path) -> int | None:
    m = re.fullmatch(r"encut(\d+)", path.name)
    return int(m.group(1)) if m else None


def collect(root: Path, kind: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for d in sorted([p for p in root.iterdir() if p.is_dir()]):
        if kind == "kpoint":
            parsed = parse_kdir(d)
            if not parsed:
                continue
            kpts, sort_value = parsed
            label = kpts
        else:
            encut = parse_encut_dir(d)
            if encut is None:
                continue
            sort_value = encut
            label = encut
        energy = final_energy(d)
        rows.append({"directory": str(d), "value": label, "sort_value": sort_value, "energy_eV": energy})
    rows.sort(key=lambda r: r["sort_value"])
    return rows


def add_deltas(rows: list[dict[str, Any]]) -> None:
    for i, row in enumerate(rows):
        if i + 1 < len(rows) and row["energy_eV"] is not None and rows[i + 1]["energy_eV"] is not None:
            row["delta_to_next_eV"] = abs(float(row["energy_eV"]) - float(rows[i + 1]["energy_eV"]))
        else:
            row["delta_to_next_eV"] = None


def select_value(rows: list[dict[str, Any]], tolerance: float) -> dict[str, Any] | None:
    for row in rows:
        delta = row.get("delta_to_next_eV")
        if delta is not None and float(delta) <= tolerance:
            return row
    return None


def merge_selected(write_path: Path, kind: str, selected: dict[str, Any], tolerance: float, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if write_path.exists():
        data = load_yaml(write_path)
    else:
        data = {}
    conv = data.setdefault("slab_convergence", {})
    if kind == "kpoint":
        conv["selected_kpts"] = selected["value"]
        conv["kpoint_tolerance_eV"] = tolerance
        conv["kpoint_table"] = rows
    else:
        conv["selected_encut"] = selected["value"]
        conv["encut_tolerance_eV"] = tolerance
        conv["encut_table"] = rows
    write_yaml(write_path, data)
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze VASP convergence directories.")
    parser.add_argument("--type", required=True, choices=["kpoint", "encut"])
    parser.add_argument("--root", required=True, help="Root directory, e.g. slab/kconv or slab/encut_conv")
    parser.add_argument("--tolerance", type=float, default=None)
    parser.add_argument("--defaults", default=str(Path(__file__).resolve().parent.parent / "references" / "defaults.yaml"))
    parser.add_argument("--write", help="Write/update selected settings YAML.")
    args = parser.parse_args()

    try:
        root = Path(args.root).expanduser().resolve()
        if not root.is_dir():
            raise SkillError(f"Root directory not found: {root}")
        defaults = load_defaults(args.defaults)
        tolerance = float(args.tolerance if args.tolerance is not None else defaults.get("convergence", {}).get("default_tolerance_eV", 0.02))
        rows = collect(root, args.type)
        if not rows:
            raise SkillError(f"No {args.type} directories found under {root}")
        add_deltas(rows)
        selected = select_value(rows, tolerance)
        result: dict[str, Any] = {"ok": True, "type": args.type, "root": str(root), "tolerance_eV": tolerance, "table": rows, "selected": selected}
        if selected and args.write:
            result["written_settings"] = merge_selected(Path(args.write), args.type, selected, tolerance, rows)
    except SkillError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
