#!/usr/bin/env python3
"""Realize strategy figure candidates into source/exported/QA artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - optional runtime dependency
    Image = None
    ImageDraw = None
    ImageFont = None


EXPORT_EXTS = {".png"}
SOURCE_EXTS = {".json", ".csv", ".md", ".yaml", ".yml", ".vasp", ".cif", ".xyz", ".extxyz", ".traj"}
STRUCTURE_EXTS = {".vasp", ".cif", ".xyz", ".extxyz", ".traj"}
SKIP_LEVELS = {"si-archive"}
IDENTIFIER_COLUMNS = {"motif", "motif_class", "site", "state", "species", "label", "group", "rank"}
UNSUPPORTED_DERIVED_KEYS = ("bounded_activity_score", "activity_ranking")
UNSUPPORTED_DERIVED_TEXT = ("bounded activity score", "activity ranking", "descriptor ranking", "descriptor-ranking")
DROP = object()
PALETTE = {
    "Ni-doped": "#0072B2",
    "pristine": "#666666",
    "Overpotential": "#009E73",
    "Tafel slope": "#D55E00",
    "default": "#009E73",
    "accent": "#D55E00",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return value or "figure"


def unique(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    out: list[Any] = []
    for value in values:
        key = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def resolve_artifact(project_root: Path, artifact: str) -> Path:
    path = Path(artifact)
    if path.is_absolute():
        return path
    return project_root / path


def figure_root_from_mapping(mapping: Path) -> Path:
    if mapping.name == "figure_info.json" and mapping.parent.name == "mapping":
        return mapping.parent.parent
    return mapping.parent


def ensure_workspace(root: Path) -> None:
    for name in ("source", "exported", "qa", "realization"):
        (root / name).mkdir(parents=True, exist_ok=True)


def clear_exports(exported_dir: Path, base: str) -> None:
    if not exported_dir.exists():
        return
    for path in exported_dir.glob(f"{base}*"):
        if path.is_file():
            path.unlink()


def copy_file(src: Path, dst: Path, force: bool) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and not force:
        return dst
    shutil.copy2(src, dst)
    return dst


def unsupported_text(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in UNSUPPORTED_DERIVED_TEXT)


def unsupported_key(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in UNSUPPORTED_DERIVED_KEYS) or unsupported_text(lowered.replace("_", " "))


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if unsupported_key(str(key)):
                continue
            clean = sanitize_json_value(item)
            if clean is not DROP:
                out[key] = clean
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            clean = sanitize_json_value(item)
            if clean is not DROP:
                out.append(clean)
        return out
    if isinstance(value, str) and unsupported_text(value):
        return DROP
    return value


def copy_json_source(src: Path, dst: Path, force: bool) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and not force:
        return dst
    write_json(dst, sanitize_json_value(read_json(src)))
    return dst


def copy_csv_source(src: Path, dst: Path, force: bool) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and not force:
        return dst
    with src.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = [name for name in (reader.fieldnames or []) if not unsupported_key(name)]
        rows = [{key: row.get(key, "") for key in fieldnames} for row in reader]
    with dst.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return dst


def copy_text_source(src: Path, dst: Path, force: bool) -> Path | None:
    text = src.read_text(encoding="utf-8", errors="replace")
    if unsupported_text(text):
        return None
    return copy_file(src, dst, force)


def copy_or_sanitize_source(src: Path, dst: Path, force: bool) -> Path | None:
    suffix = src.suffix.lower()
    if suffix == ".json":
        return copy_json_source(src, dst, force)
    if suffix == ".csv":
        return copy_csv_source(src, dst, force)
    if suffix in {".md", ".yaml", ".yml"}:
        return copy_text_source(src, dst, force)
    return copy_file(src, dst, force)


def source_destination(src: Path, source_dir: Path, used: set[str], index: int) -> Path:
    name = src.name
    if name not in used:
        used.add(name)
        return source_dir / name
    context = "-".join(slug(part) for part in src.parts[-4:-1] if part not in {"", "/"})
    candidate = f"{index:02d}_{context}_{name}" if context else f"{index:02d}_{name}"
    used.add(candidate)
    return source_dir / candidate


def copy_candidate_sources(
    fig: dict[str, Any],
    project_root: Path,
    source_dir: Path,
    force: bool,
    include_exts: set[str] = SOURCE_EXTS,
    max_files: int = 24,
) -> list[Path]:
    copied: list[Path] = []
    used: set[str] = set()
    for index, artifact in enumerate(fig.get("artifacts", []), start=1):
        src = resolve_artifact(project_root, str(artifact))
        if not src.exists() or src.suffix.lower() not in include_exts:
            continue
        dst = source_destination(src, source_dir, used, index)
        copied_file = copy_or_sanitize_source(src, dst, force)
        if copied_file is None:
            continue
        copied.append(copied_file)
        if len(copied) >= max_files:
            break
    return copied


def copy_existing_exports(fig: dict[str, Any], project_root: Path, exported_dir: Path, base: str, force: bool) -> list[Path]:
    copied: list[Path] = []
    for artifact in fig.get("artifacts", []):
        src = resolve_artifact(project_root, str(artifact))
        if not src.exists() or src.suffix.lower() not in EXPORT_EXTS:
            continue
        dst = exported_dir / f"{base}.png"
        copied.append(copy_file(src, dst, force))
    return copied


def read_csv_records(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def plottable_metric_name(metric: str) -> bool:
    lowered = metric.lower()
    if lowered in IDENTIFIER_COLUMNS or unsupported_key(lowered):
        return False
    return (
        lowered.endswith("_ev")
        or "free_energy" in lowered
        or "adsorption" in lowered
        or "barrier" in lowered
        or "span" in lowered
        or "uphill" in lowered
    )


def preferred_descriptor_metrics(fig: dict[str, Any]) -> list[str]:
    text = f"{fig.get('figure_type', '')} {fig.get('title', '')}".lower()
    if any(token in text for token in ("limiting", "uphill", "step")):
        return ["largest_uphill_step_ev", "thermodynamic_span_ev"]
    if "adsorption" in text:
        return [
            "delta_g_h_ev",
            "delta_g_oh_ev",
            "delta_g_h2o_ev",
            "h2_desorption_free_energy_ev",
            "thermodynamic_span_ev",
        ]
    if "thermodynamic" in text:
        return ["thermodynamic_span_ev", "largest_uphill_step_ev"]
    return ["thermodynamic_span_ev", "largest_uphill_step_ev"]


def metric_priority(path: Path, metric: str, preferred_metrics: list[str] | None = None) -> tuple[int, int, int, str]:
    name = path.name.lower()
    stem = metric.lower()
    preferred = {item: idx for idx, item in enumerate(preferred_metrics or [])}
    preferred_rank = preferred.get(metric, 99)
    no_unit = re.sub(r"(_ev|_kcal_mol|_kj_mol)$", "", stem)
    compact_name = re.sub(r"[^a-z0-9]+", "", name)
    compact_metric = re.sub(r"[^a-z0-9]+", "", no_unit)
    if compact_metric and compact_metric in compact_name:
        return (preferred_rank, 0, len(metric), metric)
    if stem.startswith("thermodynamic_span"):
        return (preferred_rank, 1, len(metric), metric)
    if stem.startswith("largest_uphill"):
        return (preferred_rank, 2, len(metric), metric)
    if stem.startswith("delta_g_"):
        return (preferred_rank, 3, len(metric), metric)
    if "desorption" in stem:
        return (preferred_rank, 4, len(metric), metric)
    return (preferred_rank, 5, len(metric), metric)


def descriptor_metric_for_file(path: Path, columns: dict[str, str], allowed_metrics: set[str], preferred_metrics: list[str]) -> str:
    candidates = [
        metric
        for metric in columns
        if metric in allowed_metrics and plottable_metric_name(metric)
    ]
    if not candidates:
        return ""
    return sorted(candidates, key=lambda metric: metric_priority(path, metric, preferred_metrics))[0]


def find_descriptor_records(fig: dict[str, Any], project_root: Path) -> tuple[list[dict[str, Any]], str]:
    allowed_metrics = set(str(item) for item in fig.get("grounding", {}).get("quantities", []))
    if not allowed_metrics:
        return [], ""
    preferred_metrics = preferred_descriptor_metrics(fig)
    candidate_paths: list[Path] = []
    for artifact in fig.get("artifacts", []):
        path = resolve_artifact(project_root, str(artifact))
        if not path.exists():
            continue
        name = path.name.lower()
        if path.suffix.lower() == ".csv" and any(token in name for token in ("thermodynamic_span", "largest_uphill", "delta_g_", "h2_desorption")):
            candidate_paths.append(path)

    candidates: list[tuple[tuple[int, int, int, str], list[dict[str, Any]], str]] = []
    for path in candidate_paths:
        records = read_csv_records(path)
        if records and "motif" in records[0]:
            metric = descriptor_metric_for_file(path, records[0], allowed_metrics, preferred_metrics)
            if metric:
                out: list[dict[str, Any]] = []
                for rec in records:
                    try:
                        value = float(rec[metric])
                    except Exception:
                        continue
                    out.append(
                        {
                            "label": rec.get("motif", ""),
                            "group": rec.get("motif_class", ""),
                            "value": value,
                        }
                    )
                if out:
                    out.sort(key=lambda x: x["value"])
                    candidates.append((metric_priority(path, metric, preferred_metrics), out, metric))
    if candidates:
        _, records, metric = sorted(candidates, key=lambda item: item[0])[0]
        return records, metric
    return [], ""


def find_benchmark_records(fig: dict[str, Any], project_root: Path) -> list[dict[str, Any]]:
    for artifact in fig.get("artifacts", []):
        path = resolve_artifact(project_root, str(artifact))
        if not path.exists() or path.suffix.lower() != ".json":
            continue
        data = read_json(path)
        constraints = data.get("benchmark_constraints", {}) if isinstance(data, dict) else {}
        records: list[dict[str, Any]] = []
        over = constraints.get("overpotential_mV_at_10_mA_cm2", {})
        if isinstance(over, dict):
            if "MoS2" in over:
                records.append({"label": "MoS2 overpotential", "group": "Overpotential", "value": float(over["MoS2"])})
            if "Ni_doped_M300N10_5h" in over:
                records.append(
                    {"label": "Ni-doped overpotential", "group": "Overpotential", "value": float(over["Ni_doped_M300N10_5h"])}
                )
        tafel = constraints.get("tafel_slope_mV_dec", {})
        if isinstance(tafel, dict):
            if "undoped_or_M100_reference" in tafel:
                records.append(
                    {"label": "M100 Tafel slope", "group": "Tafel slope", "value": float(tafel["undoped_or_M100_reference"])}
                )
            if "Ni_doped_M300N10_5h" in tafel:
                records.append({"label": "Ni-doped Tafel slope", "group": "Tafel slope", "value": float(tafel["Ni_doped_M300N10_5h"])})
        if records:
            return records
    return []


def value_axis_label(metric: str) -> str:
    labels = {
        "thermodynamic_span_ev": "thermodynamic span (eV)",
        "largest_uphill_step_ev": "largest uphill step (eV)",
    }
    return labels.get(metric, metric.replace("_ev", " (eV)").replace("_", " "))


def nice_label(text: str) -> str:
    return text.replace("ni_", "Ni ").replace("_", " ").replace("mos2", "MoS2")


def bar_chart_png(records: list[dict[str, Any]], title: str, value_label: str, out: Path, width: int = 920, height: int = 520) -> Path | None:
    if Image is None or ImageDraw is None:
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    try:
        font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        font_bold = ImageFont.truetype("DejaVuSans-Bold.ttf", 14)
        font = ImageFont.truetype("DejaVuSans.ttf", 12)
        font_label = ImageFont.truetype("DejaVuSans.ttf", 13)
    except Exception:
        font_title = font_bold = font = font_label = None

    margin_l, margin_r, margin_t, margin_b = 190, 42, 72, 96
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b
    values = [float(r["value"]) for r in records] if records else [0.0]
    min_value = min(0.0, min(values))
    max_value = max(0.0, max(values))
    span = max_value - min_value
    if span == 0:
        span = max(abs(max_value), 1.0)
        min_value -= 0.5 * span
        max_value += 0.5 * span
    pad = 0.08 * (max_value - min_value)
    min_value -= pad
    max_value += pad
    span = max_value - min_value
    zero_x = margin_l + (0.0 - min_value) / span * plot_w
    bar_h = min(46, max(18, plot_h / max(len(records), 1) * 0.62))
    gap = (plot_h - bar_h * len(records)) / max(len(records) + 1, 1)
    draw.text((margin_l, 18), title, fill="#111111", font=font_title)
    draw.text((margin_l, height - 42), value_label, fill="#111111", font=font_bold)
    draw.line((margin_l, margin_t + plot_h, margin_l + plot_w, margin_t + plot_h), fill="#222222", width=1)
    draw.line((zero_x, margin_t, zero_x, margin_t + plot_h), fill="#222222", width=1)
    for i in range(6):
        value = min_value + span * i / 5
        x = margin_l + plot_w * i / 5
        draw.line((x, margin_t, x, margin_t + plot_h), fill="#e5e5e5", width=1)
        draw.text((x - 12, margin_t + plot_h + 8), f"{value:.1f}", fill="#333333", font=font)
    for idx, rec in enumerate(records):
        value = float(rec["value"])
        y = margin_t + gap + idx * (bar_h + gap)
        value_x = margin_l + (value - min_value) / span * plot_w
        x = min(zero_x, value_x)
        w = abs(value_x - zero_x)
        color = PALETTE.get(str(rec.get("group", "")), PALETTE["default"])
        label = nice_label(str(rec["label"]))
        draw.text((10, y + bar_h * 0.28), label[:28], fill="#111111", font=font_label)
        draw.rectangle((x, y, x + w, y + bar_h), fill=color)
        text_x = value_x + 7 if value >= 0 else value_x - 42
        draw.text((text_x, y + bar_h * 0.28), f"{value:.2f}", fill="#111111", font=font)
    img.save(out)
    return out


def structure_manifest(fig: dict[str, Any], project_root: Path, out: Path) -> Path:
    all_structures = []
    seen: set[str] = set()
    for artifact in fig.get("artifacts", []):
        path = resolve_artifact(project_root, str(artifact))
        if not path.exists():
            continue
        name = path.name.lower()
        if path.suffix.lower() in STRUCTURE_EXTS or name in {"poscar", "contcar"}:
            key = str(path)
            if key not in seen:
                seen.add(key)
                all_structures.append(path)
    preferred = [path for path in all_structures if "model_build/structures" in str(path)]
    structures = preferred or all_structures
    rows = [{"label": nice_label(path.parent.parent.name if path.name.lower() in {"poscar", "contcar"} else path.parent.name)} for path in structures]
    manifest = {
        "defaults": {"view": "side_a", "width": 720, "height": 560},
        "cols": [{"label": "Clean model"}],
        "rows": rows,
        "cells": [
            {"row": idx, "col": 0, "structure": str(path), "view": "side_a"}
            for idx, path in enumerate(structures)
        ],
        "layout": {"cell_size_in": 1.7, "label_fontsize": 8},
    }
    write_json(out, manifest)
    return out


def execution_root_for_path(path: Path) -> Path | None:
    parts = path.parts
    exec_idx = next((idx for idx, part in enumerate(parts) if part.endswith("_execution") and part != "strategy_execution"), None)
    if exec_idx is None:
        return None
    return Path(*parts[: exec_idx + 1])


def motif_state_from_structure_path(path: Path) -> tuple[str, str] | None:
    parts = list(path.parts)
    if "model_build" in parts and "structures" in parts:
        idx = parts.index("structures")
        if idx + 1 < len(parts):
            return parts[idx + 1], "clean"
    if "uma_relax" in parts and "surface" in parts:
        idx = parts.index("surface")
        if idx + 2 < len(parts):
            return parts[idx + 1], parts[idx + 2]
    return None


def overlay_for_structure(path: Path, view: str = "side_a") -> Path | None:
    if path.suffix.lower() == ".png" and path.exists():
        return path
    motif_state = motif_state_from_structure_path(path)
    exec_root = execution_root_for_path(path)
    if motif_state is None or exec_root is None:
        return None
    motif, state = motif_state
    overlay = exec_root / "analysis" / "final_relaxations" / f"surface_{motif}_{state}" / f"overlay_{view}.png"
    return overlay if overlay.exists() else None


def structure_cells(fig: dict[str, Any], project_root: Path) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for artifact in fig.get("artifacts", []):
        path = resolve_artifact(project_root, str(artifact))
        if not path.exists():
            continue
        motif_state = motif_state_from_structure_path(path)
        overlay = overlay_for_structure(path)
        if motif_state is None or overlay is None:
            continue
        motif, state = motif_state
        key = (motif, state)
        if key in seen:
            continue
        seen.add(key)
        cells.append(
            {
                "motif": motif,
                "state": state,
                "label": f"{nice_label(motif)} {nice_label(state)}",
                "source": str(path),
                "image": overlay,
            }
        )
    return cells


def ordered_unique(values: list[str], preferred: list[str] | None = None) -> list[str]:
    order = {value: idx for idx, value in enumerate(preferred or [])}
    return sorted(unique(values), key=lambda value: (order.get(value, 999), values.index(value)))


def fit_image(src: Path, size: tuple[int, int]) -> Image.Image:
    assert Image is not None
    image = Image.open(src).convert("RGB")
    image.thumbnail(size, Image.LANCZOS)
    canvas = Image.new("RGB", size, "white")
    x = (size[0] - image.size[0]) // 2
    y = (size[1] - image.size[1]) // 2
    canvas.paste(image, (x, y))
    return canvas


def structure_grid_from_overlays(fig: dict[str, Any], project_root: Path, out_png: Path) -> list[Path]:
    if Image is None or ImageDraw is None:
        return []
    cells = structure_cells(fig, project_root)
    if not cells:
        return []
    state_order = ["clean", "H", "H2O", "OH", "H2", "H_OH"]
    motifs = ordered_unique([cell["motif"] for cell in cells])
    states = ordered_unique([cell["state"] for cell in cells], state_order)
    by_key = {(cell["motif"], cell["state"]): cell for cell in cells}

    cell_w, cell_h = 260, 210
    row_label_w = 170
    col_label_h = 44
    pad = 16
    gap = 8
    width = row_label_w + len(states) * cell_w + max(len(states) - 1, 0) * gap + pad * 2
    height = col_label_h + len(motifs) * cell_h + max(len(motifs) - 1, 0) * gap + pad * 2
    out_png.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    try:
        font_header = ImageFont.truetype("DejaVuSans-Bold.ttf", 15)
        font_label = ImageFont.truetype("DejaVuSans-Bold.ttf", 13)
    except Exception:
        font_header = font_label = None

    x0 = pad + row_label_w
    y0 = pad + col_label_h
    draw.line((pad, y0 - 8, width - pad, y0 - 8), fill="#222222", width=2)
    for col_idx, state in enumerate(states):
        x = x0 + col_idx * (cell_w + gap) + cell_w // 2
        draw.text((x, pad + 10), nice_label(state), fill="#111111", font=font_header, anchor="mm")
    for row_idx, motif in enumerate(motifs):
        y = y0 + row_idx * (cell_h + gap)
        draw.text((pad + row_label_w // 2, y + cell_h // 2), nice_label(motif), fill="#111111", font=font_label, anchor="mm")
        draw.line((pad, y - 4, width - pad, y - 4), fill="#d2d2d2", width=1)
        for col_idx, state in enumerate(states):
            x = x0 + col_idx * (cell_w + gap)
            cell = by_key.get((motif, state))
            draw.rectangle((x, y, x + cell_w, y + cell_h), outline="#d9d9d9", width=1)
            if not cell:
                continue
            thumb = fit_image(Path(cell["image"]), (cell_w - 10, cell_h - 10))
            canvas.paste(thumb, (x + 5, y + 5))
    canvas.save(out_png)
    return [out_png]


def diagnostic_exports(fig: dict[str, Any], project_root: Path, exported_dir: Path, base: str, force: bool) -> list[Path]:
    copied: list[Path] = []
    candidates: list[Path] = []
    for artifact in fig.get("artifacts", []):
        path = resolve_artifact(project_root, str(artifact))
        if path.exists() and path.suffix.lower() == ".png":
            candidates.append(path)
        parts = path.parts
        exec_idx = next((idx for idx, part in enumerate(parts) if part.endswith("_execution") and part != "strategy_execution"), None)
        if exec_idx is not None:
            exec_root = Path(*parts[: exec_idx + 1])
            candidates.extend(sorted((exec_root / "analysis" / "final_relaxations" / "contact_sheets").glob("*.png")))
    for idx, src in enumerate(sorted(set(candidates))[:12], start=1):
        dst = exported_dir / f"{base}_{idx:02d}_{src.name}"
        copied.append(copy_file(src, dst, force))
    return copied


def qa_markdown(fig: dict[str, Any], record: dict[str, Any]) -> str:
    lines = [
        f"# {fig['id']} {fig.get('title', '')}",
        "",
        f"- State: `{record['state']}`",
        f"- Type: `{fig.get('type', '')}`",
        f"- Level: `{fig.get('level', '')}`",
        f"- Declared skill: `{fig.get('skill', '')}`",
        f"- Source procedures: {', '.join(fig.get('source', {}).get('procedures', [])) or 'none'}",
        f"- Source calculations: {', '.join(fig.get('source', {}).get('calculations', [])) or 'none'}",
    ]
    if fig.get("grounding"):
        grounding = fig["grounding"]
        lines.extend(["", "## Grounding"])
        lines.append(f"- Status: `{grounding.get('status', 'unknown')}`")
        lines.append(f"- Quantities: {', '.join(grounding.get('quantities', [])) or 'none'}")
        for basis in grounding.get("basis", [])[:3]:
            lines.append(f"- Basis: {basis}")
    if record.get("notes"):
        lines.extend(["", "## Notes"])
        lines.extend(f"- {note}" for note in record["notes"])
    if fig.get("caveats"):
        lines.extend(["", "## Caveats"])
        lines.extend(f"- {caveat}" for caveat in fig["caveats"])
    if fig.get("blockers"):
        lines.extend(["", "## Blockers"])
        lines.extend(f"- {blocker}" for blocker in fig["blockers"])
    if record.get("exported_files"):
        lines.extend(["", "## Exported Files"])
        lines.extend(f"- `{path}`" for path in record["exported_files"])
    if record.get("source_files"):
        lines.extend(["", "## Source Files"])
        lines.extend(f"- `{path}`" for path in record["source_files"])
    return "\n".join(lines).rstrip() + "\n"


def realize_one(fig: dict[str, Any], root: Path, project_root: Path, force: bool, include_blocked: bool) -> dict[str, Any]:
    base = f"{fig['id']}_{slug(fig.get('type', 'figure'))}"
    source_dir = root / "source" / base
    exported_dir = root / "exported"
    qa_file = root / "qa" / f"{base}.md"
    record = {
        "id": fig["id"],
        "type": fig.get("type", ""),
        "level": fig.get("level", ""),
        "state": "failed",
        "source_files": [],
        "exported_files": [],
        "qa_file": str(qa_file),
        "command": "",
        "notes": [],
    }
    if force and source_dir.exists():
        shutil.rmtree(source_dir)
    if force:
        clear_exports(exported_dir, base)

    if fig.get("status") == "blocked" or fig.get("level") in SKIP_LEVELS or fig.get("grounding", {}).get("status") == "blocked":
        record["state"] = "blocked" if fig.get("status") == "blocked" else "skipped"
        if include_blocked:
            copied = copy_candidate_sources(fig, project_root, source_dir, force)
            record["source_files"] = [str(path) for path in copied]
        record["notes"].append("No exported figure was created for a blocked or archive-level candidate.")
        write_text(qa_file, qa_markdown(fig, record))
        return record

    fig_type = fig.get("type", "")
    copied_sources = copy_candidate_sources(fig, project_root, source_dir, force)
    record["source_files"] = [str(path) for path in copied_sources]

    if fig_type == "energy-diagram":
        exported = copy_existing_exports(fig, project_root, exported_dir, base, force)
        record["exported_files"] = [str(path) for path in exported]
        record["state"] = "realized" if exported else "failed"
        record["notes"].append("Reused existing energy-diagram exports from mapped artifacts.")

    elif fig_type == "descriptor-comparison":
        records, metric = find_descriptor_records(fig, project_root)
        if records:
            chart_title = str(fig.get("figure_type") or fig.get("title") or "Strategy-backed descriptor comparison")
            png = bar_chart_png(records, chart_title, value_axis_label(metric), exported_dir / f"{base}.png")
            record["exported_files"] = [str(png)] if png else []
            record["state"] = "realized" if png else "failed"
            record["notes"].append(f"Generated a local PNG bar chart from strategy-backed descriptor `{metric}`.")
        else:
            record["state"] = "failed"
            record["notes"].append("No descriptor table matched the strategy-authorized quantities declared in mapping grounding.")

    elif fig_type == "benchmark-comparison":
        records = find_benchmark_records(fig, project_root)
        if records:
            png = bar_chart_png(records, "Benchmark comparison", "mV or mV dec-1", exported_dir / f"{base}.png")
            record["exported_files"] = [str(png)] if png else []
            record["state"] = "realized" if png else "failed"
            record["notes"].append("Generated a local PNG bar chart from benchmark comparison JSON.")
        else:
            record["state"] = "failed"
            record["notes"].append("No benchmark JSON with recognized overpotential/Tafel fields was found.")

    elif fig_type == "calculation-diagnostic":
        exported = diagnostic_exports(fig, project_root, exported_dir, base, force)
        record["exported_files"] = [str(path) for path in exported]
        record["state"] = "realized" if exported else "source-ready"
        record["notes"].append("Collected existing analyzer/contact-sheet PNG diagnostics.")

    elif fig_type == "structure-grid":
        manifest = structure_manifest(fig, project_root, source_dir / f"{base}.manifest.json")
        record["source_files"].append(str(manifest))
        record["command"] = (
            "mamba run -n modeling python SKILL/adsorbate-structure-grid/scripts/build_grid_figure.py "
            f"--input {manifest} --output {exported_dir / (base + '.png')}"
        )
        exported = structure_grid_from_overlays(
            fig,
            project_root,
            exported_dir / f"{base}.png",
        )
        record["exported_files"] = [str(path) for path in exported]
        if exported:
            record["state"] = "realized"
            record["notes"].append("Rendered a structure grid from existing analyzer overlay PNGs.")
            record["notes"].append("Also prepared an adsorbate-structure-grid manifest for rerendering in the modeling environment.")
        else:
            record["state"] = "source-ready"
            record["notes"].append("Prepared an adsorbate-structure-grid manifest; run the recorded command to render structure images.")

    else:
        exported = copy_existing_exports(fig, project_root, exported_dir, base, force)
        record["exported_files"] = [str(path) for path in exported]
        record["state"] = "realized" if exported else "source-ready"
        record["notes"].append("No type-specific local renderer exists; copied source/exported artifacts where available.")

    write_text(qa_file, qa_markdown(fig, record))
    return record


def realization_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Figure Realization for {payload.get('strategy_id', 'strategy')}",
        "",
        "| ID | Type | Level | State | Exported |",
        "| --- | --- | --- | --- | --- |",
    ]
    for rec in payload.get("figures", []):
        exported = len(rec.get("exported_files", []))
        lines.append(f"| {rec['id']} | {rec['type']} | {rec['level']} | {rec['state']} | {exported} |")
    lines.extend(["", "## Details", ""])
    for rec in payload.get("figures", []):
        lines.append(f"### {rec['id']} {rec['type']}")
        lines.append(f"- State: `{rec['state']}`")
        if rec.get("command"):
            lines.append(f"- Follow-up command: `{rec['command']}`")
        if rec.get("exported_files"):
            lines.append("- Exported files:")
            lines.extend(f"  - `{path}`" for path in rec["exported_files"])
        if rec.get("source_files"):
            lines.append("- Source files:")
            lines.extend(f"  - `{path}`" for path in rec["source_files"][:12])
        if rec.get("notes"):
            lines.append("- Notes:")
            lines.extend(f"  - {note}" for note in rec["notes"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Realize mapped MESA strategy figure candidates.")
    parser.add_argument("--mapping", required=True, help="Path to figure_info.json from strategy-figure-mapper.")
    parser.add_argument("--figure-root", help="Override figure workspace root. Default is parent of mapping/.")
    parser.add_argument("--project-root", default=".", help="Project root used to resolve mapped relative artifacts.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing realized outputs.")
    parser.add_argument("--include-blocked", action="store_true", help="Copy source artifacts for blocked/archive candidates.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    mapping = Path(args.mapping)
    project_root = Path(args.project_root).resolve()
    root = Path(args.figure_root) if args.figure_root else figure_root_from_mapping(mapping)
    ensure_workspace(root)
    info = read_json(mapping)

    records = []
    for fig in info.get("figures", []):
        records.append(realize_one(fig, root, project_root, args.force, args.include_blocked))

    payload = {
        "schema_version": 1,
        "strategy_id": info.get("strategy_id", ""),
        "mapping": str(mapping),
        "figure_root": str(root),
        "figures": records,
    }
    manifest = root / "realization" / "figure_realization.json"
    summary = root / "realization" / "figure_realization.md"
    write_json(manifest, payload)
    write_text(summary, realization_markdown(payload))
    print(f"Wrote {manifest}")
    print(f"Wrote {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
