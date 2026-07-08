"""CSV and dictionary energy-input normalization."""

from __future__ import annotations

import csv
import io
from typing import Any, Iterable, Mapping, Sequence

from .chemistry import canonical_label
from .constants import METADATA_COLUMNS, STEP_COLUMN_CANDIDATES
from .errors import MesaValidationError
from .utils import as_list, is_number, resolve_path, safe_string, to_float


def normalise_energy_input(
    input_data: dict[str, Any],
    context: dict[str, Any] | None,
) -> tuple[str, list[str], list[str], dict[str, list[float]], dict[str, Any], list[str]]:
    """Normalize CSV or dictionary input into a common energy table.

    Returns step column name, canonical steps, catalyst labels, catalyst->energy
    series, input provenance record, and warnings.
    """
    warnings: list[str] = []
    if input_data.get("csv_text") or input_data.get("csv_path"):
        csv_text, input_record = load_csv_text(input_data, context)
        step_column, steps, catalysts, values, parse_warnings = parse_csv(csv_text)
        warnings.extend(parse_warnings)
        return step_column, steps, catalysts, values, input_record, warnings

    for key in ["energy_data", "reaction_energies", "energies", "values"]:
        if key in input_data:
            step_column, steps, catalysts, values, input_record, parse_warnings = parse_dictionary_energy_data(input_data[key])
            input_record["top_level_key"] = key
            warnings.extend(parse_warnings)
            return step_column, steps, catalysts, values, input_record, warnings

    if "steps" in input_data and ("catalysts" in input_data or "energies" in input_data or "values" in input_data):
        compact = {
            "steps": input_data.get("steps"),
            "catalysts": input_data.get("catalysts"),
            "energies": input_data.get("energies", input_data.get("values")),
        }
        step_column, steps, catalysts, values, input_record, parse_warnings = parse_dictionary_energy_data(compact)
        input_record["top_level_key"] = "steps+energies"
        warnings.extend(parse_warnings)
        return step_column, steps, catalysts, values, input_record, warnings

    raise MesaValidationError("Provide csv_path, csv_text, energy_data, reaction_energies, or dictionary energy data.")


