#!/usr/bin/env python3
"""Validate required NO3RR skill files, run tests, and regenerate example artifacts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = [
    ROOT / "README.md",
    ROOT / "SKILL.md",
    ROOT / "agents" / "openai.yaml",
    ROOT / "references" / "input-schema.md",
    ROOT / "references" / "no3rr-correction-policy.md",
    ROOT / "references" / "literature-and-provenance.md",
    ROOT / "scripts" / "compute_no3rr_corrections.py",
    ROOT / "scripts" / "test_compute_no3rr_corrections.py",
    ROOT / "assets" / "example_no3rr_input.json",
    ROOT / "assets" / "example_no3rr_calle_vallejo_pH0_input.json",
    ROOT / "evals" / "trigger-prompts.csv",
]


def main() -> int:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED if not path.exists()]
    if missing:
        print("Missing required files:", file=sys.stderr)
        for item in missing:
            print(f"- {item}", file=sys.stderr)
        return 2
    frontmatter = (ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines()
    if not frontmatter or frontmatter[0].strip() != "---":
        print("SKILL.md does not start with YAML front matter", file=sys.stderr)
        return 2
    joined = "\n".join(frontmatter[:30])
    for token in ("name:", "description:"):
        if token not in joined:
            print(f"SKILL.md missing {token}", file=sys.stderr)
            return 2
    test = subprocess.run([sys.executable, str(ROOT / "scripts" / "test_compute_no3rr_corrections.py")], cwd=ROOT)
    if test.returncode != 0:
        return test.returncode
    outdir = ROOT / "assets" / "example_no3rr_output"
    run = subprocess.run([
        sys.executable,
        str(ROOT / "scripts" / "compute_no3rr_corrections.py"),
        "--input", str(ROOT / "assets" / "example_no3rr_input.json"),
        "--outdir", str(outdir),
        "--strict",
    ], cwd=ROOT)
    if run.returncode != 0:
        return run.returncode

    pH0_outdir = ROOT / "assets" / "example_no3rr_calle_vallejo_pH0_output"
    pH0_run = subprocess.run([
        sys.executable,
        str(ROOT / "scripts" / "compute_no3rr_corrections.py"),
        "--input", str(ROOT / "assets" / "example_no3rr_calle_vallejo_pH0_input.json"),
        "--outdir", str(pH0_outdir),
        "--strict",
    ], cwd=ROOT)
    if pH0_run.returncode != 0:
        return pH0_run.returncode
    print("NO3RR skill validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
