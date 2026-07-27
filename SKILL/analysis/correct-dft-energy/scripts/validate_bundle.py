#!/usr/bin/env python3
"""Validate the combined MESA OER/NO3RR skills-only plugin bundle."""

from __future__ import annotations

import json
import py_compile
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # optional convenience check
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
SKILLS = (
    ROOT / "skills" / "assemble-oer-energy-corrections",
    ROOT / "skills" / "assemble-no3rr-energy-corrections",
)


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 2


def main() -> int:
    manifest_path = ROOT / ".codex-plugin" / "plugin.json"
    if not manifest_path.is_file():
        return fail("missing .codex-plugin/plugin.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in ("name", "version", "description", "skills"):
        if not manifest.get(key):
            return fail(f"plugin manifest missing {key}")
    if manifest["skills"] != "./skills/":
        return fail("plugin manifest skills path must be ./skills/")

    for skill in SKILLS:
        if not (skill / "SKILL.md").is_file():
            return fail(f"missing {skill.relative_to(ROOT)}/SKILL.md")
        metadata_path = skill / "agents" / "openai.yaml"
        if yaml is not None:
            metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict) or not isinstance(metadata.get("interface"), dict):
                return fail(f"invalid skill metadata: {metadata_path.relative_to(ROOT)}")
        for script in (skill / "scripts").glob("*.py"):
            py_compile.compile(str(script), doraise=True)
        run = subprocess.run(
            [sys.executable, str(skill / "scripts" / "validate_skill.py")],
            cwd=skill,
        )
        if run.returncode != 0:
            return run.returncode

    print("Combined OER/NO3RR plugin bundle validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
