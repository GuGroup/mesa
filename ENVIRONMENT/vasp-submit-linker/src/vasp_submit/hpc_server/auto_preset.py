from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


CAPACITY_HINT_RE = re.compile(r"\b(?:avail(?:able)?|free|idle|remain(?:ing)?)\s*[:=]\s*(-?\d+)\b", re.IGNORECASE)
DEFAULT_FULL_QUEUE_FALLBACK_CORES = 48


def remaining_capacity_hint(text: str) -> int | None:
    labelled_counts = [int(value) for value in CAPACITY_HINT_RE.findall(text)]
    if labelled_counts:
        return max(labelled_counts)
    return None


def parse_available_qq_nodes(output: str, config: dict[str, Any]) -> dict[int, list[str]]:
    auto = config.get("auto_preset") or {}
    ranges = auto.get("node_core_ranges") or {
        48: [[1, 30]],
        64: [[31, 40]],
    }
    available: dict[int, list[str]] = {}
    for line in output.splitlines():
        stripped = line.strip()
        match = re.match(r"^n(\d+)\b(.*)$", stripped)
        if not match:
            continue
        node_number = int(match.group(1))
        node_details = match.group(2).strip()
        capacity = remaining_capacity_hint(node_details)
        # The real qq table lists occupied nodes as job rows whose final
        # unlabelled number is the slot count (for example, 64), not free
        # capacity.  Treat non-empty, unlabelled rows as occupied rather than
        # guessing from arbitrary numbers.  A free node is either a bare node
        # row or has an explicit free/remaining-style capacity hint.
        if node_details and capacity is None:
            continue
        if capacity is not None and capacity <= 0:
            continue
        node_name = f"n{node_number:02d}"
        for cores_raw, intervals in ranges.items():
            cores = int(cores_raw)
            for start, end in intervals:
                if int(start) <= node_number <= int(end):
                    available.setdefault(cores, []).append(node_name)
    return available


def queue_status_output(config: dict[str, Any]) -> str:
    command = str(config.get("queue_status_command") or "qq")
    if command.startswith("~"):
        command = str(Path(command).expanduser())
    proc = subprocess.run(
        [command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{command} failed: {proc.stderr.strip()}")
    return proc.stdout


def auto_select_preset(spec: dict[str, Any], config: dict[str, Any]) -> str:
    vasp = spec.get("vasp") or {}
    binary = "gam" if bool(vasp.get("gamma", False)) and vasp.get("kpts") == [1, 1, 1] else "std"
    available = parse_available_qq_nodes(queue_status_output(config), config)
    prefer = (config.get("auto_preset") or {}).get("prefer") or [64, 48]
    preferred_core_counts = [int(cores) for cores in prefer]
    for core_count in preferred_core_counts:
        if available.get(core_count):
            return f"preset{core_count}{binary}"
    fallback = (config.get("auto_preset") or {}).get("fallback")
    if fallback:
        return str(fallback)
    return f"preset{DEFAULT_FULL_QUEUE_FALLBACK_CORES}{binary}"
