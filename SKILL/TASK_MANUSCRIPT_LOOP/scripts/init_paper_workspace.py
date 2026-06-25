#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final


PAPER_DIRS: Final[tuple[str, ...]] = (
    "inputs/results",
    "inputs/structures",
    "inputs/tables",
    "inputs/figures",
    "inputs/prior-notes",
    "inputs/references",
    "logic",
    "state",
    "manuscript/sections",
    "manuscript/si",
    "figures/source",
    "figures/exported",
    "figures/qa",
    "build/docx",
)

INIT_CURRENT_STAGE: Final[str] = """version: 1
stage: intake
status: pending
blockers: []
next_action: Run ingest_mesa_outputs.py with completed MESA outputs.
"""

SEED_FILES: Final[dict[str, str]] = {
    "inputs/manifest.yaml": "",
    "logic/result-inventory.md": "",
    "logic/claim-matrix.yaml": """version: 1
target: nature-family
claims: []
""",
    "logic/story-spine.md": "# Story Spine\n\n",
    "logic/figure-map.yaml": """version: 1
figures: []
""",
    "logic/reviewer-risks.md": "# Reviewer Risks\n\n",
    "logic/notation.yaml": """version: 1
systems: []
methods: []
energies: []
figures: []
abbreviations: []
""",
    "state/ledger.jsonl": "",
    "state/current-stage.yaml": INIT_CURRENT_STAGE,
    "state/reviewer-issues.yaml": "version: 1\nissues: []\n",
    "state/revision-plan.yaml": "version: 1\ndecisions: []\n",
    "state/qa-checks.yaml": "version: 1\nchecks: []\n",
    "manuscript/outline.md": "# Manuscript Outline\n\n",
    "manuscript/section-contracts.yaml": """version: 1
sections:
  - id: abstract
    path: paper/manuscript/sections/abstract.md
    status: not-ready
    allowed_claims: []
    required_figures: []
    required_sources: []
    required_caveats: []
    blocked_by: [results, discussion]
    chunk_policy:
      unit: abstract
      locked_chunks: []
  - id: introduction
    path: paper/manuscript/sections/introduction.md
    status: not-ready
    allowed_claims: []
    required_figures: []
    required_sources: []
    required_caveats: []
    blocked_by: [results, discussion]
    chunk_policy:
      unit: introduction-block
      locked_chunks: []
  - id: results
    path: paper/manuscript/sections/results.md
    status: not-ready
    allowed_claims: []
    required_figures: []
    required_sources: []
    required_caveats: []
    blocked_by: [claim_matrix, figure_map]
    chunk_policy:
      unit: flow-sized-result-block
      locked_chunks: []
  - id: discussion
    path: paper/manuscript/sections/discussion.md
    status: not-ready
    allowed_claims: []
    required_figures: []
    required_sources: []
    required_caveats: []
    blocked_by: [results]
    chunk_policy:
      unit: discussion-block
      locked_chunks: []
  - id: methods
    path: paper/manuscript/sections/methods.md
    status: not-ready
    allowed_claims: []
    required_figures: []
    required_sources: []
    required_caveats: []
    blocked_by: [intake]
    chunk_policy:
      unit: method-block
      locked_chunks: []
""",
    "manuscript/sections/abstract.md": "",
    "manuscript/sections/introduction.md": "",
    "manuscript/sections/results.md": "",
    "manuscript/sections/discussion.md": "",
    "manuscript/sections/methods.md": "",
    "manuscript/si/si-outline.md": "",
    "manuscript/si/methods-detail.md": "",
    "manuscript/si/tables.md": "",
    "manuscript/si/figures.md": "",
    "manuscript/references.bib": "",
}


class WorkspaceInitError(Exception):
    pass


def ensure_safe_paper_write_target(path: Path, paper: Path) -> None:
    paper_root = _absolute_path(paper)
    target = _absolute_path(path)
    try:
        relative_target = target.relative_to(paper_root)
    except ValueError as exc:
        raise WorkspaceInitError(f"write target outside paper root: {path}") from exc
    if ".." in relative_target.parts:
        raise WorkspaceInitError(f"write target escapes paper root: {path}")
    candidate = paper_root
    if candidate.is_symlink():
        raise WorkspaceInitError(f"refusing to write through symlink under paper root: {candidate}")
    for part in relative_target.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise WorkspaceInitError(f"refusing to write through symlink under paper root: {candidate}")


def _absolute_path(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


def write_seed_file(path: Path, content: str, force: bool) -> bool:
    ensure_safe_paper_write_target(path, _paper_root_for(path))
    if path.exists() and path.read_text(encoding="utf-8") and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _paper_root_for(path: Path) -> Path:
    for parent in (path.parent, *path.parents):
        if parent.name == "paper":
            return parent
    raise WorkspaceInitError(f"cannot infer paper root for write target: {path}")


def initialize_workspace(root: Path, force: bool) -> tuple[Path, int, int]:
    paper = root / "paper"
    for rel_dir in PAPER_DIRS:
        ensure_safe_paper_write_target(paper / rel_dir, paper)
        (paper / rel_dir).mkdir(parents=True, exist_ok=True)

    written = 0
    preserved = 0
    for rel_path, content in sorted(SEED_FILES.items()):
        if write_seed_file(paper / rel_path, content, force):
            written += 1
        else:
            preserved += 1
    return paper, written, preserved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create an idempotent MESA manuscript paper/ workspace."
    )
    parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="Project root under which paper/ will be created.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rewrite existing seed files, including non-empty files.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        paper, written, preserved = initialize_workspace(args.root, args.force)
    except WorkspaceInitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        f"initialized {paper} "
        f"(written={written}, preserved_nonempty={preserved}, force={args.force})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
