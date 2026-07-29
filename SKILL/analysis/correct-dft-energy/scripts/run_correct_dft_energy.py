#!/usr/bin/env python3
"""Location-independent entry point for the included OER and NO3RR workflows."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent
CHILDREN = {
    "oer": ROOT / "skills" / "assemble-oer-energy-corrections"
    / "scripts" / "compute_oer_corrections.py",
    "no3rr": ROOT / "skills" / "assemble-no3rr-energy-corrections"
    / "scripts" / "compute_no3rr_corrections.py",
}


class DispatchError(ValueError):
    """Raised when a correction workflow cannot be selected safely."""


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Dispatch catalyst free-energy bookkeeping to OER or NO3RR.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--mode", choices=("auto", "oer", "no3rr"), default="auto")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_known_args()


def detect_mode(payload: Mapping[str, Any]) -> str:
    """Return an unambiguous reaction mode or raise DispatchError."""
    references = payload.get("references")
    reference_keys = set(references) if isinstance(references, Mapping) else set()
    policy = payload.get("reference_policy")
    policy_keys = set(policy) if isinstance(policy, Mapping) else set()

    no3rr_markers = bool(
        payload.get("pathways")
        or {"HNO3", "NO3", "NH3"} & reference_keys
        or any("hno3" in str(key).lower() for key in policy_keys)
    )

    oer_markers = False
    motifs = payload.get("motifs")
    if isinstance(motifs, list):
        for motif in motifs:
            if not isinstance(motif, Mapping):
                continue
            states = motif.get("states")
            if isinstance(states, Mapping) and {"clean", "OH", "O", "OOH"} <= set(states):
                oer_markers = True
                break
    oer_markers = oer_markers or bool({"O2", "H2O", "H2"} <= reference_keys)

    if oer_markers == no3rr_markers:
        detected = "both" if oer_markers else "neither"
        raise DispatchError(
            f"automatic detection found {detected} OER/NO3RR marker sets; "
            "rerun with --mode oer or --mode no3rr"
        )
    return "oer" if oer_markers else "no3rr"


def build_command(
    mode: str,
    input_path: Path,
    outdir: Path,
    strict: bool,
    passthrough: list[str],
) -> list[str]:
    script = CHILDREN[mode]
    if not script.is_file():
        raise DispatchError(f"missing child workflow script: {script}")
    command = [
        sys.executable,
        str(script),
        "--input",
        str(input_path.resolve()),
        "--outdir",
        str(outdir.resolve()),
    ]
    if strict:
        command.append("--strict")
    command.extend(passthrough)
    return command


def main() -> int:
    args, passthrough = parse_args()
    try:
        payload = json.loads(args.input.expanduser().read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise DispatchError("input JSON must contain an object at its root")
        mode = detect_mode(payload) if args.mode == "auto" else args.mode
        command = build_command(
            mode,
            args.input.expanduser(),
            args.outdir.expanduser(),
            args.strict,
            passthrough,
        )
    except (DispatchError, json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps({"selected_mode": mode, "command": command}, indent=2), flush=True)
    return subprocess.run(command, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
