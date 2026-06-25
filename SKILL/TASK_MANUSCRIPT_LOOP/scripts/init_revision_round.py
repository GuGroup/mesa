#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final


ROUND_PATTERN: Final = re.compile(r"^round-\d{3}$")
ROUND_DIRS: Final[tuple[str, ...]] = (
    "reviewer-comments.raw",
    "patches",
    "snapshots",
)
ROUND_FILES: Final[dict[str, str]] = {
    "README.md": "# Revision Round\n\nRecord reviewer comments, responses, patches, and verification here.\n",
    "reviewer-comments.raw/README.md": "# Raw Reviewer Comments\n\nPlace one raw issue file per reviewer or comment source here.\n",
    "reviewer-issues.merged.yaml": "version: 1\nissues: []\n",
    "author-response.yaml": "version: 1\nresponses: []\n",
    "change-plan.yaml": "version: 1\nchanges: []\n",
    "patches/README.md": "# Patch Diffs\n\nStore unified diffs that map changes to issue IDs.\n",
    "changed-files.md": "# Changed Files\n\n",
    "snapshots/README.md": "# Snapshots\n\nOptional before/after source snapshots for review.\n",
    "verification.md": "# Verification\n\n",
}


@dataclass(frozen=True)
class RevisionRoundArgs:
    paper: Path
    round_id: str
    force: bool


@dataclass(frozen=True)
class RevisionRoundResult:
    path: Path
    written: int
    preserved: int


class RevisionRoundError(Exception):
    pass


def normalize_round_id(value: str) -> str:
    if value.isdecimal():
        return f"round-{int(value):03d}"
    if ROUND_PATTERN.fullmatch(value):
        return value
    raise RevisionRoundError("round must be an integer or round-NNN label")


def ensure_paper_root(path: Path) -> Path:
    paper = path.resolve()
    if not paper.is_dir():
        raise RevisionRoundError(f"paper root does not exist or is not a directory: {path}")
    if paper.name != "paper":
        raise RevisionRoundError(f"paper root must be named paper: {path}")
    return paper


def ensure_safe_round_path(paper: Path, path: Path) -> None:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(paper)
    except ValueError as exc:
        raise RevisionRoundError(f"revision path escapes paper root: {path}") from exc
    if ".." in relative.parts:
        raise RevisionRoundError(f"revision path escapes paper root: {path}")
    current = paper
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise RevisionRoundError(f"refusing to write through symlink: {current}")


def write_round_file(path: Path, content: str, force: bool) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def initialize_revision_round(config: RevisionRoundArgs) -> RevisionRoundResult:
    paper = ensure_paper_root(config.paper)
    round_dir = paper / "revisions" / config.round_id
    ensure_safe_round_path(paper, round_dir)
    round_dir.mkdir(parents=True, exist_ok=True)
    for rel_dir in ROUND_DIRS:
        target = round_dir / rel_dir
        ensure_safe_round_path(paper, target)
        target.mkdir(parents=True, exist_ok=True)
    written = 0
    preserved = 0
    for rel_path, content in sorted(ROUND_FILES.items()):
        target = round_dir / rel_path
        ensure_safe_round_path(paper, target)
        if write_round_file(target, content, config.force):
            written += 1
        else:
            preserved += 1
    return RevisionRoundResult(round_dir, written, preserved)


def parse_args(argv: tuple[str, ...]) -> RevisionRoundArgs:
    parser = argparse.ArgumentParser(description="Create a MESA manuscript revision round audit directory.")
    parser.add_argument("--paper", required=True, type=Path, help="Path to canonical paper/ directory.")
    parser.add_argument("--round", required=True, dest="round_value", help="Round number or round-NNN label.")
    parser.add_argument("--force", action="store_true", help="Rewrite existing non-empty round seed files.")
    args = parser.parse_args(argv)
    return RevisionRoundArgs(args.paper, normalize_round_id(args.round_value), args.force)


def main(argv: tuple[str, ...] | None = None) -> int:
    try:
        result = initialize_revision_round(parse_args(tuple(sys.argv[1:] if argv is None else argv)))
    except RevisionRoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"initialized {result.path} (written={result.written}, preserved_nonempty={result.preserved})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
