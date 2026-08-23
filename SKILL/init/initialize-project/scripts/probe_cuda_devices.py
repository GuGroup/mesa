#!/usr/bin/env python3
"""Capture stable CUDA inventory and visibility mapping."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


QUERY_FIELDS = "index,uuid,name,memory.total"


class ProbeError(RuntimeError):
    pass


def unavailable_inventory(
    raw_visibility: str | None, diagnostic: str
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "query_fields": QUERY_FIELDS.split(","),
        "status": "unavailable",
        "cuda_visible_devices": raw_visibility,
        "devices": [],
        "unresolved_visibility_tokens": [],
        "diagnostics": [diagnostic],
    }


def parse_query_output(text: str) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    for row_number, row in enumerate(csv.reader(text.splitlines()), start=1):
        if not row or all(not value.strip() for value in row):
            continue
        if len(row) != 4:
            raise ProbeError(f"Unexpected nvidia-smi row {row_number}: {row!r}")
        index_text, uuid, name, memory_text = (value.strip() for value in row)
        try:
            index = int(index_text)
        except ValueError as exc:
            raise ProbeError(f"Invalid GPU index in row {row_number}: {index_text!r}") from exc
        memory_match = re.search(r"\d+", memory_text.replace(",", ""))
        if not memory_match:
            raise ProbeError(f"Invalid total memory in row {row_number}: {memory_text!r}")
        devices.append(
            {
                "index": index,
                "uuid": uuid,
                "name": name,
                "memory_total_mib": int(memory_match.group()),
            }
        )
    devices.sort(key=lambda item: item["index"])
    return devices


def _match_token(token: str, devices: list[dict[str, Any]]) -> dict[str, Any] | None:
    if token.isdigit():
        index = int(token)
        return next((item for item in devices if item["index"] == index), None)
    exact = next((item for item in devices if item["uuid"] == token), None)
    if exact:
        return exact
    matches = [item for item in devices if item["uuid"].startswith(token)]
    return matches[0] if len(matches) == 1 else None


def apply_visibility(
    devices: list[dict[str, Any]], raw_visibility: str | None
) -> tuple[list[dict[str, Any]], list[str]]:
    mapping: dict[int, int] = {}
    unresolved: list[str] = []
    if raw_visibility is None:
        mapping = {item["index"]: logical for logical, item in enumerate(devices)}
    else:
        normalized = raw_visibility.strip()
        hidden = normalized.lower() in {"", "-1", "none", "nodevfiles"}
        tokens = [] if hidden else [part.strip() for part in normalized.split(",")]
        for logical, token in enumerate(token for token in tokens if token):
            match = _match_token(token, devices)
            if match is None or match["index"] in mapping:
                unresolved.append(token)
                continue
            mapping[match["index"]] = logical

    visible_devices: list[dict[str, Any]] = []
    for item in devices:
        physical_index = item["index"]
        visible_devices.append(
            {
                **item,
                "visibility": {
                    "eligible": physical_index in mapping,
                    "logical_index": mapping.get(physical_index),
                },
            }
        )
    return visible_devices, unresolved


def run_probe() -> str:
    command = [
        "nvidia-smi",
        f"--query-gpu={QUERY_FIELDS}",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError as exc:
        raise ProbeError("nvidia-smi is unavailable") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "nvidia-smi failed").strip()
        raise ProbeError(detail) from exc
    except subprocess.TimeoutExpired as exc:
        raise ProbeError("nvidia-smi timed out") from exc
    return completed.stdout


def build_inventory(query_output: str, raw_visibility: str | None) -> dict[str, Any]:
    devices, unresolved = apply_visibility(parse_query_output(query_output), raw_visibility)
    eligible = any(item["visibility"]["eligible"] for item in devices)
    diagnostics = [
        f"Unresolved CUDA_VISIBLE_DEVICES selector: {token}" for token in unresolved
    ]
    if not devices:
        diagnostics.append("nvidia-smi reported no GPUs")
    elif not eligible:
        diagnostics.append("No probed GPU is CUDA-visible")
    return {
        "schema_version": "1.0",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "query_fields": QUERY_FIELDS.split(","),
        "status": "available" if eligible else "unavailable",
        "cuda_visible_devices": raw_visibility,
        "devices": devices,
        "unresolved_visibility_tokens": unresolved,
        "diagnostics": diagnostics,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write inventory JSON to this path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raw_visibility = os.environ.get("CUDA_VISIBLE_DEVICES")
    try:
        inventory = build_inventory(run_probe(), raw_visibility)
    except ProbeError as exc:
        inventory = unavailable_inventory(raw_visibility, str(exc))
    text = json.dumps(inventory, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if inventory["status"] == "available" else 1


if __name__ == "__main__":
    raise SystemExit(main())