def load_csv_text(input_data: dict[str, Any], context: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    if input_data.get("csv_text"):
        return str(input_data["csv_text"]), {"type": "csv_text"}
    csv_path = safe_string(input_data.get("csv_path"))
    if not csv_path:
        raise MesaValidationError("Provide either 'csv_path', 'csv_text', or dictionary energy data.")
    resolved = resolve_path(csv_path, context)
    return resolved.read_text(encoding="utf-8-sig"), {"type": "csv_path", "path": str(resolved)}


def parse_csv(csv_text: str) -> tuple[str, list[str], list[str], dict[str, list[float]], list[str]]:
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    if not rows:
        raise MesaValidationError("CSV input has no data rows.")

    columns = [column for column in list(rows[0].keys()) if column is not None]
    if len(columns) < 2:
        raise MesaValidationError("CSV must contain one step column and at least one catalyst column.")

    step_column = detect_step_column(columns, rows)
    catalysts = detect_numeric_columns(columns, rows, step_column)
    if not catalysts:
        raise MesaValidationError("CSV must contain at least one numeric catalyst energy column.")

    steps = [canonical_label(row.get(step_column)) for row in rows]
    if any(not step for step in steps):
        raise MesaValidationError(f"CSV step column '{step_column}' contains an empty label.")

    values: dict[str, list[float]] = {}
    for catalyst in catalysts:
        series: list[float] = []
        for row_index, row in enumerate(rows, start=2):
            series.append(to_float(row.get(catalyst), f"column '{catalyst}', CSV row {row_index}"))
        values[catalyst] = series
    warnings = duplicate_step_warnings(steps)
    return step_column, steps, catalysts, values, warnings


def detect_step_column(columns: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str:
    lowered = {column.lower(): column for column in columns}
    for candidate in STEP_COLUMN_CANDIDATES:
        if candidate in lowered:
            return lowered[candidate]
    for column in columns:
        numeric_count = sum(is_number(row.get(column)) for row in rows)
        if numeric_count < max(1, len(rows) // 2):
            return column
    return columns[0]


def detect_numeric_columns(columns: Sequence[str], rows: Sequence[Mapping[str, Any]], step_column: str) -> list[str]:
    numeric_columns: list[str] = []
    for column in columns:
        if column == step_column or column.lower() in METADATA_COLUMNS:
            continue
        if all(is_number(row.get(column)) for row in rows):
            numeric_columns.append(column)
    return numeric_columns


def duplicate_step_warnings(steps: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    warnings: list[str] = []
    for step in steps:
        if step in seen:
            warnings.append(f"Duplicate canonical reaction-coordinate label detected: {step}")
        seen.add(step)
    return warnings


def parse_dictionary_energy_data(
    energy_data: Any,
) -> tuple[str, list[str], list[str], dict[str, list[float]], dict[str, Any], list[str]]:
    warnings: list[str] = []
    if isinstance(energy_data, list):
        step_column, steps, catalysts, values = parse_row_records(energy_data)
        warnings.extend(duplicate_step_warnings(steps))
        return step_column, steps, catalysts, values, {"type": "dictionary_rows"}, warnings

    if not isinstance(energy_data, dict):
        raise MesaValidationError("Dictionary energy input must be a dictionary or list of row records.")

    if "rows" in energy_data and isinstance(energy_data["rows"], list):
        step_column, steps, catalysts, values = parse_row_records(energy_data["rows"])
        warnings.extend(duplicate_step_warnings(steps))
        return step_column, steps, catalysts, values, {"type": "dictionary_rows"}, warnings

    raw_steps = energy_data.get("steps") or energy_data.get("intermediates") or energy_data.get("states")
    raw_values = energy_data.get("energies", energy_data.get("values"))
    if raw_steps is not None and raw_values is not None:
        steps = [canonical_label(step) for step in as_list(raw_steps)]
        if any(not step for step in steps):
            raise MesaValidationError("Dictionary steps contain an empty label.")
        catalysts, values = values_object_to_series(raw_values, steps)
        warnings.extend(duplicate_step_warnings(steps))
        return "intermediate", steps, catalysts, values, {"type": "dictionary_steps_values"}, warnings

    # Catalyst-centric form: {"NiOOH": {"*": 0.0, "*OH": 1.55}, ...}
    if all(isinstance(value, dict) for value in energy_data.values()):
        step_groups = [mapping.keys() for mapping in energy_data.values() if isinstance(mapping, dict)]
        steps = ordered_union_steps(step_groups)
        catalysts, values = values_object_to_series(energy_data, steps)
        warnings.extend(duplicate_step_warnings(steps))
        return "intermediate", steps, catalysts, values, {"type": "dictionary_catalyst_step_map"}, warnings

    raise MesaValidationError(
        "Unsupported dictionary energy format. Use steps+energies, catalyst->step mapping, or row records."
    )


def parse_row_records(rows: list[Any]) -> tuple[str, list[str], list[str], dict[str, list[float]]]:
    if not rows:
        raise MesaValidationError("Row-record energy input is empty.")
    if not all(isinstance(row, dict) for row in rows):
        raise MesaValidationError("Row-record energy input must be a list of dictionaries.")
    columns: list[str] = []
    for row in rows:
        for key in row.keys():
            key_str = safe_string(key)
            if key_str and key_str not in columns:
                columns.append(key_str)
    step_column = detect_step_column(columns, rows)  # type: ignore[arg-type]
    catalysts = detect_numeric_columns(columns, rows, step_column)  # type: ignore[arg-type]
    if not catalysts:
        raise MesaValidationError("Row-record energy input must contain numeric catalyst columns.")
    steps = [canonical_label(row.get(step_column)) for row in rows]
    values: dict[str, list[float]] = {}
    for catalyst in catalysts:
        values[catalyst] = [to_float(row.get(catalyst), f"{catalyst}/{steps[index]}") for index, row in enumerate(rows)]
    return step_column, steps, catalysts, values


def ordered_union_steps(step_groups: Iterable[Iterable[Any]]) -> list[str]:
    seen: set[str] = set()
    steps: list[str] = []
    for group in step_groups:
        for raw_step in group:
            step = canonical_label(raw_step)
            if step and step not in seen:
                seen.add(step)
                steps.append(step)
    if not steps:
        raise MesaValidationError("No reaction-coordinate steps found in dictionary energy input.")
    return steps


def find_matching_step_key(mapping: Mapping[Any, Any], canonical_step: str) -> Any | None:
    for key in mapping.keys():
        if canonical_label(key) == canonical_step:
            return key
    return None


def values_object_to_series(values_obj: Any, steps: Sequence[str]) -> tuple[list[str], dict[str, list[float]]]:
    if not isinstance(values_obj, dict) or not values_obj:
        raise MesaValidationError("values/energies must be a non-empty dictionary mapping catalyst names to energies.")
    catalysts = [safe_string(key) for key in values_obj.keys()]
    values: dict[str, list[float]] = {}
    for catalyst in catalysts:
        raw_series = values_obj[catalyst]
        if isinstance(raw_series, dict):
            series: list[float] = []
            for step in steps:
                matching_key = find_matching_step_key(raw_series, step)
                if matching_key is None:
                    raise MesaValidationError(f"Missing energy for catalyst '{catalyst}' at step '{step}'.")
                series.append(to_float(raw_series[matching_key], f"{catalyst}/{step}"))
        else:
            raw_list = as_list(raw_series)
            if len(raw_list) != len(steps):
                raise MesaValidationError(
                    f"Catalyst '{catalyst}' has {len(raw_list)} energies but {len(steps)} step labels were provided."
                )
            series = [to_float(value, f"{catalyst}/{steps[index]}") for index, value in enumerate(raw_list)]
        values[catalyst] = series
    return catalysts, values
