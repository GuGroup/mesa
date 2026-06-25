from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Final, NamedTuple, Optional, Union


CANONICAL_STRUCTURE: Final[str] = "paper/inputs/structures/CO_on_Pt111_POSCAR"
GENERATED_MARKER: Final[str] = "# generated-by: ingest_mesa_outputs.py\n"
SVG_GENERATED_MARKER: Final[str] = "<!-- generated-by: ingest_mesa_outputs.py -->\n"
JsonScalar = Union[None, bool, int, float, str]
JsonValue = Union[JsonScalar, list["JsonValue"], dict[str, "JsonValue"]]
JsonObject = dict[str, JsonValue]


class IntakeError(Exception):
    pass


ResultRecord = NamedTuple(
    "ResultRecord",
    [
        ("source_id", str),
        ("system_id", str),
        ("system_label", str),
        ("method_id", str),
        ("method_label", str),
        ("quantity", str),
        ("quantity_label", str),
        ("value", str),
        ("units", str),
        ("status", str),
        ("source_task", str),
        ("source_ref", str),
        ("result_path", str),
    ],
)
SourceItem = NamedTuple(
    "SourceItem",
    [
        ("id", str),
        ("kind", str),
        ("path", str),
        ("source_task", str),
        ("status", str),
        ("provenance", str),
        ("units", str),
        ("claim_role", str),
        ("blockers", tuple[str, ...]),
    ],
)
IngestOptions = NamedTuple(
    "IngestOptions",
    [("paper", Path), ("input_root", Path), ("out", Optional[Path]), ("force", bool)],
)
WriteContext = NamedTuple(
    "WriteContext",
    [("paper", Path), ("force", bool), ("preserved", list[str])],
)
IngestResult = NamedTuple("IngestResult", [("preserved", tuple[str, ...])])


def fail(message: str) -> None:
    raise IntakeError(message)


def slug(raw: str) -> str:
    return "-".join(
        token.lower()
        for token in re.split(r"[^A-Za-z0-9]+", raw)
        if token and token.lower() != "on"
    )


def read_json(path: Path) -> JsonObject:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IntakeError(f"malformed JSON in {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        fail(f"malformed JSON in {path}: top level must be an object")
    return parsed


def text_field(data: JsonObject, key: str, where: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        fail(f"missing required envelope field {key} in {where}")
    return value


def source_ref(path: Path, input_root: Path) -> str:
    return f"{input_root.name}/{path.relative_to(input_root).as_posix()}"


def parse_result(path: Path, input_root: Path) -> ResultRecord:
    envelope = read_json(path)
    data = envelope.get("data")
    provenance = envelope.get("provenance")
    if not isinstance(data, dict):
        fail(f"missing required envelope field data.system_id in {path}")
    if not isinstance(provenance, dict):
        fail(f"missing required envelope field provenance.task in {path}")
    if "value" not in data:
        fail(f"missing required envelope field data.value in {path}")

    system_id = text_field(data, "system_id", path)
    quantity = text_field(data, "quantity", path)
    result_slug = slug(f"{system_id}_{quantity.replace('adsorption_', '')}")
    method_id = str(data.get("method_id", "PBE_D3_slab_fixture"))
    method_label = str(
        data.get("method_label", method_id.replace("_", "-").replace("slab-fixture", "slab fixture"))
    )
    return ResultRecord(
        source_id=f"result-{result_slug}",
        system_id=system_id,
        system_label=system_id.replace("_on_", " on ").replace("Pt111", "Pt(111)").replace("_", " "),
        method_id=method_id,
        method_label=method_label,
        quantity=quantity,
        quantity_label=quantity.replace("_", " "),
        value=str(data["value"]),
        units=text_field(data, "units", path),
        status="converged" if envelope.get("status") == "success" else str(envelope.get("status")),
        source_task=text_field(provenance, "task", path),
        source_ref=source_ref(path, input_root),
        result_path=f"paper/inputs/results/{result_slug.replace('-', '_')}.yaml",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Typed record parsing helpers for manuscript output ingestion. This module "
            "is imported by ingest_mesa_outputs.py; run that CLI for normal use."
        )
    )
    parser.parse_args()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
